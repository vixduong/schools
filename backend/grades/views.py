from decimal import Decimal, InvalidOperation

from django.db import models
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.fields import IntegerField
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from accounts.permissions import HasMembership
from permissions.actor import Actor, TeachingPair
from permissions.drf import Can, CanPermission
from permissions.engine import can, visible_pairs
from schools.models import (
    AssessmentProfileVersion,
    Enrollment,
    Level,
    SchoolClass,
    Student,
    Subject,
    SubjectLoad,
    Term,
)
from schools.views import database_rules

from . import serializers
from .models import Gradebook, GradebookColumn, ScoreEntry

SECONDARY = (Level.Kind.LOWER_SECONDARY, Level.Kind.UPPER_SECONDARY)
SCALE_MAX = Decimal(10)
ONE_DECIMAL = Decimal("0.1")

# Regular columns first, then the mid-term and end-term tests.
COLUMN_ORDER = (
    models.Case(
        models.When(kind=GradebookColumn.Kind.REGULAR, then=0),
        models.When(kind=GradebookColumn.Kind.MID_TERM, then=1),
        default=2,
    ),
    "index",
)


def pair_of(gradebook):
    return TeachingPair(gradebook.subject, gradebook.school_class)


def gradebook_pair(request, view):
    return pair_of(view.get_gradebook())


def open_pair(request, view):
    body = view.open_body(request)
    return TeachingPair(body["subject"], body["school_class"])


class CanUseGradebook(CanPermission):
    """A gradebook by the subject x class it belongs to: `scores.view` to read it (every teacher
    and the board), `scores.enter` to write (the subject teacher of the pair)."""

    def has_permission(self, request, view):
        action = "scores.view" if request.method in SAFE_METHODS else "scores.enter"
        return Can(action, gradebook_pair)().has_permission(request, view)


class CanListOrOpen(CanPermission):
    """Listing needs `scores.view`; opening one needs `scores.enter` on the pair in the body."""

    def has_permission(self, request, view):
        permission = (
            Can("scores.view") if request.method in SAFE_METHODS else Can("scores.enter", open_pair)
        )
        return permission().has_permission(request, view)


def current_entries(gradebook):
    """The latest entry of every cell of the gradebook that has one. Narrow it by column or
    student, never by value: a WHERE runs before DISTINCT ON."""
    return (
        ScoreEntry.objects.filter(column__gradebook=gradebook)
        .order_by("column_id", "student_id", "-entered_at", "-id")
        .distinct("column_id", "student_id")
    )


def roster(gradebook, today):
    """([(id, name)] by name, ids still in the class today): the students enrolled in the class at
    any time during the term, and those among them a new score may still be entered for (the rule
    of `scoreentry_student_in_class`)."""
    term = gradebook.term
    during_term = Enrollment.objects.filter(
        models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=term.starts_on),
        school_class=gradebook.school_class,
        valid_from__lte=term.ends_on,
    )
    students = (
        Student.objects.filter(pk__in=during_term.values("student_id"))
        .order_by("full_name", "id")
        .values_list("id", "full_name")
    )
    in_class = set(during_term.in_force(today).values_list("student_id", flat=True))
    return list(students), in_class


def int_param(request, name):
    raw = request.query_params.get(name)
    if raw is None:
        raise ValidationError({name: ["required"]})
    return IntegerField().run_validation(raw)


class GradebookMixin:
    """The gradebook in the URL (404 for one of another School: RLS shows none)."""

    def get_gradebook(self):
        if not hasattr(self, "gradebook"):
            self.gradebook = (
                Gradebook.objects.select_related(
                    "term", "subject", "school_class", "profile_version"
                )
                .filter(pk=self.kwargs["pk"])
                .first()
            )
        if self.gradebook is None:
            raise NotFound
        return self.gradebook

    @staticmethod
    def lock(gradebook):
        """Saves, releases (and slice 5's submit) of one gradebook take turns; a score entry in
        flight holds it FOR SHARE (a trigger) and so conflicts with a lock taken this way."""
        Gradebook.objects.select_for_update(no_key=True).get(pk=gradebook.pk)
        gradebook.refresh_from_db(fields=["status"])
        if gradebook.status != Gradebook.Status.DRAFT:
            raise ValidationError({"gradebook": ["not_draft"]})


def regular_columns(rules, subject, periods_per_year):
    """How many regular columns the profile gives the subject (ADR 0006 `rules`)."""
    regular = rules["regular_assessments"]
    if subject.assessment == Subject.Assessment.COMMENT_ONLY:
        return regular["comment_only"]
    for band in regular["scored_by_periods_per_year"]:
        if band["up_to"] is None or periods_per_year <= band["up_to"]:
            return band["count"]
    raise AssertionError("the last band has no limit")


class GradebooksView(GradebookMixin, GenericAPIView):
    """GET: the gradebooks the member may see (`scores.view`), by `?term=&school_class=&subject=`.
    POST: open one, or return the existing one (200); the subject teacher of the pair only."""

    permission_classes = [HasMembership, CanListOrOpen]
    serializer_class = serializers.GradebookSerializer

    def open_body(self, request):
        if not hasattr(self, "opened"):
            body = serializers.OpenGradebookSerializer(data=request.data)
            body.is_valid(raise_exception=True)
            self.opened = body.validated_data
        return self.opened

    @extend_schema(
        parameters=[
            OpenApiParameter(name, int, description=f"Only this {name}")
            for name in ("term", "school_class", "subject")
        ],
        responses=serializers.GradebookSerializer(many=True),
    )
    def get(self, request):
        books = Gradebook.objects.filter(visible_pairs(Actor.of(request), "scores.view"))
        for name in ("term", "school_class", "subject"):
            if name in request.query_params:
                books = books.filter(**{f"{name}_id": int_param(request, name)})
        books = books.select_related("term", "subject", "school_class").order_by("-id")
        return Response(serializers.GradebookSerializer(books, many=True).data)

    @extend_schema(
        request=serializers.OpenGradebookSerializer,
        responses={
            200: serializers.GradebookDetailSerializer,
            201: serializers.GradebookDetailSerializer,
        },
    )
    def post(self, request):
        body = self.open_body(request)
        term, subject, klass = body["term"], body["subject"], body["school_class"]
        if term.school_year_id != klass.school_year_id:
            raise ValidationError({"term": ["not_in_class_year"]})
        existing = Gradebook.objects.filter(term=term, subject=subject, school_class=klass).first()
        if existing is not None:
            return Response(detail(request, existing))
        created = self.open(request, term, subject, klass)
        if created is None:  # opened by someone else while this request waited
            return Response(detail(request, self.existing(term, subject, klass)))
        return Response(detail(request, created), status=status.HTTP_201_CREATED)

    @staticmethod
    def existing(term, subject, klass):
        return Gradebook.objects.get(term=term, subject=subject, school_class=klass)

    def open(self, request, term, subject, klass):
        """The gradebook with its columns, in one transaction; None when it already exists. The
        profile version is the class's Level kind's in force on the school year's first day."""
        year = klass.school_year
        version = (
            AssessmentProfileVersion.objects.filter(
                models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=year.starts_on),
                level_kind=klass.grade.level.kind,
                effective_from__lte=year.starts_on,
            )
            .order_by("-effective_from")
            .first()
        )
        if version is None:
            raise ValidationError({"gradebook": ["no_profile_version"]})
        with database_rules():
            # The load decides the columns and is frozen once a gradebook exists: holding it FOR
            # NO KEY UPDATE makes two openings, and an edit of the load, take turns.
            load = (
                SubjectLoad.objects.select_for_update(no_key=True)
                .filter(school_year=year, grade=klass.grade, subject=subject)
                .first()
            )
            if load is None:
                raise ValidationError({"gradebook": ["no_subject_load"]})
            if Gradebook.objects.filter(term=term, subject=subject, school_class=klass).exists():
                return None
            gradebook = Gradebook.objects.create(
                school=request.school,
                school_year=year,
                term=term,
                subject=subject,
                school_class=klass,
                profile_version=version,
                opened_by=request.membership,
            )
            rules = version.rules
            counts = {
                GradebookColumn.Kind.REGULAR: regular_columns(
                    rules, subject, load.periods_per_year
                ),
                GradebookColumn.Kind.MID_TERM: rules["periodic"]["mid_term"],
                GradebookColumn.Kind.END_TERM: rules["periodic"]["end_term"],
            }
            GradebookColumn.objects.bulk_create(
                GradebookColumn(school=request.school, gradebook=gradebook, kind=kind, index=index)
                for kind, count in counts.items()
                for index in range(1, count + 1)
            )
        return gradebook


def detail(request, gradebook):
    """The grid: header, columns, and a row per student enrolled in the class during the term with
    each cell's current entry."""
    today = timezone.localdate()
    students, in_class = roster(gradebook, today)
    released = {
        (column, student): count
        for column, student, count in ScoreEntry.objects.filter(
            column__gradebook=gradebook, entered_at__gt=models.F("column__released_at")
        )
        .values_list("column_id", "student_id")
        .annotate(count=models.Count("id"))
    }
    cells: dict[int, list] = {}
    for entry in current_entries(gradebook):
        cells.setdefault(entry.student_id, []).append(
            {
                "column": entry.column_id,
                "entry": entry.pk,
                "value": entry.value,
                "result": entry.result,
                # shortcut: any entry after the release counts as a change (the plan says "more
                # than one"; see the slice report).
                "changed_after_release": (entry.column_id, entry.student_id) in released,
            }
        )
    gradebook.profile_source = gradebook.profile_version.source
    gradebook.can_enter = can(Actor.of(request), "scores.enter", pair_of(gradebook))
    gradebook.columns = gradebook.gradebookcolumn_set.order_by(*COLUMN_ORDER)
    gradebook.students = [
        {"id": pk, "name": name, "in_class": pk in in_class, "cells": cells.get(pk, [])}
        for pk, name in students
    ]
    return serializers.GradebookDetailSerializer(gradebook).data


class GradebookView(GradebookMixin, GenericAPIView):
    permission_classes = [HasMembership, CanUseGradebook]
    serializer_class = serializers.GradebookDetailSerializer

    @extend_schema(responses=serializers.GradebookDetailSerializer)
    def get(self, request, pk):
        return Response(detail(request, self.get_gradebook()))


def judge(cell, assessment):
    """(code, value): what is wrong with a cell's form or value (None when nothing), and the value
    as a one-decimal Decimal (None for a cleared cell or a result). The API never rounds."""
    value, result = cell["value"], cell["result"]
    if assessment == Subject.Assessment.COMMENT_ONLY:
        return ("wrong_form" if value is not None else None), None
    if result is not None:
        return "wrong_form", None
    if value is None:
        return None, None
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return "wrong_form", None
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        return "wrong_form", None
    if not number.is_finite():
        return "wrong_form", None
    if number.normalize().as_tuple().exponent < -1:
        return "too_many_decimals", None
    if not 0 <= number <= SCALE_MAX:
        return "out_of_range", None
    return None, number.quantize(ONE_DECIMAL)


def describe(entry):
    """A cell's current entry as the screen shows it beside a conflicting save."""
    return {
        "entry": entry.pk,
        "value": entry.value,
        "result": entry.result,
        "entered_by_name": entry.entered_by.account.display_name,
        "entered_at": entry.entered_at,
    }


def check_cell(cell, assessment, in_class, now):
    """(code, value) for one cell against its `now` (current entry): the code of what is wrong
    (None when nothing) and the value to save. A student who left, then a bad form or value,
    then a stale `expected` (someone else saved the cell meanwhile)."""
    if cell["student"] not in in_class:
        return "not_enrolled", None
    code, value = judge(cell, assessment)
    if code is None and (now.pk if now else None) != cell["expected"]:
        return "conflict", None
    return code, value


class GradebookCellsView(GradebookMixin, GenericAPIView):
    """Save cells of the grid, all or nothing. In one transaction, with the gradebook locked: a
    cell whose current entry is not the one the client last saw (`expected`) is a conflict, an
    invalid one an error; any of either and nothing is saved (400 with each failing cell's code),
    otherwise an entry is appended for every cell whose value differs from its current one."""

    permission_classes = [HasMembership, CanUseGradebook]
    serializer_class = serializers.SaveCellsSerializer

    @extend_schema(
        request=serializers.SaveCellsSerializer,
        responses={200: serializers.SavedCellsSerializer, 400: serializers.CellErrorsSerializer},
    )
    def put(self, request, pk):
        gradebook = self.get_gradebook()
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        given = body.validated_data["cells"]
        # A gradebook never gains or loses a column, so they are read before the lock.
        columns = set(gradebook.gradebookcolumn_set.values_list("pk", flat=True))
        if any(cell["column"] not in columns for cell in given):
            raise ValidationError({"cells": ["unknown_column"]})
        with database_rules():
            self.lock(gradebook)  # everything below reads what the last saver committed
            _, in_class = roster(gradebook, timezone.localdate())
            current = {
                (entry.column_id, entry.student_id): entry
                for entry in current_entries(gradebook).select_related("entered_by__account")
            }
            checked, errors = [], []
            for cell in given:
                now = current.get((cell["column"], cell["student"]))
                code, value = check_cell(cell, gradebook.subject.assessment, in_class, now)
                if code is None:
                    checked.append((cell, value, now))
                else:
                    errors.append(
                        {
                            "column": cell["column"],
                            "student": cell["student"],
                            "code": code,
                            "current": describe(now) if code == "conflict" and now else None,
                        }
                    )
            if errors:
                return Response({"cells": errors}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"cells": self.append(request, gradebook, checked)})

    @staticmethod
    def append(request, gradebook, checked):
        """An entry for every checked cell whose value or result differs from its current one;
        the cells with the id of their current entry afterwards."""
        # Never earlier than an entry already saved, whatever the clocks say: the latest entry
        # (by time, then id) is the cell's score.
        last = ScoreEntry.objects.filter(column__gradebook=gradebook).aggregate(
            last=models.Max("entered_at")
        )["last"]
        at = max(timezone.now(), last) if last else timezone.now()
        written = {}
        for cell, value, now in checked:
            if (value, cell["result"]) != ((now.value, now.result) if now else (None, None)):
                written[cell["column"], cell["student"]] = ScoreEntry(
                    school=request.school,
                    column_id=cell["column"],
                    student_id=cell["student"],
                    value=value,
                    result=cell["result"],
                    entered_by=request.membership,
                    entered_at=at,
                )
        ScoreEntry.objects.bulk_create(written.values())
        return [
            {
                "column": cell["column"],
                "student": cell["student"],
                "entry": written[key].pk if key in written else (now.pk if now else None),
            }
            for cell, _, now in checked
            for key in [(cell["column"], cell["student"])]
        ]


class ColumnReleaseView(GradebookMixin, GenericAPIView):
    """The subject teacher releases a column once, when every student still enrolled has a score
    in it."""

    permission_classes = [HasMembership, CanUseGradebook]
    serializer_class = serializers.ColumnSerializer

    @extend_schema(
        request=None,
        responses={200: serializers.ColumnSerializer, 400: serializers.ReleaseIncompleteSerializer},
    )
    def post(self, request, pk, column):
        gradebook = self.get_gradebook()
        with database_rules():
            self.lock(gradebook)
            students, in_class = roster(gradebook, timezone.localdate())
            released = GradebookColumn.objects.filter(gradebook=gradebook, pk=column).first()
            if released is None:
                raise NotFound
            if released.released_at is not None:
                raise ValidationError({"column": ["already_released"]})
            # Filtered here, not in SQL: a WHERE runs before DISTINCT ON and would bring back the
            # entry a clearing replaced.
            scored = {
                entry.student_id
                for entry in current_entries(gradebook).filter(column=released)
                if entry.value is not None or entry.result is not None
            }
            missing = [
                {"id": pk, "name": name}
                for pk, name in students
                if pk in in_class and pk not in scored
            ]
            if missing:
                return Response(
                    {"column": ["incomplete"], "students": missing},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            released.released_at = timezone.now()
            released.released_by = request.membership
            released.save(update_fields=["released_at", "released_by"])
        return Response(serializers.ColumnSerializer(released).data)


class GradebookHistoryView(GradebookMixin, GenericAPIView):
    permission_classes = [HasMembership, CanUseGradebook]
    serializer_class = serializers.HistoryEntrySerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("column", int, required=True),
            OpenApiParameter("student", int, required=True),
        ],
        responses=serializers.HistoryEntrySerializer(many=True),
    )
    def get(self, request, pk):
        gradebook = self.get_gradebook()
        column, student = int_param(request, "column"), int_param(request, "student")
        if not gradebook.gradebookcolumn_set.filter(pk=column).exists():
            raise NotFound
        entries = (
            ScoreEntry.objects.filter(column_id=column, student_id=student)
            .select_related("entered_by__account")
            .order_by("entered_at", "id")
        )
        data = [
            {
                "id": entry.pk,
                "value": entry.value,
                "result": entry.result,
                "entered_by_name": entry.entered_by.account.display_name,
                "entered_at": entry.entered_at,
            }
            for entry in entries
        ]
        return Response(serializers.HistoryEntrySerializer(data, many=True).data)


class MyGradebooksView(GenericAPIView):
    """The signed-in teacher's teaching pairs of this school year with each term's gradebook (or
    none yet): the teacher home's board and the `/gradebook` picker. Empty for anyone who teaches
    nothing in a Lower or Upper Secondary class."""

    permission_classes = [HasMembership, Can("scores.view")]
    serializer_class = serializers.MyPairSerializer

    @extend_schema(responses=serializers.MyPairSerializer(many=True))
    def get(self, request):
        pairs = Actor.of(request).teaching_pairs
        today = timezone.localdate()
        classes = SchoolClass.objects.select_related("school_year", "grade__level").filter(
            pk__in={klass for _, klass in pairs},
            school_year__starts_on__lte=today,
            school_year__ends_on__gte=today,
            grade__level__kind__in=SECONDARY,
        )
        subjects = Subject.objects.in_bulk({subject for subject, _ in pairs})
        terms = {}
        for term in Term.objects.filter(school_year__in=[k.school_year_id for k in classes]):
            terms.setdefault(term.school_year_id, []).append(term)
        books = {
            (book.subject_id, book.school_class_id, book.term_id): book
            for book in Gradebook.objects.filter(school_class__in=classes)
        }
        data = [
            {
                "subject": subject.pk,
                "subject_name": subject.name,
                "school_class": klass.pk,
                "class_name": klass.name,
                "terms": [
                    {
                        "term": term.pk,
                        "term_name": term.name,
                        "gradebook": book.pk if book else None,
                        "status": book.status if book else None,
                    }
                    for term in sorted(
                        terms.get(klass.school_year_id, []), key=lambda t: t.starts_on
                    )
                    for book in [books.get((subject.pk, klass.pk, term.pk))]
                ],
            }
            for klass in sorted(classes, key=lambda k: k.name)
            for subject in sorted(
                (subjects[s] for s, c in pairs if c == klass.pk), key=lambda s: s.name
            )
        ]
        return Response(serializers.MyPairSerializer(data, many=True).data)
