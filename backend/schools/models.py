from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.db import models
from django.db.models import Func, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone


class TenantModel(models.Model):
    """A School-owned table (RLS). Each concrete model also declares a `(school, id)` unique
    constraint so other tenant tables can reference it with a composite same-School FK; the
    migration adds those FKs (`composite_fk`) and the model fields use `db_constraint=False`."""

    school = models.ForeignKey("tenancy.School", on_delete=models.CASCADE)

    class Meta:
        abstract = True


class SchoolYear(TenantModel):
    name = models.CharField(max_length=20)  # "2026-2027"
    starts_on = models.DateField()
    ends_on = models.DateField()  # inclusive

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="schoolyear_name_key"),
            models.UniqueConstraint(fields=["school", "id"], name="schoolyear_school_id_key"),
            models.CheckConstraint(
                condition=Q(ends_on__gt=models.F("starts_on")), name="schoolyear_ends_after_start"
            ),
            # No overlapping years per School (needs btree_gist, created in the migration).
            ExclusionConstraint(
                name="schoolyear_no_overlap",
                expressions=[
                    ("school", RangeOperators.EQUAL),
                    (
                        Func(
                            "starts_on",
                            "ends_on",
                            Value("[]"),
                            function="daterange",
                            output_field=DateRangeField(),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
            ),
        ]

    def __str__(self):
        return self.name


class Term(TenantModel):
    school_year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, db_constraint=False)
    name = models.CharField(max_length=50)  # "HK I"
    starts_on = models.DateField()
    ends_on = models.DateField()  # inclusive

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="term_school_id_key"),
            # Target of Gradebook's (school, school_year, term) foreign key.
            models.UniqueConstraint(
                fields=["school", "school_year", "id"], name="term_school_year_id_key"
            ),
            models.CheckConstraint(
                condition=Q(ends_on__gt=models.F("starts_on")), name="term_ends_after_start"
            ),
            # "Inside its year" is a trigger (term_inside_school_year), in the migration.
        ]

    def __str__(self):
        return self.name


class Level(TenantModel):
    class Kind(models.TextChoices):
        PRESCHOOL = "preschool"
        PRIMARY = "primary"
        LOWER_SECONDARY = "lower_secondary"
        UPPER_SECONDARY = "upper_secondary"

    kind = models.CharField(max_length=20, choices=Kind)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "kind"], name="level_kind_key"),
            models.UniqueConstraint(fields=["school", "id"], name="level_school_id_key"),
        ]

    def __str__(self):
        return self.kind


class Grade(TenantModel):
    level = models.ForeignKey(Level, on_delete=models.PROTECT, db_constraint=False)
    number = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "number"], name="grade_number_key"),
            models.UniqueConstraint(fields=["school", "id"], name="grade_school_id_key"),
            # Which numbers fit which Level is a trigger (grade_number_fits_level).
            models.CheckConstraint(
                condition=Q(number__gte=1, number__lte=12), name="grade_number_in_1_to_12"
            ),
        ]

    def __str__(self):
        return f"Grade {self.number}"


class SubjectGroup(TenantModel):
    name = models.CharField(max_length=100)  # "Toán"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="subjectgroup_school_id_key"),
        ]

    def __str__(self):
        return self.name


class Subject(TenantModel):
    class Assessment(models.TextChoices):
        SCORED = "scored"
        COMMENT_ONLY = "comment_only"

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30)
    subject_group = models.ForeignKey(
        SubjectGroup, null=True, blank=True, on_delete=models.PROTECT, db_constraint=False
    )
    ministry_code = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001
    assessment = models.CharField(max_length=20, choices=Assessment, default=Assessment.SCORED)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "code"], name="subject_code_key"),
            models.UniqueConstraint(fields=["school", "id"], name="subject_school_id_key"),
        ]

    def __str__(self):
        return self.name


class SubjectLoad(TenantModel):
    """The periods a Grade has a subject per school year. It decides how many regular columns a
    gradebook of that year, Grade and subject gets, so it is frozen once such a gradebook exists
    (trigger `subjectload_frozen_by_gradebooks`, in the grades migration). The app role changes
    `periods_per_year` only and never deletes one."""

    school_year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, db_constraint=False)
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, db_constraint=False)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, db_constraint=False)
    periods_per_year = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "school_year", "grade", "subject"],
                name="subjectload_once_per_year_grade_subject",
            ),
            models.CheckConstraint(
                condition=Q(periods_per_year__gte=1, periods_per_year__lte=400),
                name="subjectload_periods_in_1_to_400",
            ),
        ]

    def __str__(self):
        return f"{self.grade_id}/{self.subject_id}: {self.periods_per_year}"


class Room(TenantModel):
    name = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="room_school_id_key"),
        ]

    def __str__(self):
        return self.name


class SchoolClass(TenantModel):
    school_year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, db_constraint=False)
    grade = models.ForeignKey(Grade, on_delete=models.PROTECT, db_constraint=False)
    name = models.CharField(max_length=50)  # "7A"
    room = models.ForeignKey(
        Room, null=True, blank=True, on_delete=models.PROTECT, db_constraint=False
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "school_year", "name"], name="schoolclass_name_per_year_key"
            ),
            models.UniqueConstraint(fields=["school", "id"], name="schoolclass_school_id_key"),
            # Target of RoleAssignment's (school, school_year, school_class) foreign key.
            models.UniqueConstraint(
                fields=["school", "school_year", "id"], name="schoolclass_school_year_id_key"
            ),
        ]

    def __str__(self):
        return self.name


def _daterange(start: str, end: str) -> Func:
    return Func(start, end, Value("[]"), function="daterange", output_field=DateRangeField())


class StudentQuerySet(models.QuerySet):
    def with_status(self, on=None):
        """Annotates `current_status`: the status as of `on` (default today), for filtering."""
        on = on or timezone.localdate()
        latest = (
            StudentStatusEvent.objects.filter(student=OuterRef("pk"), on__lte=on)
            .order_by("-on", "-id")
            .values("status")[:1]
        )
        return self.annotate(
            current_status=Coalesce(Subquery(latest), Value(Student.Status.STUDYING))
        )


class Student(TenantModel):
    """A student of this School. `membership` (the student's sign-in) exists only for Lower and
    Upper Secondary students, so a trigger (student_membership_needs_secondary_level) requires an
    Enrollment in such a class first, and Enrollment refuses a lower-level class afterwards.
    There is no stored status: it is derived from the StudentStatusEvents as of a date
    (`status_as_of`, `with_status`), so a leave can be scheduled without changing today's status."""

    class Gender(models.TextChoices):
        MALE = "male"
        FEMALE = "female"

    class Status(models.TextChoices):
        STUDYING = "studying"
        TRANSFERRED_OUT = "transferred_out"
        DROPPED_OUT = "dropped_out"
        GRADUATED = "graduated"

    full_name = models.CharField(max_length=200)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=Gender)
    # NULL, not "", when unknown, so the per-School uniques never collide on blanks.
    ministry_student_id = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001
    national_id = models.CharField(max_length=20, null=True, blank=True)  # noqa: DJ001
    membership = models.ForeignKey(
        "accounts.Membership", null=True, blank=True, on_delete=models.PROTECT, db_constraint=False
    )

    objects = StudentQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="student_school_id_key"),
            models.UniqueConstraint(
                fields=["school", "ministry_student_id"], name="student_ministry_student_id_key"
            ),
            models.UniqueConstraint(
                fields=["school", "national_id"], name="student_national_id_key"
            ),
            models.UniqueConstraint(fields=["school", "membership"], name="student_membership_key"),
            models.CheckConstraint(
                condition=~Q(ministry_student_id="") & ~Q(national_id=""),
                name="student_ids_are_null_not_blank",
            ),
            models.CheckConstraint(
                condition=Q(national_id__isnull=True) | Q(national_id__regex=r"^[0-9]{12}$"),
                name="student_national_id_is_12_digits",
            ),
            # The secondary-level rule is a trigger, in the migration.
        ]

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        self.ministry_student_id = (self.ministry_student_id or "").strip() or None
        self.national_id = (self.national_id or "").strip() or None
        super().save(*args, **kwargs)


class StudentStatusEvent(TenantModel):
    """Append-only history of a student's status: the app role has SELECT and INSERT only. The
    status on a date is the latest event (by `on`, then id) with `on` up to that date; an event
    dated in the future is a scheduled change."""

    student = models.ForeignKey(Student, on_delete=models.PROTECT, db_constraint=False)
    status = models.CharField(max_length=20, choices=Student.Status)
    on = models.DateField()
    reason = models.CharField(max_length=500, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.Membership", on_delete=models.PROTECT, db_constraint=False, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "id"], name="studentstatusevent_school_id_key"
            )
        ]

    def __str__(self):
        return f"{self.student_id} {self.status} on {self.on}"


def status_as_of(events, on):
    """The status on `on` from a student's events (any iterable): the latest one up to that day,
    'studying' when there is none. Same rule as `StudentQuerySet.with_status`."""
    past = [e for e in events if e.on <= on]
    return max(past, key=lambda e: (e.on, e.id)).status if past else Student.Status.STUDYING


def scheduled_change(events, today):
    """`{"status", "on"}` of the next change of status after today, or None. A change cancelled
    by a later event of the same day is no change."""
    events = list(events)
    status = status_as_of(events, today)
    for day in sorted({e.on for e in events if e.on > today}):
        if (later := status_as_of(events, day)) != status:
            return {"status": later, "on": day}
    return None


class EnrollmentQuerySet(models.QuerySet):
    def in_force(self, on=None):
        """Periods containing `on` (default: today) and lying in a school year that contains it:
        an open period (no `valid_to`) is ongoing only until its year ends."""
        on = on or timezone.localdate()
        return self.filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=on),
            valid_from__lte=on,
            school_year__starts_on__lte=on,
            school_year__ends_on__gte=on,
        )


class Enrollment(TenantModel):
    """A student's place in one School and class for a period of one school year (GLOSSARY). A
    student moves class mid-year, or arrives or leaves, by ending one row and starting another, so
    the history stays. A period is [valid_from, valid_to] inside the school year (open-ended while
    ongoing, but in force only within its year; `school-years/{id}/close/` ends the open ones with
    `year_end`); periods of one student never overlap.
    The class must belong to the year: (school_id, school_year_id, school_class_id) references the
    class's (school_id, school_year_id, id). `valid_to` and `reason_ended` are set together."""

    class ReasonStarted(models.TextChoices):
        NEW_YEAR = "new_year"
        TRANSFER_IN = "transfer_in"
        CLASS_CHANGE = "class_change"
        RETURN = "return"

    class ReasonEnded(models.TextChoices):
        TRANSFER_OUT = "transfer_out"
        CLASS_CHANGE = "class_change"
        DROPPED_OUT = "dropped_out"
        GRADUATED = "graduated"
        YEAR_END = "year_end"

    student = models.ForeignKey(Student, on_delete=models.PROTECT, db_constraint=False)
    school_year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, db_constraint=False)
    school_class = models.ForeignKey(SchoolClass, on_delete=models.PROTECT, db_constraint=False)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    reason_started = models.CharField(max_length=20, choices=ReasonStarted)
    reason_ended = models.CharField(max_length=20, choices=ReasonEnded, null=True, blank=True)  # noqa: DJ001

    objects = EnrollmentQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="enrollment_school_id_key"),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=models.F("valid_from")),
                name="enrollment_valid_to_after_valid_from",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True, reason_ended__isnull=True)
                | Q(valid_to__isnull=False, reason_ended__isnull=False),
                name="enrollment_end_has_a_reason",
            ),
            ExclusionConstraint(
                name="enrollment_no_overlapping_periods",
                expressions=[
                    ("school", RangeOperators.EQUAL),
                    ("student", RangeOperators.EQUAL),
                    (_daterange("valid_from", "valid_to"), RangeOperators.OVERLAPS),
                ],
            ),
            # "Period inside its school year" is a trigger (enrollment_inside_school_year).
        ]

    def __str__(self):
        return f"{self.student_id} in {self.school_class_id} from {self.valid_from}"


class GuardianLink(TenantModel):
    """A Guardian's (Membership's) link to a student; the source of the Guardian's rights over
    that student. A period [valid_from, valid_to] (open-ended when valid_to is null); two periods
    of the same Membership and student never overlap. Ended with valid_to, never deleted."""

    class Relation(models.TextChoices):
        MOTHER = "mother"
        FATHER = "father"
        GRANDPARENT = "grandparent"
        OTHER = "other"

    membership = models.ForeignKey(
        "accounts.Membership",
        on_delete=models.PROTECT,
        db_constraint=False,
        related_name="guardian_links",
    )
    student = models.ForeignKey(Student, on_delete=models.PROTECT, db_constraint=False)
    relation = models.CharField(max_length=20, choices=Relation)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="guardianlink_school_id_key"),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=models.F("valid_from")),
                name="guardianlink_valid_to_after_valid_from",
            ),
            ExclusionConstraint(
                name="guardianlink_no_overlapping_periods",
                expressions=[
                    ("school", RangeOperators.EQUAL),
                    ("membership", RangeOperators.EQUAL),
                    ("student", RangeOperators.EQUAL),
                    (_daterange("valid_from", "valid_to"), RangeOperators.OVERLAPS),
                ],
            ),
        ]

    def __str__(self):
        return f"{self.membership_id} -> {self.student_id}"


class AssessmentProfileVersion(models.Model):
    """One dated edition of the assessment rules of a Level kind (ADR 0006). Global table: no
    `school_id`, no RLS, SELECT only for the app role (rows arrive by migration). A school year is
    assessed under the version in force for it. Periods of one `level_kind` never overlap;
    `effective_to` is inclusive, null while no later version exists.

    `rules` shape for Lower/Upper Secondary (Circular 22/2021), all keys required:

        {"schema": 1,
         "verified": "ocr",                  # how the values were read: re-check against the PDF
         "effective_from_assumed": true,     # the circular's own date was not in the research
         "scale": {"max": 10, "decimals": 1, "rounding": "half_up", "rounding_assumed": true},
         "subject_forms": ["scored", "comment_only"],
         "comment_results": ["Đạt", "Chưa đạt"],
         "regular_assessments": {            # per semester
             "comment_only": 2,
             "scored_by_periods_per_year": [{"up_to": 35, "count": 2},
                                            {"up_to": 70, "count": 3},
                                            {"up_to": null, "count": 4}]},   # null = no limit
         "periodic": {"mid_term": 1, "end_term": 1},
         "weights": {"regular": 1, "mid_term": 2, "end_term": 3},
         "semester_average": "<formula text>",
         "year_average": {"weights": {"semester_1": 1, "semester_2": 2}, "formula": "<text>"},
         "year_average_uses_rounded_semester_averages": true,
         "rounding": "ROUND_HALF_UP",        # a decimal.Decimal rounding mode
         "not_modelled": ["<what this shape does not capture yet>"],
         "learning_ratings": [               # best first; the last one has "otherwise": true
             {"name": "Tốt",
              "comment_subjects_not_passed_max": 0,
              "every_scored_at_least": 6.5,  # null = no such condition
              "scored_at_least": {"subjects": 6, "score": 8.0},
              "no_scored_below": null},
             ...],
         "rating_adjustment": "<text>"}

    Other Level kinds define their own shape under their own `schema` number."""

    level_kind = models.CharField(max_length=20, choices=Level.Kind)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=200)  # "Circular 22/2021/TT-BGDĐT"
    rules = models.JSONField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="assessmentprofileversion_ends_after_start",
            ),
            ExclusionConstraint(
                name="assessmentprofileversion_no_overlap",
                expressions=[
                    ("level_kind", RangeOperators.EQUAL),
                    (_daterange("effective_from", "effective_to"), RangeOperators.OVERLAPS),
                ],
            ),
        ]

    def __str__(self):
        return f"{self.level_kind} from {self.effective_from}"


class ImportBatch(TenantModel):
    """One uploaded Excel file (docs/slices/slice-6.md, 6b): its parsed rows and the per-row
    outcome of the preview, kept so `commit` applies exactly what was previewed. The file itself
    is not kept. A batch commits once, within 24 hours of its upload."""

    class Kind(models.TextChoices):
        STAFF = "staff"
        STUDENTS = "students"
        GUARDIANS = "guardians"

    class Status(models.TextChoices):
        PREVIEWED = "previewed"
        COMMITTED = "committed"

    kind = models.CharField(max_length=20, choices=Kind)
    # The year whose classes the rows name (staff and students); NULL for guardians.
    school_year = models.ForeignKey(
        SchoolYear, null=True, blank=True, on_delete=models.PROTECT, db_constraint=False
    )
    file_sha256 = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(
        "accounts.Membership", on_delete=models.PROTECT, db_constraint=False, related_name="+"
    )
    status = models.CharField(max_length=20, choices=Status, default=Status.PREVIEWED)
    created_at = models.DateTimeField(default=timezone.now)
    rows = models.JSONField()  # [{"row": n, <field>: <cleaned value>, ...}]
    results = models.JSONField()  # [{"row": n, "result": "created" | "updated" | ...}]
    errors = models.JSONField()  # [{"row": n, "column": <header> | null, "code": ...}]

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="importbatch_school_id_key"),
        ]

    def __str__(self):
        return f"{self.kind} import {self.pk}"
