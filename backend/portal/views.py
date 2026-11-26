"""The Guardian and student views (slice 8): a member's children, a child's day and their released
scores. Read only. A child is a student in `own_student_ids | linked_student_ids` that the engine
still opens for `scores.view` through the SELF or LINKED cell (so a child who left stays one for
scores until the leaving year ends); anyone else's student is a 404, never a 403."""

from django.db import models
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.fields import IntegerField
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from accounts.permissions import HasMembership
from grades.models import Gradebook, GradebookColumn, ScoreEntry
from grades.views import COLUMN_ORDER, latest_per_cell
from permissions.actor import Actor
from permissions.engine import can
from permissions.matrix import Scope
from schools.models import Enrollment, Student, Term
from timetable.models import AttendanceMark, TimetableEntry
from timetable.views import MORNING_FIRST, ON, date_param, in_force

from . import serializers

TERM = OpenApiParameter("term", int, description="A term of this school year; default today's")


def own_or_linked(actor: Actor):
    return Student.objects.filter(pk__in=actor.own_student_ids | actor.linked_student_ids)


def is_child(actor: Actor, student: Student) -> bool:
    """May the member read the student's released scores as themself or as their Guardian (a
    post-leave read)? Only the SELF and LINKED cells: a teacher who is also a Guardian must not
    reach their class's students through their teaching cell."""
    return any(
        can(actor, "scores.view", student, released=True, scope=scope)
        for scope in (Scope.SELF, Scope.LINKED)
    )


def get_child(request, pk) -> Student:
    actor = Actor.of(request)
    child = own_or_linked(actor).filter(pk=pk).first()
    if child is None or not is_child(actor, child):
        raise NotFound
    return child


class ChildrenView(GenericAPIView):
    """The member's children by name, each with their class today (null when not enrolled) and
    whether they left the School. Empty for anyone with none."""

    permission_classes = [HasMembership]
    serializer_class = serializers.ChildSerializer

    @extend_schema(responses=serializers.ChildSerializer(many=True))
    def get(self, request):
        actor = Actor.of(request)
        children = [
            student
            for student in own_or_linked(actor).order_by("full_name", "id")
            if is_child(actor, student)
        ]
        classes = dict(
            Enrollment.objects.in_force()
            .filter(student__in=children)
            .values_list("student_id", "school_class__name")
        )
        body = [
            {
                "id": child.pk,
                "name": child.full_name,
                "class_name": classes.get(child.pk),
                "left": not actor.student_access[child.pk].at_school,
            }
            for child in children
        ]
        return Response(serializers.ChildSerializer(body, many=True).data)


class ChildDayView(GenericAPIView):
    """The periods of the class the child is enrolled in on `?on=` (the School's day, default
    today), with the teacher's name and the child's mark. Empty when the member may not read that
    class's records (a child who left) or the class has no periods that day."""

    permission_classes = [HasMembership]
    serializer_class = serializers.ChildDaySerializer

    @extend_schema(parameters=[ON], responses=serializers.ChildDaySerializer)
    def get(self, request, pk):
        child = get_child(request, pk)
        on = date_param(request)
        actor = Actor.of(request)
        enrollment = (
            Enrollment.objects.in_force(on).filter(student=child).select_related("school_class")
        ).first()
        periods = []
        if enrollment and can(actor, "class_records.view", enrollment.school_class):
            klass = enrollment.school_class
            entries = in_force(
                TimetableEntry.objects.filter(school_class=klass, weekday=on.isoweekday()), on
            ).order_by(*MORNING_FIRST)
            rows = entries.values_list(
                "pk",
                "bell_period__session",
                "bell_period__number",
                "bell_period__starts_at",
                "bell_period__ends_at",
                "subject__name",
                "teacher__account__display_name",  # the name only, never the contact details
                "room__name",
            )
            # Cannot be false today when class_records.view holds; kept as defence.
            names = can(actor, "class_teachers.view", klass)
            marks = {}
            if can(actor, "attendance.view", child):
                marks = dict(
                    AttendanceMark.objects.filter(
                        entry__in=entries.values("pk"), on=on, student=child
                    ).values_list("entry_id", "status")
                )
            periods = [
                {
                    "session": session,
                    "number": number,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "subject_name": subject,
                    "teacher_name": teacher if names else None,
                    "room_name": room,
                    "status": marks.get(entry),
                }
                for entry, session, number, starts_at, ends_at, subject, teacher, room in rows
            ]
        return Response(serializers.ChildDaySerializer({"on": on, "periods": periods}).data)


def term_param(request):
    """`?term=`: a term of the school year in force today (400 `unknown` otherwise); default the
    term in force today, None when there is none."""
    today = timezone.localdate()
    terms = Term.objects.filter(school_year__starts_on__lte=today, school_year__ends_on__gte=today)
    raw = request.query_params.get("term")
    if raw is None:
        return terms.filter(starts_on__lte=today, ends_on__gte=today).first()
    try:
        term = terms.filter(pk=IntegerField().run_validation(raw)).first()
    except ValidationError:
        term = None
    if term is None:
        raise ValidationError({"term": ["unknown"]})
    return term


class ChildScoresView(GenericAPIView):
    """The child's released scores in `?term=`: one gradebook per class they were enrolled in
    during the term (a class change or a leave included) that has a released column, with the
    child's current entry of each released column. Unreleased columns are absent."""

    permission_classes = [HasMembership]
    serializer_class = serializers.ChildScoresSerializer

    @extend_schema(parameters=[TERM], responses=serializers.ChildScoresSerializer)
    def get(self, request, pk):
        child = get_child(request, pk)
        term = term_param(request)
        if term is None:
            body = {"term": None, "term_name": None, "gradebooks": []}
            return Response(serializers.ChildScoresSerializer(body).data)
        # The gradebook `roster` rule from the student's side: a class whose Enrollment overlaps
        # the term.
        classes = Enrollment.objects.filter(
            models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=term.starts_on),
            student=child,
            valid_from__lte=term.ends_on,
        ).values("school_class_id")
        books = Gradebook.objects.filter(term=term, school_class_id__in=classes)
        columns = (
            GradebookColumn.objects.filter(gradebook__in=books, released_at__isnull=False)
            .select_related("gradebook__subject", "gradebook__school_class")
            .order_by("gradebook__school_class__name", "gradebook__subject__name", *COLUMN_ORDER)
        )
        # Narrowed by column and student only (never by value), so a cleared cell stays blank.
        entries = {
            entry.column_id: entry
            for entry in latest_per_cell(
                ScoreEntry.objects.filter(
                    column__gradebook__in=books, column__released_at__isnull=False, student=child
                )
            )
        }
        gradebooks: dict[int, dict] = {}
        for column in columns:
            book = column.gradebook
            entry = entries.get(column.pk)
            gradebooks.setdefault(
                book.pk,
                {
                    "subject_name": book.subject.name,
                    "class_name": book.school_class.name,
                    "columns": [],
                },
            )["columns"].append(
                {
                    "kind": column.kind,
                    "index": column.index,
                    "value": entry.value if entry else None,
                    "result": entry.result if entry else None,
                    # Same rule as the teacher's grid: an entry after the release is a change.
                    "changed_after_release": bool(entry and entry.entered_at > column.released_at),
                }
            )
        body = {"term": term.pk, "term_name": term.name, "gradebooks": list(gradebooks.values())}
        return Response(serializers.ChildScoresSerializer(body).data)
