from contextlib import contextmanager
from datetime import timedelta

from django.db import IntegrityError, models, transaction
from django.db.models import F, Q, Value
from django.db.models.functions import Greatest
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.fields import ChoiceField, DateField, IntegerField
from rest_framework.response import Response

from accounts.invitations import issue_code
from accounts.models import Invitation, Membership, RoleAssignment
from accounts.permissions import HasMembership, NotRequesterOrAssignee
from permissions.actor import Actor
from permissions.drf import Can
from permissions.engine import can, visible_students

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


@contextmanager
def database_rules():
    """Writes in one savepoint. A rule only the database can check (overlap, term inside year,
    grade range, role scope, same-School references) answers 400 naming the constraint, not 500,
    and undoes every write in the block."""
    try:
        with transaction.atomic():
            yield
    except IntegrityError as error:
        name = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
        raise ValidationError({"constraint": [name or "unknown"]}) from error


class SetupViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Reads for the School admin and the principal board (`school.configure`, 👁 for the board);
    writes for the School admin only: `read=True` lets a read-only cell through for GET, HEAD and
    OPTIONS and never for a write (the one exception is `confirm` below). No DELETE: years,
    classes and role assignments are ended or kept, rooms and subjects are deactivated (history
    instead of deletes). Querysets need no School filter: RLS shows only the request's School."""

    permission_classes = [HasMembership, Can("school.configure", read=True)]

    def perform_create(self, serializer):
        self._save(serializer)

    def perform_update(self, serializer):
        self._save(serializer)

    def _save(self, serializer, **extra):
        with self._database_rules():
            serializer.save(**extra)

    _database_rules = staticmethod(database_rules)


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
    permission_classes = [HasMembership, Can("accounts.manage", read=True)]
    queryset = RoleAssignment.objects.order_by("id")
    serializer_class = serializers.RoleAssignmentSetupSerializer

    @extend_schema(request=None)
    @action(
        detail=True,
        methods=["post"],
        # The School admin (✔) and the principal board (👁) may confirm, as in slice 4.
        permission_classes=[
            HasMembership,
            Can("accounts.manage", read=True, read_on_writes=True),
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

    @staticmethod
    def _last_enrollment(student):
        """The student's latest period, locked; None when there is none."""
        return (
            Enrollment.objects.select_for_update()
            .filter(student=student)
            .order_by("valid_from", "id")
            .last()
        )

    def _record_cancellation(self, request, student, on):
        StudentStatusEvent.objects.create(
            school=request.school,
            student=student,
            status=Student.Status.STUDYING,
            on=on,
            reason="Leave cancelled",
            recorded_by=request.membership,
        )

    @extend_schema(request=serializers.LeaveSerializer, responses=serializers.StudentSerializer)
    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        """The student leaves (transfer out, drop out, graduation): the open enrollment ends on
        `on` and the matching status event is recorded with that date, in one transaction. A
        future `on` schedules the leave: the student stays in the class and `studying` until
        then. A continuing student between school years (no open enrollment, the last one ended
        `year_end`) leaves with the status event alone, dated on or after that enrollment's end.
        Nothing is deleted; this School keeps the student's records."""
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
                # Between school years the leave is only the status event: nothing to end.
                last = self._last_enrollment(student)
                if last is None or last.reason_ended != Enrollment.ReasonEnded.YEAR_END:
                    raise ValidationError({"enrollment": ["no_open_enrollment"]})
                if on < last.valid_to:
                    raise ValidationError({"on": ["before_enrollment_end"]})
            else:
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
            last = self._last_enrollment(student)
            if last is not None and last.reason_ended == Enrollment.ReasonEnded.YEAR_END:
                # A leave recorded between school years has no enrollment to reopen: cancelling
                # appends the `studying` event (the later event wins) and nothing else.
                event = (
                    StudentStatusEvent.objects.filter(student=student).order_by("on", "id").last()
                )
                if event is None or event.status == Student.Status.STUDYING:
                    raise ValidationError({"leave": ["no_leave"]})
                if event.on <= timezone.localdate():
                    raise ValidationError({"leave": ["leave_already_effective"]})
                self._record_cancellation(request, student, event.on)
                return Response(self.get_serializer(self.get_queryset().get(pk=pk)).data)
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
            self._record_cancellation(request, student, row.valid_to)
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


class MembershipViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """The people of this School: read by the School admin and the principal board, deactivated
    and reactivated by the School admin (`accounts.manage`). People join through invitations."""

    permission_classes = [HasMembership, Can("accounts.manage", read=True)]
    queryset = Membership.objects.select_related("account").order_by("id")
    serializer_class = serializers.MembershipSerializer

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """End the person's Role Assignments and Guardian links still running after today (dated
        today, or their first day when that is later) and set the Membership inactive, which
        also ends their sessions' access. Refused for the last in-force School admin (appoint
        the replacement first). Idempotent."""
        today = timezone.localdate()
        membership = self.get_object()
        with database_rules():
            # The admin rows first, then the Membership, in the order role edits lock them.
            for role in RoleAssignment.objects.in_force().filter(
                membership=membership, role=RoleAssignment.Role.SCHOOL_ADMIN
            ):
                try:
                    serializers.ensure_school_admin_coverage(role, today)
                except ValidationError as error:
                    raise ValidationError({"status": error.detail}) from None
            membership = Membership.objects.select_for_update().get(pk=membership.pk)
            today_value = Value(today, output_field=models.DateField())
            ends = {"valid_to": Greatest(today_value, F("valid_from"))}
            running = Q(valid_to__isnull=True) | Q(valid_to__gt=today)
            RoleAssignment.objects.filter(running, membership=membership).update(**ends)
            GuardianLink.objects.filter(running, membership=membership).update(**ends)
            membership.status = Membership.Status.INACTIVE
            membership.save(update_fields=["status"])
        return Response(self.get_serializer(membership).data)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        """Set the Membership active again; no role or link comes back (assign them anew)."""
        membership = self.get_object()
        membership.status = Membership.Status.ACTIVE
        membership.save(update_fields=["status"])
        return Response(self.get_serializer(membership).data)


class InvitationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Invitations to join this School. The School admin issues every kind (`accounts.manage`,
    `guardian_invite.issue`); a homeroom teacher issues guardian and student invitations for
    students of their class (`guardian_invite.issue`). Each member lists the invitations they
    may issue (the principal board reads staff invitations). Never edited or deleted: `revoke/`.
    """

    permission_classes = [HasMembership]
    queryset = Invitation.objects.select_related("student").prefetch_related("roles").order_by("id")
    serializer_class = serializers.InvitationSerializer

    def get_queryset(self):
        actor = Actor.of(self.request)
        visible = Q(student__in=visible_students(actor, "guardian_invite.issue"))
        if can(actor, "accounts.manage", self.request.school, read=True):
            visible |= Q(kind=Invitation.Kind.STAFF)
        return super().get_queryset().filter(visible)

    def perform_create(self, serializer):
        with database_rules():
            serializer.save(created_by=self.request.membership)

    @extend_schema(request=None)
    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        """A pending invitation (expired or not) stops working."""
        invitation = self.get_object()
        actor = Actor.of(request)
        if not serializers.may_issue(actor, invitation.kind, invitation.student, request.school):
            raise PermissionDenied()
        if invitation.status != Invitation.Status.PENDING:
            raise ValidationError({"status": ["not_pending"]})
        invitation.status = Invitation.Status.REVOKED
        invitation.save(update_fields=["status"])
        return Response(self.get_serializer(invitation).data)

    @extend_schema(
        request=serializers.InvitationPrintSerializer,
        responses=serializers.InvitationSerializer(many=True),
    )
    @action(detail=False, methods=["post"])
    def print(self, request):
        """The printable list of a class: the pending guardian and student invitations of the
        students in the class today, each with a fresh code and expiry (codes are stored only as
        a digest, so printing again replaces the codes of the previous print). JSON for now; a
        PDF comes with the report-card pipeline."""
        body = serializers.InvitationPrintSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        school_class = body.validated_data["school_class"]
        if not can(Actor.of(request), "guardian_invite.issue", school_class):
            raise PermissionDenied()
        invitations = list(
            Invitation.objects.select_for_update(of=("self",))
            .filter(
                status=Invitation.Status.PENDING,
                student__in=Enrollment.objects.in_force()
                .filter(school_class=school_class)
                .values("student_id"),
            )
            .select_related("student")
            .order_by("student__full_name", "student_id", "kind", "id")
        )
        for invitation in invitations:
            invitation.code = issue_code(invitation)
            invitation.save(update_fields=["code_digest", "expires_at"])
        return Response(self.get_serializer(invitations, many=True).data)


class AssessmentProfileViewSet(viewsets.ReadOnlyModelViewSet):
    """Any member of the School may read the rules; they are global and arrive by migration."""

    permission_classes = [HasMembership]
    queryset = AssessmentProfileVersion.objects.order_by("level_kind", "effective_from")
    serializer_class = serializers.AssessmentProfileVersionSerializer
