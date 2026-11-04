from datetime import timedelta

from django.db import IntegrityError, models, transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.fields import DateField
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response

from accounts.permissions import HasMembership
from permissions.actor import Actor
from permissions.drf import CanPermission
from permissions.engine import can
from schools.models import SchoolClass
from schools.views import SetupViewSet, database_rules

from . import serializers
from .models import BellPeriod, TimetableEntry

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


ON = OpenApiParameter("on", str, description="A date (YYYY-MM-DD); default today")


def in_force(entries, on):
    return entries.filter(
        models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=on), valid_from__lte=on
    )


# The morning's periods come before the afternoon's ("afternoon" sorts first alphabetically).
MORNING_FIRST = (
    models.Case(models.When(bell_period__session="morning", then=0), default=1),
    "bell_period__number",
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
        SchoolClass.objects.select_for_update().get(pk=klass.pk)
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
        entries = in_force(
            TimetableEntry.objects.filter(teacher=request.membership, weekday=on.isoweekday()), on
        ).select_related("bell_period", "school_class", "subject", "room")
        entries = entries.order_by(*MORNING_FIRST)
        return Response(serializers.MyPeriodSerializer(entries, many=True).data)
