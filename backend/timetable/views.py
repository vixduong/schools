from collections import defaultdict
from datetime import timedelta
from functools import reduce
from operator import or_

from django.db import IntegrityError, models, transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.fields import DateField
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from accounts.permissions import HasMembership
from permissions.actor import Actor, TeachingPair
from permissions.drf import Can, CanPermission
from permissions.engine import can, visible_students
from schools.models import Enrollment, SchoolClass, Student
from schools.views import SetupViewSet, database_rules

from . import serializers
from .models import AttendanceMark, BellPeriod, LeaveRequest, TimetableEntry

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
    that date (and anyone marked in it who has left the class since) with each student's mark; PUT
    the whole sheet, in one transaction. A date the entry is not held on is a 404; a PUT for a day
    after today is a 400."""

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
        """(id, name, enrolled) by name: the students enrolled in the entry's class on the date,
        and those already marked in this period that day who have left the class since (a move or
        a leave, even backdated), who stay on the sheet so their mark can be corrected."""
        enrolled = set(
            Enrollment.objects.in_force(on)
            .filter(school_class=entry.school_class)
            .values_list("student_id", flat=True)
        )
        marked = AttendanceMark.objects.filter(entry=entry, on=on).values("student_id")
        students = Student.objects.filter(models.Q(pk__in=enrolled) | models.Q(pk__in=marked))
        return [
            (pk, name, pk in enrolled)
            for pk, name in students.order_by("full_name", "id").values_list("id", "full_name")
        ]

    def sheet(self, request, entry, on):
        marks = {m.student_id: m for m in AttendanceMark.objects.filter(entry=entry, on=on)}
        roster = self.roster(entry, on)
        # The approved request covering the day; the screen defaults an untaken sheet from it and
        # nothing here writes a mark.
        leaves = {
            leave.student_id: leave
            for leave in LeaveRequest.objects.filter(
                student_id__in=[pk for pk, _, _ in roster],
                status=LeaveRequest.Status.APPROVED,
                from_on__lte=on,
                to_on__gte=on,
            )
        }
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
                {"id": pk, "name": name, "mark": marks.get(pk), "leave": leaves.get(pk)}
                for pk, name, _ in roster
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
        roster = self.roster(entry, on)
        enrolled = {pk for pk, _, here in roster if here}
        allowed = {pk for pk, _, _ in roster}  # also the marked ones, who need not be listed
        # An id listed twice counts as extra, so each student has exactly one mark.
        extra = sorted({pk for pk in given if pk not in allowed or given.count(pk) > 1})
        missing = sorted(enrolled - set(given))
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


def held_periods(klass, first, last, taken):
    """The periods the class held from `first` to `last`, by day and bell period: the entries in
    force on each day (its weekday, dates and school year), flagged by whether (entry, day) is in
    `taken`."""
    entries = (
        TimetableEntry.objects.filter(
            models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=first),
            school_class=klass,
            valid_from__lte=last,
        )
        .select_related("bell_period", "subject", "school_year")
        .order_by(*MORNING_FIRST)
    )
    days = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    return [
        {
            "on": day,
            "session": e.bell_period.session,
            "number": e.bell_period.number,
            "subject_name": e.subject.name,
            "taken": (e.pk, day) in taken,
        }
        for day in days
        for e in entries
        if e.weekday == day.isoweekday()
        and e.valid_from <= day
        and (e.valid_to is None or day <= e.valid_to)
        and e.school_year.starts_on <= day <= e.school_year.ends_on
    ]


class ClassAttendanceView(GenericAPIView):
    """The class's absences and late arrivals from `?from=` to `?to=` (at most 31 days), for the
    homeroom teacher and the principal board: every student enrolled in the class during the range
    or marked in its periods (so one without an absence is still listed, and one who left after a
    mark stays), each with their late or absent marks, taken in this class's periods, by day and
    bell period. `periods` are the periods the class held in the range up to today, each flagged
    `taken`, so "all present" reads apart from "not taken"."""

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
        in_class = AttendanceMark.objects.filter(entry__school_class=klass, on__range=(first, last))
        students = {
            pk: {"id": pk, "name": name, "marks": []}
            for pk, name in Student.objects.filter(
                models.Q(pk__in=enrollments.values("student_id"))
                | models.Q(pk__in=in_class.values("student_id"))
            )
            .order_by("full_name", "id")
            .values_list("id", "full_name")
        }
        marks = (
            in_class.exclude(status=AttendanceMark.Status.PRESENT)
            .select_related("entry__bell_period", "entry__subject")
            .order_by("on", *MORNING_FIRST_OF_ENTRY)
        )
        for mark in marks:
            period = mark.entry.bell_period
            students[mark.student_id]["marks"].append(
                {
                    "on": mark.on,
                    "session": period.session,
                    "number": period.number,
                    "subject_name": mark.entry.subject.name,
                    "status": mark.status,
                }
            )
        taken = set(in_class.values_list("entry_id", "on").distinct())
        periods = held_periods(klass, first, min(last, timezone.localdate()), taken)
        return Response(
            serializers.OverviewSerializer(
                {"class_name": klass.name, "students": list(students.values()), "periods": periods}
            ).data
        )


def leave_student_in_body(request, view):
    """The Student a send names (one of another School is not found: RLS), kept on the view."""
    try:
        pk = int(request.data["student"])
    except (KeyError, TypeError, ValueError):
        raise ValidationError({"student": ["required"]}) from None
    view.student = Student.objects.filter(pk=pk).first()
    if view.student is None:
        raise PermissionDenied
    return view.student


class CanUseLeaveRequests(CanPermission):
    """Any member may ask for the list and the children: each answers only what `visible_students`
    reaches for the member, which for most is nothing. Sending is `leave_request.send` on the
    student the body names."""

    action = "leave_request.send"

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return getattr(request, "membership", None) is not None
        return Can(self.action, leave_student_in_body)().has_permission(request, view)


def with_classes(leaves):
    """The requests as a list, each with `class_name`: the student's class on its first day."""
    leaves = list(leaves)
    periods = defaultdict(list)
    for student, start, end, name in Enrollment.objects.filter(
        student_id__in={leave.student_id for leave in leaves}
    ).values_list("student_id", "valid_from", "valid_to", "school_class__name"):
        periods[student].append((start, end, name))
    for leave in leaves:
        leave.class_name = next(
            (
                name
                for start, end, name in periods[leave.student_id]
                if start <= leave.from_on and (end is None or end >= leave.from_on)
            ),
            None,
        )
    return leaves


def leave_requests():
    return LeaveRequest.objects.select_related("student", "sent_by__account", "decided_by__account")


class LeaveRequestsView(GenericAPIView):
    """Leave requests. GET: those the member may see, newest first: a Guardian the ones they sent
    for a linked student, a homeroom teacher those of their class's students, the principal board
    all (`visible_students` with `leave_request.send` and `.approve`); `?sent=1` keeps the ones the
    member sent, `?to_decide=1` those they decide, not their own. POST: a Guardian sends one
    for a linked student, from today, for a student enrolled on the first day; it waits."""

    permission_classes = [HasMembership, CanUseLeaveRequests]
    serializer_class = serializers.SendLeaveRequestSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str, description="Only this status"),
            OpenApiParameter("student", int, description="Only this student"),
            OpenApiParameter("sent", int, description="1: only the requests the member sent"),
            OpenApiParameter(
                "to_decide",
                int,
                description="1: only the requests of students the member decides for, "
                "without the ones the member sent",
            ),
        ],
        responses=serializers.LeaveRequestSerializer(many=True),
    )
    def get(self, request):
        actor = Actor.of(request)
        sent = models.Q(
            sent_by=request.membership,
            student__in=visible_students(actor, "leave_request.send"),
        )
        decidable = models.Q(student__in=visible_students(actor, "leave_request.approve"))
        # A person who is a Guardian and a teacher reads two lists: what they sent, and what
        # waits for them (nobody decides their own request).
        asked = [
            q
            for name, q in (
                ("sent", sent),
                ("to_decide", decidable & ~models.Q(sent_by=request.membership)),
            )
            if request.query_params.get(name) == "1"
        ]
        leaves = leave_requests().filter(reduce(or_, asked) if asked else sent | decidable)
        wanted = request.query_params.get("status")
        if wanted is not None:
            if wanted not in LeaveRequest.Status.values:
                raise ValidationError({"status": ["unknown"]})
            leaves = leaves.filter(status=wanted)
        student = request.query_params.get("student")
        if student is not None:
            leaves = leaves.filter(student_id=student) if student.isdigit() else leaves.none()
        body = with_classes(leaves.order_by("-sent_at", "-id"))
        return Response(serializers.LeaveRequestSerializer(body, many=True).data)

    @extend_schema(responses={201: serializers.LeaveRequestSerializer})
    def post(self, request):
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        days = body.validated_data
        if not Enrollment.objects.in_force(days["from_on"]).filter(student=self.student).exists():
            raise ValidationError({"from_on": ["not_enrolled"]})
        with database_rules():
            leave = LeaveRequest.objects.create(
                school=request.school,
                student=self.student,
                sent_by=request.membership,
                from_on=days["from_on"],
                to_on=days["to_on"],
                reason=days["reason"],
            )
        (sent,) = with_classes(leave_requests().filter(pk=leave.pk))
        return Response(
            serializers.LeaveRequestSerializer(sent).data, status=status.HTTP_201_CREATED
        )


class LeaveChildrenView(GenericAPIView):
    """The students the member may send a leave request for, by name, each with their class today:
    the Guardian's child picker."""

    permission_classes = [HasMembership, CanUseLeaveRequests]
    serializer_class = serializers.LeaveChildSerializer

    @extend_schema(responses=serializers.LeaveChildSerializer(many=True))
    def get(self, request):
        students = list(
            visible_students(Actor.of(request), "leave_request.send").order_by("full_name", "id")
        )
        classes = dict(
            Enrollment.objects.in_force()
            .filter(student_id__in=[s.pk for s in students])
            .values_list("student_id", "school_class__name")
        )
        body = [
            {"id": s.pk, "name": s.full_name, "class_name": classes.get(s.pk)} for s in students
        ]
        return Response(serializers.LeaveChildSerializer(body, many=True).data)


class LeaveRequestAction(GenericAPIView):
    """Base of approve, decline and cancel: the request in the URL, changed from waiting under a
    row lock (the trigger `leaverequest_lifecycle` is the net under it). The permission target is
    the request's student."""

    outcome: str

    def get_leave(self):
        if not hasattr(self, "leave"):
            self.leave = (
                LeaveRequest.objects.select_related("student").filter(pk=self.kwargs["pk"]).first()
            )
        if self.leave is None:
            raise NotFound
        return self.leave

    def decide(self, request, pk, comment=""):
        with database_rules():
            leave = LeaveRequest.objects.select_for_update(no_key=True).get(pk=pk)
            if leave.status != LeaveRequest.Status.WAITING:
                raise ValidationError({"status": ["not_waiting"]})
            leave.status = self.outcome
            if self.outcome != LeaveRequest.Status.CANCELLED:
                leave.decided_by, leave.decided_at = request.membership, timezone.now()
                leave.decision_comment = comment
            leave.save(update_fields=["status", "decided_by", "decided_at", "decision_comment"])
        (changed,) = with_classes(leave_requests().filter(pk=pk))
        return Response(serializers.LeaveRequestSerializer(changed).data)


def leave_student(request, view):
    return view.get_leave().student


class LeaveRequestDecideView(LeaveRequestAction):
    """Approve (the comment is optional) or decline (the comment says why) a waiting request:
    `leave_request.approve` on its student, as of today. Nobody decides a request they sent
    themselves (400 `own_request`), even when they are also the homeroom teacher."""

    permission_classes = [HasMembership, Can("leave_request.approve", leave_student)]
    serializer_class = serializers.DecideLeaveRequestSerializer

    @extend_schema(responses=serializers.LeaveRequestSerializer)
    def post(self, request, pk):
        body = self.get_serializer(data=request.data)
        body.is_valid(raise_exception=True)
        if self.get_leave().sent_by_id == request.membership.pk:
            raise ValidationError({"status": ["own_request"]})
        return self.decide(request, pk, body.validated_data["comment"])


class LeaveRequestApproveView(LeaveRequestDecideView):
    outcome = LeaveRequest.Status.APPROVED


class LeaveRequestDeclineView(LeaveRequestDecideView):
    outcome = LeaveRequest.Status.DECLINED
    serializer_class = serializers.DeclineLeaveRequestSerializer


class LeaveRequestCancelView(LeaveRequestAction):
    """Cancel a waiting request: only its sender, who still holds `leave_request.send` on the
    student."""

    outcome = LeaveRequest.Status.CANCELLED
    permission_classes = [HasMembership, Can("leave_request.send", leave_student)]
    serializer_class = serializers.DecideLeaveRequestSerializer

    @extend_schema(request=None, responses=serializers.LeaveRequestSerializer)
    def post(self, request, pk):
        if self.get_leave().sent_by_id != request.membership.pk:
            raise PermissionDenied
        return self.decide(request, pk)
