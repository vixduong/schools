from django.db import models
from django.db.models import Q
from django.db.models.functions import Length, Now
from django.db.models.lookups import LessThanOrEqual

from schools.models import TenantModel

MAX_BODY_LENGTH = 5000


class Notice(TenantModel):
    """A title and a plain-text body from one sender to an audience (GLOSSARY "Notice"). Its
    recipients are the `NoticeRecipient` rows made when it is sent. Append-only: the app role may
    only INSERT and SELECT, so a sent notice is never edited or deleted. `title` is the mail
    subject, so it is one line (`notice_title_single_line`). The audit log keeps who sent which
    audience and when, never the title or the body (migration 0001)."""

    class Audience(models.TextChoices):
        SCHOOL = "school"
        GROUP = "group"
        HOMEROOM_GUARDIANS = "homeroom_guardians"
        CLASS = "class"

    sender = models.ForeignKey(
        "accounts.Membership", on_delete=models.PROTECT, db_constraint=False, related_name="+"
    )
    audience = models.CharField(max_length=30, choices=Audience)
    school_class = models.ForeignKey(
        "schools.SchoolClass", null=True, blank=True, on_delete=models.PROTECT, db_constraint=False
    )
    subject_group = models.ForeignKey(
        "schools.SubjectGroup", null=True, blank=True, on_delete=models.PROTECT, db_constraint=False
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    sent_at = models.DateTimeField(db_default=Now())

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="notice_school_id_key"),
            models.CheckConstraint(
                condition=Q(audience__in=["school", "group", "homeroom_guardians", "class"]),
                name="notice_audience_is_known",
            ),
            models.CheckConstraint(
                condition=(
                    Q(audience="school", school_class__isnull=True, subject_group__isnull=True)
                    | Q(audience="group", school_class__isnull=True, subject_group__isnull=False)
                    | Q(
                        audience__in=["homeroom_guardians", "class"],
                        school_class__isnull=False,
                        subject_group__isnull=True,
                    )
                ),
                name="notice_target_fits_audience",
            ),
            models.CheckConstraint(
                condition=~Q(title__regex=r"^\s*$"), name="notice_title_not_blank"
            ),
            models.CheckConstraint(
                condition=~Q(title__regex=r"[\r\n]"), name="notice_title_single_line"
            ),
            models.CheckConstraint(
                condition=~Q(body__regex=r"^\s*$"), name="notice_body_not_blank"
            ),
            models.CheckConstraint(
                condition=LessThanOrEqual(Length("body"), MAX_BODY_LENGTH),
                name="notice_body_length",
            ),
        ]

    def __str__(self):
        return f"{self.audience} notice {self.pk}"


class NoticeRecipient(TenantModel):
    """One person a notice reached, fixed at sending. The trigger `noticerecipient_is_in_audience`
    (function `notice_reaches`, migration 0002) holds who may be a recipient; the app role may
    set `read_at` (the recipient's first open) and `emailed_at` (the email task's stamp) and
    nothing else, each once (trigger `noticerecipient_set_once`). Not audited: a whole-School
    notice writes one row per family, and the rows follow from audited Guardian links,
    Enrollments and Role Assignments."""

    notice = models.ForeignKey(Notice, on_delete=models.PROTECT, db_constraint=False)
    membership = models.ForeignKey(
        "accounts.Membership", on_delete=models.PROTECT, db_constraint=False, related_name="+"
    )
    read_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="noticerecipient_school_id_key"),
            models.UniqueConstraint(
                fields=["school", "notice", "membership"], name="noticerecipient_once_per_notice"
            ),
        ]

    def __str__(self):
        return f"{self.notice_id} -> {self.membership_id}"
