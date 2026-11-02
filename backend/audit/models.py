from django.db import models
from django.db.models import Q
from django.utils import timezone

from schools.models import TenantModel


class AuditEvent(TenantModel):
    """One entry of the School's audit log (docs/slices/slice-7.md). Append-only in the
    database: the app role may only SELECT; entries come from the `audit_row_change` trigger
    (row writes on the audited tables) and the `audit_record` function (other events), both
    SECURITY DEFINER. `actor` says who acted (`member`, `activation`, `operator:<name>`,
    `system`); `actor_membership` is set when a member did. `details`: the new row for an
    insert, `{column: [old, new]}` of the changed columns for an update, the old row for a
    delete; event-specific for the others."""

    at = models.DateTimeField()
    actor_membership = models.ForeignKey(
        "accounts.Membership",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_constraint=False,
        related_name="+",
    )
    actor = models.CharField(max_length=200)
    action = models.CharField(max_length=50)  # insert, update, delete, student.view_sensitive, ...
    target_table = models.CharField(max_length=63, blank=True)
    target_id = models.BigIntegerField(null=True, blank=True)
    details = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="auditevent_school_id_key"),
        ]
        indexes = [models.Index(fields=["school", "target_table", "target_id"])]

    def __str__(self):
        return f"{self.action} {self.target_table} {self.target_id}"


class SupportGrantQuerySet(models.QuerySet):
    def in_force(self, at=None):
        at = at or timezone.now()
        return self.filter(starts_at__lte=at, ends_at__gt=at, revoked_at__isnull=True)


class SupportGrant(TenantModel):
    """The School lets the platform operator in, read only, for a fixed window
    (docs/roles.md "Least data"). Never edited except `revoked_*`; never deleted."""

    granted_by = models.ForeignKey(
        "accounts.Membership", on_delete=models.PROTECT, db_constraint=False, related_name="+"
    )
    reason = models.CharField(max_length=500)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        "accounts.Membership",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        db_constraint=False,
        related_name="+",
    )

    objects = SupportGrantQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["school", "id"], name="supportgrant_school_id_key"),
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="supportgrant_ends_after_start"
            ),
            models.CheckConstraint(
                condition=Q(revoked_at__isnull=True, revoked_by__isnull=True)
                | Q(revoked_at__isnull=False, revoked_by__isnull=False),
                name="supportgrant_revoked_by_whom",
            ),
        ]

    def __str__(self):
        return f"support grant {self.pk} until {self.ends_at}"
