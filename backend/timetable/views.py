from datetime import timedelta

from django.db import IntegrityError, models, transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.fields import DateField
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from accounts.permissions import HasMembership
from permissions.actor import Actor, TeachingPair
from permissions.drf import Can, CanPermission
from permissions.engine import can
from schools.models import Enrollment, SchoolClass
from schools.views import SetupViewSet, database_rules

from . import serializers
from .models import AttendanceMark, BellPeriod, TimetableEntry

# The exclusion constraints, and the TimetableEntry column each one is about.
CLASH_COLUMNS = {
    "timetableentry_class_clash": "school_class",
    "timetableentry_teacher_clash": "teacher",
    "timetableentry_room_clash": "room",
}


class Clash(Exception):
    """A clash, with the 400 body that names the entry it hit (ids stay numbers, which
    `ValidationError` would turn into text). Raised inside `database_rules()`, so it undoes the
    whole replacement."""

    def __init__(self, body):
        self.body = body


ABSENCES = (AttendanceMark.Status.ABSENT_EXCUSED, AttendanceMark.Status.ABSENT_UNEXCUSED)
MAX_OVERVIEW_DAYS = 31

ON = OpenApiParameter("on", str, description="A date (YYYY-MM-DD); default today")


def in_force(entries, on):
    """Entries covering `on`; an open one only inside its school year."""
    return entries.filter(
        models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=on),
        valid_from__lte=on,
        school_year__starts_on__lte=on,
        school_year__ends_on__gte=on,
    )


# The morning's periods come before the afternoon's ("afternoon" sorts first alphabetically).
MORNING_FIRST = (
    models.Case(models.When(bell_period__session="morning", then=0), default=1),
    "bell_period__number",
)


MORNING_FIRST_OF_ENTRY = (
    models.Case(models.When(entry__bell_period__session="morning", then=0), default=1),
    "entry__bell_period__number",
)


def date_param(request):
    """`?on=<date>`, default today; a malformed date is a 400."""
    raw = request.query_params.get("on")
    if raw is None:
        return timezone.localdate()
    return DateField().run_validation(raw)


@extend_schema_view(
    list=extend_schema(
        parameters=[OpenApiParameter("school_year", int, description="Only this school year")]
    )
)
class BellPeriodViewSet(SetupViewSet):
    """The School's bell schedule (`school.configure`, read-only for the principal board). A
    period's times can change; its year, session and number cannot, and none is deleted."""

    queryset = BellPeriod.objects.order_by("school_year_id", "session", "number")
    serializer_class = serializers.BellPeriodSerializer

    def filter_queryset(self, queryset):
        if "school_year" in self.request.query_params:
            year = self.request.query_params["school_year"]
            queryset = queryset.filter(school_year_id=year) if year.isdigit() else queryset.none()
        return queryset


class CanReadClassTimetable(CanPermission):
    """`school.configure` (read for the principal board), or for a read `class_records.view` on
    the class in the URL, which is how a teacher reaches the class they teach."""

    action = "school.configure"
    read = True
    target_getter = staticmethod(lambda request, view: request.school)

    def has_permission(self, request, view):
        if super().has_permission(request, view):
            return True
        if request.method not in SAFE_METHODS or getattr(request, "membership", None) is None:
            return False
        klass = SchoolClass.objects.filter(pk=view.kwargs["pk"]).first()
        return klass is not None and can(Actor.of(request), "class_records.view", klass)


class ClassTimetableView(GenericAPIView):
    """A class's timetable. GET: its entries in force on `?on=` (default today). POST: replace it
    from a day, in one transaction (School admin only): entries not yet started by `valid_from`
    are deleted (they never governed a period), entries in force end the day before, and the new
    ones start on `valid_from`. A clash is a 400 naming the constraint and the entry it hit."""

    permission_classes = [HasMembership, CanReadClassTimetable]
    serializer_class = serializers.ReplaceTimetableSerializer

    def get_class(self, pk):
        klass = SchoolClass.objects.select_related("school_year").filter(pk=pk).first()
        if klass is None:
            raise NotFound
        return klass

    @extend_schema(parameters=[ON], responses=serializers.TimetableEntrySerializer(many=True))
    def get(self, request, pk):
        klass = self.get_class(pk)
        entries = in_force(TimetableEntry.objects.filter(school_class=klass), date_param(request))
        entries = entries.order_by("weekday", *MORNING_FIRST)
        return Response(serializers.TimetableEntrySerializer(entries, many=True).data)

    @extend_schema(responses={201: serializers.TimetableEntrySerializer(many=True)})
    def post(self, request, pk):
        klass = self.get_class(pk)
        context = {**self.get_serializer_context(), "school_class": klass}
        body = self.get_serializer(data=request.data, context=context)
        body.is_valid(raise_exception=True)
        start = body.validated_data["valid_from"]
        try:
            with database_rules():
                return self.replace(request, klass, start, body.validated_data["entries"])
        except Clash as clash:
            return Response(clash.body, status=status.HTTP_400_BAD_REQUEST)

    def replace(self, request, klass, start, slots):
        # Lock the class: two admins saving at once take turns.
        SchoolClass.objects.select_for_update(no_key=True).get(pk=klass.pk)
        mine = TimetableEntry.objects.filter(school_class=klass)
        mine.filter(valid_from__gte=start).delete()
        in_force(mine, start).update(valid_to=start - timedelta(days=1))
        created = [self.create_entry(request, klass, start, slot) for slot in slots]
        return Response(
            serializers.TimetableEntrySerializer(created, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def create_entry(request, klass, start, slot):
        entry = TimetableEntry(
            school=request.school,
            school_year=klass.school_year,
            school_class=klass,
            valid_from=start,
            **slot,
        )
        try:
            with transaction.atomic():  # a savepoint, so the clash can be looked up after it
                entry.save()
        except IntegrityError as error:
            name = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
            if name not in CLASH_COLUMNS:
                raise
            column = CLASH_COLUMNS[name]
            other = (
                TimetableEntry.objects.filter(
                    models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=start),
                    weekday=entry.weekday,
                    bell_period=entry.bell_period,
                    **{column: getattr(entry, column)},
                )
                .order_by("id")
                .first()
            )
            body = {"constraint": [name]}
            if other is not None:
                body["clash"] = {
                    "weekday": other.weekday,
                    "bell_period": other.bell_period_id,
                    "class": other.school_class_id,
                    "subject": other.subject_id,
                    "teacher": other.teacher_id,
                    "room": other.room_id,
                }
            raise Clash(body) from error
        return entry


class MyTimetableView(GenericAPIView):
    permission_classes = [HasMembership]
    serializer_class = serializers.MyPeriodSerializer

    @extend_schema(parameters=[ON], responses=serializers.MyPeriodSerializer(many=True))
    def get(self, request):
        """The signed-in member's own periods on the weekday of `?on=` (default today), by session
        and number. Empty for anyone who teaches nothing."""
        on = date_param(request)
        taken = models.Q(attendancemark__on=on)
        absent = models.Q(attendancemark__status__in=ABSENCES)
        entries = (
            in_force(
                TimetableEntry.objects.filter(teacher=request.membership, weekday=on.isoweekday()),
                on,
            )
            .select_related("bell_period", "school_class", "subject", "room")
            .annotate(
                marks=models.Count("attendancemark", filter=taken),
                absent=models.Count("attendancemark", filter=taken & absent),
                late=models.Count(
                    "attendancemark",
                    filter=taken & models.Q(attendancemark__status=AttendanceMark.Status.LATE),
                ),
            )
        )
        entries = entries.order_by(*MORNING_FIRST)
        return Response(serializers.MyPeriodSerializer(entries, many=True).data)


def sheet_pair(request, view):
    entry = view.get_entry()
    return TeachingPair(entry.subject, entry.school_class)


class CanUseSheet(CanPermission):
    """A period's sheet, by the subject x class of its entry: `attendance.view` to read it (the
    subject teacher, the homeroom teacher of the class, the principal board), `attendance.take`
    to save it (the subject teacher only)."""

    def has_permission(self, request, view):
        action = "attendance.view" if request.method in SAFE_METHODS else "attendance.take"
        return Can(action, sheet_pair)().has_permission(request, view)


class PeriodAttendanceView(GenericAPIView):
    """The attendance of one held period (a timetable entry on a date): GET the class list as of
    that date with each student's mark; PUT the whole sheet, in one transaction. A date the entry
    is not held on is a 404; a PUT for a day after today is a 400."""

    permission_classes = [HasMembership, CanUseSheet]
    serializer_class = serializers.SaveSheetSerializer

    def get_entry(self):
        if not hasattr(self, "entry"):
            self.entry = (
                TimetableEntry.objects.select_related(
                    "bell_period", "school_class", "subject", "room"
                )
                .filter(pk=self.kwargs["entry"])
                .first()
            )
        if self.entry is None:
            raise NotFound
        return self.entry

    def held_on(self):
        """The date in the URL, if the entry is held on it."""
        entry = self.get_entry()
        on = DateField().run_validation(self.kwargs["on"])
        held = in_force(TimetableEntry.objects.filter(pk=entry.pk, weekday=on.isoweekday()), on)
        if not held.exists():
            raise NotFound
        return on

    @staticmethod
    def roster(entry, on):
        """The students enrolled in the entry's class on the date, by name."""
        enrollments = Enrollment.objects.in_force(on).filter(school_class=entry.school_class)
        return list(
            enrollments.select_related("student")
            .order_by("student__full_name", "student_id")
            .values_list("student_id", "student__full_name")
        )

    def sheet(self, request, entry, on):
        marks = {m.student_id: m for m in AttendanceMark.objects.filter(entry=entry, on=on)}
        period = entry.bell_period
        return {
            "entry": entry.pk,
            "on": on,
            "session": period.session,
            "number": period.number,
            "starts_at": period.starts_at,
            "ends_at": period.ends_at,
            "school_class": entry.school_class_id,
            "class_name": entry.school_class.name,
            "subject": entry.subject_id,
            "subject_name": entry.subject.name,
            "room_name": entry.room.name if entry.room else None,
            "can_take": can(
                Actor.of(request),
                "attendance.take",
                TeachingPair(entry.subject, entry.school_class),
            ),
            "students": [
                {"id": pk, "name": name, "mark": marks.get(pk)}
                for pk, name in self.roster(entry, on)
            ],
        }

    @extend_schema(responses=serializers.SheetSerializer)
    def get(self, request, entry, on):
        entry = self.get_entry()
        on = self.held_on()
        return Response(serializers.SheetSerializer(self.sheet(request, entry, on)).data)

    @extend_schema(request=serializers.SaveSheetSerializer, responses=serializers.SheetSerializer)
    def put(self, request, entry, on):
        entry = self.get_entry()
        on = self.held_on()
        if on > timezone.localdate():
            raise ValidationError({"on": ["not_after_today"]})
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        given = [mark["student"] for mark in body.validated_data["marks"]]
        enrolled = [pk for pk, _ in self.roster(entry, on)]
        # An id listed twice counts as extra, so each student has exactly one mark.
        extra = sorted({pk for pk in given if pk not in enrolled or given.count(pk) > 1})
        missing = sorted(set(enrolled) - set(given))
        if extra or missing:
            # Not a ValidationError, which would turn the ids into text.
            return Response(
                {"students": {"missing": missing, "extra": extra}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with database_rules():
            self.save_marks(request, entry, on, body.validated_data["marks"])
        return Response(serializers.SheetSerializer(self.sheet(request, entry, on)).data)

    @staticmethod
    def save_marks(request, entry, on, given):
        # Two sheets of one period take turns (a concurrent insert would hit the unique key).
        TimetableEntry.objects.select_for_update(no_key=True).get(pk=entry.pk)
        existing = {m.student_id: m for m in AttendanceMark.objects.filter(entry=entry, on=on)}
        now = timezone.now()
        created, changed = [], []
        for mark in given:
            old = existing.get(mark["student"])
            if old is None:
                created.append(
                    AttendanceMark(
                        school=request.school,
                        entry=entry,
                        on=on,
                        student_id=mark["student"],
                        status=mark["status"],
                        note=mark["note"],
                        recorded_by=request.membership,
                        recorded_at=now,
                    )
                )
            elif (old.status, old.note) != (mark["status"], mark["note"]):  # no audit noise
                old.status, old.note = mark["status"], mark["note"]
                old.recorded_by, old.recorded_at = request.membership, now
                changed.append(old)
        AttendanceMark.objects.bulk_create(created)
        AttendanceMark.objects.bulk_update(
            changed, ["status", "note", "recorded_by", "recorded_at"]
        )


def class_to_view(request, view):
    klass = SchoolClass.objects.filter(pk=view.kwargs["pk"]).first()
    if klass is None:
        raise NotFound
    return klass


def date_range(request):
    """`?from=&to=`, both required, at most 31 days."""
    days = {}
    for name in ("from", "to"):
        raw = request.query_params.get(name)
        if raw is None:
            raise ValidationError({name: ["required"]})
        days[name] = DateField().run_validation(raw)
    if days["to"] < days["from"]:
        raise ValidationError({"to": ["before_from"]})
    if (days["to"] - days["from"]).days >= MAX_OVERVIEW_DAYS:
        raise ValidationError({"to": ["range_too_long"]})
    return days["from"], days["to"]


class ClassAttendanceView(GenericAPIView):
    """The class's absences and late arrivals from `?from=` to `?to=` (at most 31 days), for the
    homeroom teacher and the principal board: every student enrolled in the class during the range
    (so one without an absence is still listed), each with their late or absent marks, taken in
    this class's periods, by day and bell period."""

    permission_classes = [HasMembership, Can("attendance.view", class_to_view)]
    serializer_class = serializers.OverviewSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("from", str, required=True, description="First day (YYYY-MM-DD)"),
            OpenApiParameter("to", str, required=True, description="Last day, at most 31 days"),
        ],
        responses=serializers.OverviewSerializer,
    )
    def get(self, request, pk):
        first, last = date_range(request)
        klass = class_to_view(request, self)
        enrollments = Enrollment.objects.filter(
            models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=first),
            school_class=klass,
            valid_from__lte=last,
        )
        students = {
            pk: {"id": pk, "name": name, "marks": []}
            for pk, name in enrollments.order_by("student__full_name", "student_id")
            .values_list("student_id", "student__full_name")
            .distinct()
        }
        marks = (
            AttendanceMark.objects.filter(entry__school_class=klass, on__range=(first, last))
            .exclude(status=AttendanceMark.Status.PRESENT)
            .select_related("entry__bell_period", "entry__subject")
            .order_by("on", *MORNING_FIRST_OF_ENTRY)
        )
        for mark in marks:
            period = mark.entry.bell_period
            if mark.student_id in students:
                students[mark.student_id]["marks"].append(
                    {
                        "on": mark.on,
                        "session": period.session,
                        "number": period.number,
                        "subject_name": mark.entry.subject.name,
                        "status": mark.status,
                    }
                )
        return Response(
            serializers.OverviewSerializer(
                {"class_name": klass.name, "students": list(students.values())}
            ).data
        )
