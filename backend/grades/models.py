from django.db import models
from django.db.models import Func, Q
from django.utils import timezone

from schools.models import AssessmentProfileVersion, TenantModel


class Gradebook(TenantModel):
    """One subject's scores for one class in one term (Circular 22/2021, Lower and Upper
    Secondary). Opened once per (term, subject, class) with its columns, under the assessment
    profile version in force on the school year's first day; nothing but `status` changes
    afterwards (trigger `gradebook_only_status_changes`). Slice 4 leaves every gradebook `draft`.
    The term and the class belong to `school_year` (composite foreign keys); the class's Level is
    Lower or Upper Secondary (trigger `gradebook_secondary_level`). Opening is audited."""

    class Status(models.TextChoices):
        DRAFT = "draft"

    school_year = models.ForeignKey(
        "schools.SchoolYear", on_delete=models.PROTECT, db_constraint=False
    )
    term = models.ForeignKey("schools.Term", on_delete=models.PROTECT, db_constraint=False)
    subject = models.ForeignKey("schools.Subject", on_delete=models.PROTECT, db_constraint=False)
    school_class = models.ForeignKey(
        "schools.SchoolClass", on_delete=models.PROTECT, db_constraint=False
    )
    profile_version = models.ForeignKey(AssessmentProfileVersion, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status, default=Status.DRAFT)
    opened_by = models.ForeignKey(
        "accounts.Membership", on_delete=models.PROTECT, db_constraint=False, related_name="+"
    )
    # now(), the database's transaction start (Django's `Now` is the statement's time): a column
    # may be added only in the transaction that opened its gradebook
    # (`gradebookcolumn_only_at_opening`).
    opened_at = models.DateTimeField(
        db_default=Func(function="now", output_field=models.DateTimeField())
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="gradebook_school_id_key"),
            models.UniqueConstraint(
                fields=["school", "term", "subject", "school_class"],
                name="gradebook_once_per_term_subject_class",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["draft"]), name="gradebook_status_is_known"
            ),
        ]

    def __str__(self):
        return f"{self.subject_id}/{self.school_class_id}/{self.term_id}"


class GradebookColumn(TenantModel):
    """A column of a gradebook: regular assessments 1..n, then the mid-term and end-term tests.
    Created with the gradebook and never added or removed (trigger
    `gradebookcolumn_only_at_opening`, no DELETE grant). The subject teacher releases a column
    once (`released_at`/`released_by`, trigger `gradebookcolumn_release_once`); the release is
    audited."""

    class Kind(models.TextChoices):
        REGULAR = "regular"
        MID_TERM = "mid_term"
        END_TERM = "end_term"

    gradebook = models.ForeignKey(Gradebook, on_delete=models.PROTECT, db_constraint=False)
    kind = models.CharField(max_length=10, choices=Kind)
    index = models.PositiveSmallIntegerField()
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(
        "accounts.Membership",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_constraint=False,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="gradebookcolumn_school_id_key"),
            models.UniqueConstraint(
                fields=["school", "gradebook", "kind", "index"],
                name="gradebookcolumn_once_per_kind_index",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=["regular", "mid_term", "end_term"]),
                name="gradebookcolumn_kind_is_known",
            ),
            models.CheckConstraint(condition=Q(index__gte=1), name="gradebookcolumn_index_from_1"),
            models.CheckConstraint(
                condition=Q(released_at__isnull=True, released_by__isnull=True)
                | Q(released_at__isnull=False, released_by__isnull=False),
                name="gradebookcolumn_release_has_both",
            ),
        ]

    def __str__(self):
        return f"{self.kind} {self.index}"


class ScoreEntry(TenantModel):
    """One entry in a cell's history (a student in a column). Append-only: the app role has INSERT
    and SELECT only. The cell's current score is its latest entry (by `entered_at`, then id); an
    entry with neither `value` nor `result` clears the cell. A scored subject's entries carry
    `value`, a comment-only subject's `result` (trigger `scoreentry_fits_subject`); the student
    is in the class today (`scoreentry_student_in_class`) and the gradebook is a draft
    (`scoreentry_gradebook_open`). Not copied into the audit log: the School admin reads that
    log and sees no scores (docs/roles.md, Least data)."""

    class Result(models.TextChoices):
        PASS = "pass"
        FAIL = "fail"

    column = models.ForeignKey(GradebookColumn, on_delete=models.PROTECT, db_constraint=False)
    student = models.ForeignKey("schools.Student", on_delete=models.PROTECT, db_constraint=False)
    value = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    result = models.CharField(max_length=10, choices=Result, null=True, blank=True)  # noqa: DJ001
    entered_by = models.ForeignKey(
        "accounts.Membership", on_delete=models.PROTECT, db_constraint=False, related_name="+"
    )
    entered_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="scoreentry_school_id_key"),
            models.CheckConstraint(
                condition=Q(value__isnull=True) | Q(value__gte=0, value__lte=10),
                name="scoreentry_value_in_scale",
            ),
            models.CheckConstraint(
                condition=Q(result__isnull=True) | Q(result__in=["pass", "fail"]),
                name="scoreentry_result_is_known",
            ),
        ]
        indexes = [models.Index(fields=["school", "column", "student"], name="scoreentry_cell")]

    def __str__(self):
        return f"{self.column_id}/{self.student_id}: {self.value or self.result}"
