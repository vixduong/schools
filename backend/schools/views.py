from contextlib import contextmanager
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.fields import ChoiceField, DateField, IntegerField
from rest_framework.response import Response

from accounts.models import RoleAssignment
from accounts.permissions import HasMembership, NotRequesterOrAssignee
from permissions.drf import Can

from . import serializers
from .models import (
    AssessmentProfileVersion,
    Enrollment,
    Grade,
    GuardianLink,
    Level,
    Room,
    SchoolClass,
    SchoolYear,
    Student,
    StudentStatusEvent,
    Subject,
    SubjectGroup,
    Term,
    status_as_of,
)

# What a leave does to the student's status: the same word, except the transfer.
LEAVE_STATUS = {
    Enrollment.ReasonEnded.TRANSFER_OUT: Student.Status.TRANSFERRED_OUT,
    Enrollment.ReasonEnded.DROPPED_OUT: Student.Status.DROPPED_OUT,
    Enrollment.ReasonEnded.GRADUATED: Student.Status.GRADUATED,
}


class SetupViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """School admin only (`school.configure`). No DELETE: years, classes and role assignments are
    ended or kept, rooms and subjects are deactivated (history instead of deletes). Querysets
    need no School filter: RLS shows only the request's School."""

    permission_classes = [HasMembership, Can("school.configure")]

    def perform_create(self, serializer):
        self._save(serializer)

    def perform_update(self, serializer):
        self._save(serializer)

    def _save(self, serializer, **extra):
        with self._database_rules():
            serializer.save(**extra)

    @contextmanager
    def _database_rules(self):
        """Writes in one savepoint. A rule only the database can check (overlap, term inside
        year, grade range, role scope, same-School references) answers 400 naming the constraint,
        not 500, and undoes every write in the block."""
        try:
            with transaction.atomic():
                yield
        except IntegrityError as error:
            name = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
            raise ValidationError({"constraint": [name or "unknown"]}) from error


class SchoolYearViewSet(SetupViewSet):
    queryset = SchoolYear.objects.order_by("starts_on", "id")
    serializer_class = serializers.SchoolYearSerializer

    @extend_schema(request=None, responses=serializers.SchoolYearSerializer)
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        """End every open enrollment of the year on its last day (`year_end`), in one
        transaction. Idempotent: a second call finds none open. Run it before enrolling
        continuing students in the next year, whose periods may not overlap."""
        self.get_object()  # 404 for another School's row
        with self._database_rules():
            year = SchoolYear.objects.select_for_update().get(pk=pk)
            Enrollment.objects.filter(school_year=year, valid_to__isnull=True).update(
                valid_to=year.ends_on, reason_ended=Enrollment.ReasonEnded.YEAR_END
            )
        return Response(self.get_serializer(year).data)


class TermViewSet(SetupViewSet):
    queryset = Term.objects.order_by("starts_on", "id")
    serializer_class = serializers.TermSerializer


class LevelViewSet(SetupViewSet):
    queryset = Level.objects.order_by("id")
    serializer_class = serializers.LevelSerializer


class GradeViewSet(SetupViewSet):
    queryset = Grade.objects.order_by("number")
    serializer_class = serializers.GradeSerializer


class SubjectGroupViewSet(SetupViewSet):
    queryset = SubjectGroup.objects.order_by("name", "id")
    serializer_class = serializers.SubjectGroupSerializer


class SubjectViewSet(SetupViewSet):
    queryset = Subject.objects.order_by("code")
    serializer_class = serializers.SubjectSerializer


class RoomViewSet(SetupViewSet):
    queryset = Room.objects.order_by("name", "id")
    serializer_class = serializers.RoomSerializer


class SchoolClassViewSet(SetupViewSet):
    queryset = SchoolClass.objects.order_by("school_year_id", "name")
    serializer_class = serializers.SchoolClassSerializer


class RoleAssignmentViewSet(SetupViewSet):
    permission_classes = [HasMembership, Can("accounts.manage")]
    queryset = RoleAssignment.objects.order_by("id")
    serializer_class = serializers.RoleAssignmentSetupSerializer

    @extend_schema(request=None)
    @action(
        detail=True,
        methods=["post"],
        # The School admin (✔) and the principal board (👁) may confirm, as in slice 4.
        permission_classes=[
            HasMembership,
            Can("accounts.manage", read=True),
            NotRequesterOrAssignee,
        ],
    )
    def confirm(self, request, pk=None):
        """A second person confirms a self-granted principal_board (never its requester or the
        assignee: NotRequesterOrAssignee)."""
        assignment = self.get_object()
        if assignment.status != RoleAssignment.Status.PENDING_CONFIRMATION:
            raise ValidationError({"status": ["not_pending_confirmation"]})
        assignment.status = RoleAssignment.Status.ACTIVE
        assignment.confirmed_by = request.membership
        assignment.confirmed_at = timezone.now()
        assignment.save(update_fields=["status", "confirmed_by", "confirmed_at"])
        return Response(self.get_serializer(assignment).data)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                "status", str, enum=Student.Status.values, description="Only this status today"
            )
        ]
    )
)
class StudentViewSet(SetupViewSet):
    queryset = Student.objects.order_by("full_name", "id").prefetch_related(
        "studentstatusevent_set"
    )
    serializer_class = serializers.StudentSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return serializers.StudentListSerializer
        return super().get_serializer_class()

    def filter_queryset(self, queryset):
        if self.action == "list" and "status" in self.request.query_params:
            wanted = ChoiceField(Student.Status.choices).run_validation(
                self.request.query_params["status"]
            )
            queryset = queryset.with_status().filter(current_status=wanted)
        return queryset

    @extend_schema(methods=["GET"], responses=serializers.StudentStatusEventSerializer(many=True))
    @extend_schema(
        methods=["POST"],
        request=serializers.StudentStatusEventSerializer,
        responses={201: serializers.StudentStatusEventSerializer},
    )
    @action(detail=True, methods=["get", "post"], url_path="status-events")
    def status_events(self, request, pk=None):
        """The student's status history (GET) and the way to record a return (POST, `studying`
        only, which may be dated in the future). The status on a date is the latest event up to
        that date; leaving goes through `leave/`."""
        student = self.get_object()
        context = self.get_serializer_context()
        if request.method == "GET":
            events = StudentStatusEvent.objects.filter(student=student).order_by("on", "id")
            return Response(
                serializers.StudentStatusEventSerializer(events, many=True, context=context).data
            )
        serializer = serializers.StudentStatusEventSerializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        self._save(serializer, student=student, recorded_by=request.membership)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(request=serializers.LeaveSerializer, responses=serializers.StudentSerializer)
    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        """The student leaves (transfer out, drop out, graduation): the open enrollment ends on
        `on` and the matching status event is recorded with that date, in one transaction. A
        future `on` schedules the leave: the student stays in the class and `studying` until
        then. Nothing is deleted; this School keeps the student's records."""
        self.get_object()  # 404 for another School's row
        leaving = serializers.LeaveSerializer(data=request.data)
        leaving.is_valid(raise_exception=True)
        reason, on = leaving.validated_data["reason"], leaving.validated_data["on"]
        destination = leaving.validated_data.get("destination", "")
        with self._database_rules():
            student = Student.objects.select_for_update().get(pk=pk)
            events = StudentStatusEvent.objects.filter(student=student)
            if status_as_of(events, on) != Student.Status.STUDYING:
                raise ValidationError({"status": ["not_studying"]})
            row = (
                Enrollment.objects.select_for_update()
                .filter(student=student, valid_to__isnull=True)
                .first()
            )
            if row is None:
                raise ValidationError({"enrollment": ["no_open_enrollment"]})
            if on < row.valid_from:
                raise ValidationError({"on": ["before_enrollment_start"]})
            row.valid_to = on
            row.reason_ended = reason
            row.save(update_fields=["valid_to", "reason_ended"])
            StudentStatusEvent.objects.create(
                school=request.school,
                student=student,
                status=LEAVE_STATUS[reason],
                on=on,
                reason=f"Transferred out to {destination}"
                if reason == Enrollment.ReasonEnded.TRANSFER_OUT
                else Enrollment.ReasonEnded(reason).label,
                recorded_by=request.membership,
            )
        return Response(self.get_serializer(self.get_queryset().get(pk=pk)).data)

    @extend_schema(request=None, responses=serializers.StudentSerializer)
    @action(detail=True, methods=["post"], url_path="leave/cancel")
    def cancel_leave(self, request, pk=None):
        """Cancel a leave scheduled for a later day: a `studying` event with the leave's date
        (the later event wins) and the enrollment open again, in one transaction. A leave whose
        day has come is a fact and is refused. This is the only way a `valid_to` is cleared."""
        self.get_object()  # 404 for another School's row
        with self._database_rules():
            student = Student.objects.select_for_update().get(pk=pk)
            row = (
                Enrollment.objects.select_for_update()
                .filter(student=student, reason_ended__in=list(LEAVE_STATUS))
                .order_by("-valid_to")
                .first()
            )
            if row is None:
                raise ValidationError({"leave": ["no_leave"]})
            if row.valid_to <= timezone.localdate():
                raise ValidationError({"leave": ["leave_already_effective"]})
            StudentStatusEvent.objects.create(
                school=request.school,
                student=student,
                status=Student.Status.STUDYING,
                on=row.valid_to,
                reason="Leave cancelled",
                recorded_by=request.membership,
            )
            row.valid_to = None
            row.reason_ended = None
            row.save(update_fields=["valid_to", "reason_ended"])
        return Response(self.get_serializer(self.get_queryset().get(pk=pk)).data)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("school_class", int, description="Only this class"),
            OpenApiParameter("student", int, description="Only this student"),
            OpenApiParameter("on", str, description="Only periods in force on this date"),
        ]
    )
)
class EnrollmentViewSet(SetupViewSet):
    queryset = Enrollment.objects.order_by("school_year_id", "student_id", "valid_from")
    serializer_class = serializers.EnrollmentSerializer

    def filter_queryset(self, queryset):
        """The class list: `?school_class=7&on=2026-10-01` is who is in the class that day."""
        if self.action != "list":
            return queryset
        params = self.request.query_params
        for name in ("school_class", "student"):
            if name in params:
                queryset = queryset.filter(
                    **{f"{name}_id": IntegerField().run_validation(params[name])}
                )
        if "on" in params:
            on = DateField().run_validation(params["on"])
            queryset = queryset.in_force(on)
        return queryset

    @extend_schema(
        request=serializers.EnrollmentMoveSerializer,
        responses={201: serializers.EnrollmentSerializer},
    )
    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        """Move the student to another class of the same year: the current period ends the day
        before `on` (`class_change`) and a new one starts on `on`, in one transaction."""
        self.get_object()  # 404 for another School's row
        move = serializers.EnrollmentMoveSerializer(data=request.data)
        move.is_valid(raise_exception=True)
        klass, on = move.validated_data["school_class"], move.validated_data["on"]
        with self._database_rules():
            row = Enrollment.objects.select_for_update().get(pk=pk)
            if row.valid_to is not None:
                raise ValidationError({"enrollment": ["already_ended"]})
            if on <= row.valid_from:
                raise ValidationError({"on": ["must_be_after_valid_from"]})
            if klass.pk == row.school_class_id:
                raise ValidationError({"school_class": ["same_class"]})
            row.valid_to = on - timedelta(days=1)
            row.reason_ended = Enrollment.ReasonEnded.CLASS_CHANGE
            row.save(update_fields=["valid_to", "reason_ended"])
            started = Enrollment.objects.create(
                school=request.school,
                student_id=row.student_id,
                school_year_id=row.school_year_id,
                school_class=klass,
                valid_from=on,
                reason_started=Enrollment.ReasonStarted.CLASS_CHANGE,
            )
        context = self.get_serializer_context()
        data = serializers.EnrollmentSerializer(started, context=context).data
        return Response(data, status=status.HTTP_201_CREATED)


class GuardianLinkViewSet(SetupViewSet):
    queryset = GuardianLink.objects.order_by("id")
    serializer_class = serializers.GuardianLinkSerializer


class AssessmentProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """Any member of the School may read the rules; they are global and arrive by migration."""

    permission_classes = [HasMembership]
    queryset = AssessmentProfileVersion.objects.order_by("level_kind", "effective_from")
    serializer_class = serializers.AssessmentProfileVersionSerializer
