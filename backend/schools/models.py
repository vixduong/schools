from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.db import models
from django.db.models import Func, Q, Value


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
        ]

    def __str__(self):
        return self.name
