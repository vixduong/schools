from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import F, Func, Q

from schools.models import TenantModel, _daterange


class BellTimes(Func):
    """tsrange(day + starts_at, day + ends_at): a bell period's times on a fixed day."""

    template = "tsrange('2000-01-01'::date + %(expressions)s)"
    arg_joiner = ", '2000-01-01'::date + "
    output_field = DateTimeRangeField()

    def __init__(self):
        super().__init__(F("starts_at"), F("ends_at"))

    def deconstruct(self):
        return "timetable.models.BellTimes", (), {}


class BellPeriod(TenantModel):
    """One numbered period of a session in a school year, with its clock times. The times are a
    schedule, not a dated fact, so they may be edited; a period that entries use is never deleted
    (the composite foreign key from TimetableEntry refuses it, and the API has no DELETE)."""

    class Session(models.TextChoices):
        MORNING = "morning"
        AFTERNOON = "afternoon"

    school_year = models.ForeignKey(
        "schools.SchoolYear", on_delete=models.PROTECT, db_constraint=False
    )
    session = models.CharField(max_length=10, choices=Session)
    number = models.PositiveSmallIntegerField()
    starts_at = models.TimeField()
    ends_at = models.TimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "school_year", "session", "number"], name="bellperiod_slot_key"
            ),
            models.UniqueConstraint(fields=["school", "id"], name="bellperiod_school_id_key"),
            # Target of TimetableEntry's (school, school_year, bell_period) foreign key.
            models.UniqueConstraint(
                fields=["school", "school_year", "id"], name="bellperiod_school_year_id_key"
            ),
            models.CheckConstraint(
                condition=Q(starts_at__lt=models.F("ends_at")), name="bellperiod_ends_after_start"
            ),
            models.CheckConstraint(
                condition=Q(number__gte=1, number__lte=5), name="bellperiod_number_in_1_to_5"
            ),
            # Breaks are the gaps between periods, so two periods of a year never overlap
            # (half-open: one may start the minute another ends). Times sit on a fixed day.
            ExclusionConstraint(
                name="bellperiod_no_overlap",
                expressions=[
                    ("school", RangeOperators.EQUAL),
                    ("school_year", RangeOperators.EQUAL),
                    (BellTimes(), RangeOperators.OVERLAPS),
                ],
            ),
            models.CheckConstraint(
                condition=Q(session__in=["morning", "afternoon"]),
                name="bellperiod_session_is_known",
            ),
        ]

    def __str__(self):
        return f"{self.session} {self.number}"


class TimetableEntry(TenantModel):
    """A class's subject, teacher and room in one bell period of a weekday, for a period of dates
    [valid_from, valid_to] (open-ended while valid_to is null, in force only inside its school
    year). A new timetable replaces the old from a day by ending the old rows the day before
    (`classes/{id}/timetable/`). The class, the teacher and the room each have at most one entry
    in a slot at a time (exclusion constraints; a NULL room never clashes). The School year of the
    class and of the bell period is the entry's `school_year` (composite foreign keys); the
    triggers `timetableentry_inside_school_year`, `timetableentry_teacher_teaches` and
    `school_year_keeps_its_timetable` hold the cross-table rules, in the migrations."""

    school_year = models.ForeignKey(
        "schools.SchoolYear", on_delete=models.PROTECT, db_constraint=False
    )
    school_class = models.ForeignKey(
        "schools.SchoolClass", on_delete=models.PROTECT, db_constraint=False
    )
    weekday = models.PositiveSmallIntegerField()  # ISO: 1 = Monday ... 7 = Sunday
    bell_period = models.ForeignKey(BellPeriod, on_delete=models.PROTECT, db_constraint=False)
    subject = models.ForeignKey("schools.Subject", on_delete=models.PROTECT, db_constraint=False)
    teacher = models.ForeignKey(
        "accounts.Membership", on_delete=models.PROTECT, db_constraint=False, related_name="+"
    )
    room = models.ForeignKey(
        "schools.Room", null=True, blank=True, on_delete=models.PROTECT, db_constraint=False
    )
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="timetableentry_school_id_key"),
            models.CheckConstraint(
                condition=Q(weekday__gte=1, weekday__lte=7), name="timetableentry_weekday_in_1_to_7"
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=models.F("valid_from")),
                name="timetableentry_valid_to_after_valid_from",
            ),
            *(
                ExclusionConstraint(
                    name=f"timetableentry_{name}_clash",
                    expressions=[
                        ("school", RangeOperators.EQUAL),
                        (column, RangeOperators.EQUAL),
                        ("weekday", RangeOperators.EQUAL),
                        ("bell_period", RangeOperators.EQUAL),
                        (_daterange("valid_from", "valid_to"), RangeOperators.OVERLAPS),
                    ],
                )
                for name, column in (
                    ("class", "school_class"),
                    ("teacher", "teacher"),
                    ("room", "room"),
                )
            ),
            # "Inside its school year" and "the teacher teaches it" are triggers, in the migration.
        ]

    def __str__(self):
        return f"{self.school_class_id} day {self.weekday} period {self.bell_period_id}"
