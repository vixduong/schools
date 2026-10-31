import re

from django.contrib.auth.base_user import AbstractBaseUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

# Vietnamese mobile numbers only (owner decision, slice 3): 10 digits, 0 then 3/5/7/8/9.
PHONE_PATTERN = r"^0[35789][0-9]{8}$"


def normalize_email(raw: str) -> str:
    return raw.strip().lower()


def normalize_phone(raw: str) -> str:
    """Drop separators and turn +84/84 into the leading 0. Anything else is left for the
    caller (or the database check) to reject."""
    return re.sub(r"^\+?84(?=[35789][0-9]{8}$)", "0", re.sub(r"[\s.\-()]", "", raw))


class AccountManager(models.Manager):
    def get_by_identifier(self, raw: str) -> "Account":
        """The Account whose email or phone matches what the user typed. Raises DoesNotExist."""
        if "@" in raw:
            return self.get(email=normalize_email(raw))
        return self.get(phone=normalize_phone(raw))


class Account(AbstractBaseUser):
    """One person's login across every School (ADR 0002). Global table: no `school_id`, no RLS,
    so it must never hold School data. No Django groups or permissions: School roles live in
    RoleAssignment."""

    display_name = models.CharField(max_length=200)
    # NULL, not "", when absent, so the unique indexes allow many Accounts without one.
    email = models.EmailField(unique=True, null=True, blank=True)  # noqa: DJ001
    phone = models.CharField(  # noqa: DJ001
        max_length=10,
        unique=True,
        null=True,
        blank=True,
        validators=[RegexValidator(PHONE_PATTERN)],
    )
    is_active = models.BooleanField(default=True)

    USERNAME_FIELD = "email"
    objects = AccountManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(email__isnull=False) | Q(phone__isnull=False),
                name="account_has_email_or_phone",
            ),
            models.CheckConstraint(
                condition=Q(email__isnull=True) | Q(email=Lower("email")),
                name="account_email_is_lowercase",
            ),
            models.CheckConstraint(
                condition=Q(phone__isnull=True) | Q(phone__regex=PHONE_PATTERN),
                name="account_phone_is_normalized",
            ),
        ]

    def __str__(self):
        return self.display_name

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email) if self.email else None
        self.phone = normalize_phone(self.phone) if self.phone else None
        super().save(*args, **kwargs)


class Membership(models.Model):
    """An Account's presence in one School. Tenant table (RLS)."""

    class Status(models.TextChoices):
        ACTIVE = "active"
        INACTIVE = "inactive"

    school = models.ForeignKey("tenancy.School", on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status, default=Status.ACTIVE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "account"], name="membership_one_per_school"),
            # Target of RoleAssignment's composite foreign key.
            models.UniqueConstraint(fields=["school", "id"], name="membership_school_id_key"),
        ]

    def __str__(self):
        return f"{self.account_id} in {self.school_id}"


class RoleAssignmentQuerySet(models.QuerySet):
    def in_force(self, on=None):
        on = on or timezone.localdate()
        return self.filter(Q(valid_from__lte=on), Q(valid_to__isnull=True) | Q(valid_to__gte=on))


class RoleAssignment(models.Model):
    """A Membership's duty in one scope for one school year (docs/roles.md). Tenant table (RLS).

    `membership` has no single-column database FK: the migration adds the composite FK
    (school_id, membership_id) -> Membership (school_id, id), so the Membership must belong
    to the same School."""

    class Role(models.TextChoices):
        SCHOOL_ADMIN = "school_admin"
        PRINCIPAL_BOARD = "principal_board"
        GROUP_LEADER = "group_leader"
        HOMEROOM_TEACHER = "homeroom_teacher"
        SUBJECT_TEACHER = "subject_teacher"
        STUDENT = "student"
        GUARDIAN = "guardian"

    school = models.ForeignKey("tenancy.School", on_delete=models.CASCADE)
    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, db_constraint=False)
    role = models.CharField(max_length=30, choices=Role)
    # Both null means School-wide. Real class/subject references arrive with school setup.
    scope_kind = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001
    scope_id = models.BigIntegerField(null=True, blank=True)
    school_year = models.CharField(max_length=9)  # "2025-2026"
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    objects = RoleAssignmentQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["school", "membership", "role", "scope_kind", "scope_id", "school_year"],
                nulls_distinct=False,
                name="roleassignment_unique_per_scope_and_year",
            ),
            models.CheckConstraint(
                condition=Q(scope_kind__isnull=True, scope_id__isnull=True)
                | Q(scope_kind__isnull=False, scope_id__isnull=False),
                name="roleassignment_scope_kind_and_id_together",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=models.F("valid_from")),
                name="roleassignment_valid_to_after_valid_from",
            ),
        ]

    def __str__(self):
        return f"{self.role} ({self.school_year})"
