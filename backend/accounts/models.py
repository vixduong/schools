import re

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Func, Q, Value
from django.db.models.functions import Coalesce, Lower
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
    # The Ministry's identifier for a staff member; set when known (import, slice 6).
    # NULL, not "", when unknown, so the unique never collides on blanks.
    ministry_staff_id = models.CharField(max_length=30, null=True, blank=True)  # noqa: DJ001

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "account"], name="membership_one_per_school"),
            models.UniqueConstraint(
                fields=["school", "ministry_staff_id"], name="membership_ministry_staff_id_key"
            ),
            # Target of RoleAssignment's composite foreign key.
            models.UniqueConstraint(fields=["school", "id"], name="membership_school_id_key"),
        ]

    def __str__(self):
        return f"{self.account_id} in {self.school_id}"

    def save(self, *args, **kwargs):
        self.ministry_staff_id = (self.ministry_staff_id or "").strip() or None
        super().save(*args, **kwargs)


class RoleAssignmentQuerySet(models.QuerySet):
    def in_force(self, on=None):
        """Active assignments (not pending a second person's confirmation) whose own period
        contains `on` (default: today) and whose Membership is active. School-year dates do not
        clip a role: schools work between years too."""
        on = on or timezone.localdate()
        return self.filter(
            Q(valid_from__lte=on),
            Q(valid_to__isnull=True) | Q(valid_to__gte=on),
            membership__status=Membership.Status.ACTIVE,
            status=RoleAssignment.Status.ACTIVE,
        )


# `school_year` is set only on class-scoped roles (and equals the class's year). `grade` is for
# a grade-wide role that arrives with the activities phase: no current role may set it.
SCOPE_COLUMNS = ("school_year", "grade", "subject_group", "school_class", "subject")


def _period() -> Func:
    return Func(
        "valid_from",
        "valid_to",
        Value("[]"),
        function="daterange",
        output_field=DateRangeField(),
    )


def _role_scope(role: str, *scoped: str) -> Q:
    """`role` is valid only with exactly the `scoped` scope columns set."""
    q = Q(role=role)
    for column in SCOPE_COLUMNS:
        q &= Q(**{f"{column}__isnull": column not in scoped})
    return q


class RoleAssignment(models.Model):
    """A Membership's duty in one scope (docs/roles.md). Tenant table (RLS).

    The scope is the typed nullable FKs `school_year`, `grade`, `subject_group`, `school_class`
    and `subject`; the check constraint says which a role needs. A student and a Guardian get no
    RoleAssignment row: their rights come from `Student.membership` + Enrollment and from
    GuardianLink (schools app), so each link has one source of truth.
    Every FK to another tenant table has no single-column database FK: the migrations add
    composite FKs (school_id, x_id) -> x (school_id, id), so the target must belong to the same
    School; a class-scoped role also has (school_id, school_year_id, school_class_id) ->
    schoolclass, so its school year is the class's year. A period is
    [valid_from, valid_to] (open-ended when valid_to is null); periods of the same membership,
    role and scope never overlap, so a role can end and resume with its history kept."""

    class Role(models.TextChoices):
        SCHOOL_ADMIN = "school_admin"
        PRINCIPAL_BOARD = "principal_board"
        GROUP_LEADER = "group_leader"
        HOMEROOM_TEACHER = "homeroom_teacher"
        SUBJECT_TEACHER = "subject_teacher"

    class Title(models.TextChoices):
        PRINCIPAL = "principal"
        VICE_PRINCIPAL = "vice_principal"

    class Status(models.TextChoices):
        ACTIVE = "active"
        # A School admin granting themselves principal_board waits for a second person.
        PENDING_CONFIRMATION = "pending_confirmation"

    school = models.ForeignKey("tenancy.School", on_delete=models.CASCADE)
    membership = models.ForeignKey(Membership, on_delete=models.PROTECT, db_constraint=False)
    role = models.CharField(max_length=30, choices=Role)
    school_year = models.ForeignKey(
        "schools.SchoolYear", null=True, blank=True, on_delete=models.PROTECT, db_constraint=False
    )
    grade = models.ForeignKey(
        "schools.Grade", null=True, blank=True, on_delete=models.PROTECT, db_constraint=False
    )
    subject_group = models.ForeignKey(
        "schools.SubjectGroup", null=True, blank=True, on_delete=models.PROTECT, db_constraint=False
    )
    school_class = models.ForeignKey(
        "schools.SchoolClass", null=True, blank=True, on_delete=models.PROTECT, db_constraint=False
    )
    subject = models.ForeignKey(
        "schools.Subject", null=True, blank=True, on_delete=models.PROTECT, db_constraint=False
    )
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=Status, default=Status.ACTIVE)
    # Set only on a self-granted principal_board: who asked, and the second person who confirmed.
    requested_by = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_constraint=False,
        related_name="+",
    )
    confirmed_by = models.ForeignKey(
        Membership,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_constraint=False,
        related_name="+",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # Named duties of a principal-board member (docs/roles.md); NULL/false on every other role.
    # `title` is set once (the API refuses a change), and at most one `principal` row is in force
    # at a time (exclusion constraint).
    title = models.CharField(max_length=20, choices=Title, null=True, blank=True)  # noqa: DJ001
    can_reopen_gradebooks = models.BooleanField(default=False)
    signs_for_principal = models.BooleanField(default=False)

    objects = RoleAssignmentQuerySet.as_manager()

    class Meta:
        constraints = [
            # student and guardian are absent on purpose: they are never RoleAssignment rows.
            models.CheckConstraint(
                condition=_role_scope("school_admin")
                | _role_scope("principal_board")
                | _role_scope("group_leader", "subject_group")
                | _role_scope("homeroom_teacher", "school_year", "school_class")
                | _role_scope("subject_teacher", "school_year", "subject", "school_class"),
                name="roleassignment_scope_matches_role",
            ),
            models.CheckConstraint(
                condition=Q(valid_to__isnull=True) | Q(valid_to__gte=models.F("valid_from")),
                name="roleassignment_valid_to_after_valid_from",
            ),
            models.CheckConstraint(
                condition=Q(confirmed_by__isnull=True)
                | (
                    Q(requested_by__isnull=False)
                    & ~Q(confirmed_by=models.F("requested_by"))
                    & ~Q(confirmed_by=models.F("membership"))
                ),
                name="roleassignment_confirmer_is_a_third_person",
            ),
            models.CheckConstraint(
                condition=Q(requested_by__isnull=True)
                | Q(status="pending_confirmation")
                | Q(confirmed_by__isnull=False),
                name="roleassignment_self_grant_needs_confirmation",
            ),
            models.CheckConstraint(
                condition=Q(status="active") | Q(requested_by__isnull=False),
                name="roleassignment_pending_has_requester",
            ),
            models.CheckConstraint(
                condition=Q(role="principal_board")
                | (
                    Q(title__isnull=True)
                    & Q(can_reopen_gradebooks=False)
                    & Q(signs_for_principal=False)
                ),
                name="roleassignment_duties_only_on_principal_board",
            ),
            models.CheckConstraint(
                condition=Q(title__isnull=True) | Q(title__in=["principal", "vice_principal"]),
                name="roleassignment_title_is_known",
            ),
            ExclusionConstraint(
                name="roleassignment_no_overlapping_periods",
                expressions=[
                    ("school", RangeOperators.EQUAL),
                    ("membership", RangeOperators.EQUAL),
                    ("role", RangeOperators.EQUAL),
                    # NULL never equals NULL in an exclusion constraint, so coalesce the scope.
                    *(
                        (Coalesce(column, Value(0)), RangeOperators.EQUAL)
                        for column in SCOPE_COLUMNS
                    ),
                    (_period(), RangeOperators.OVERLAPS),
                ],
            ),
            # One principal at a time: the School's principal can be replaced, not joined.
            ExclusionConstraint(
                name="roleassignment_one_principal_at_a_time",
                expressions=[
                    ("school", RangeOperators.EQUAL),
                    (_period(), RangeOperators.OVERLAPS),
                ],
                condition=Q(title="principal"),
            ),
        ]

    def __str__(self):
        return f"{self.role} ({self.school_year_id})"
