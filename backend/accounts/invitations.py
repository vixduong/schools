"""Invitation codes and acceptance (docs/slices/slice-6.md). A School never creates or edits an
Account; the person does, by activating an invitation."""

import re
import secrets
from datetime import timedelta

from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import ValidationError

from schools.models import GuardianLink, Student

from .models import Invitation, Membership, RoleAssignment

# No 0/O or 1/I/L: codes are read from paper and typed on a phone.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 10  # ~49 bits, one-time, expiring
VALID_FOR = timedelta(days=30)


def code_digest(code: str) -> str:
    """HMAC of the code (keyed by SECRET_KEY), so a stolen table yields no usable code and a code
    is found by equality. Case, spaces and dashes typed by the person are ignored."""
    normalized = re.sub(r"[^A-Z0-9]", "", code.upper())
    return salted_hmac("accounts.invitation-code", normalized, algorithm="sha256").hexdigest()


def issue_code(invitation: Invitation) -> str:
    """Give `invitation` a fresh code and expiry (not saved); returns the plain code, the only
    time it exists. An earlier code of the invitation stops working once saved."""
    code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    invitation.code_digest = code_digest(code)
    invitation.expires_at = timezone.now() + VALID_FOR
    return f"{code[:5]}-{code[5:]}"


def accept(invitation: Invitation, account) -> Membership:
    """Apply a pending invitation, locked by the caller, for `account`: the Membership (reused,
    and reactivated, when the Account already has one here), then what the kind grants, then the
    invitation `accepted`. Runs in the caller's savepoint: a database rule (overlapping period,
    membership kinds, secondary level) raises IntegrityError and undoes it all."""
    cannot_apply = ValidationError({"invitation": ["cannot_apply"]})
    membership, _ = Membership.objects.select_for_update().get_or_create(
        school_id=invitation.school_id, account=account
    )
    if membership.status != Membership.Status.ACTIVE:
        membership.status = Membership.Status.ACTIVE
        membership.save(update_fields=["status"])
    today = timezone.localdate()
    match invitation.kind:
        case Invitation.Kind.STAFF:
            for role in invitation.roles.select_related("subject"):
                if role.subject is not None and not role.subject.is_active:
                    raise cannot_apply
                RoleAssignment.objects.create(
                    school_id=invitation.school_id,
                    membership=membership,
                    role=role.role,
                    school_year_id=role.school_year_id,
                    subject_group_id=role.subject_group_id,
                    school_class_id=role.school_class_id,
                    subject_id=role.subject_id,
                    valid_from=role.valid_from,
                )
        case Invitation.Kind.GUARDIAN:
            GuardianLink.objects.create(
                school_id=invitation.school_id,
                membership=membership,
                student_id=invitation.student_id,
                relation=invitation.relation,
                valid_from=today,
            )
        case Invitation.Kind.STUDENT:
            student = Student.objects.select_for_update().get(pk=invitation.student_id)
            if student.membership_id not in (None, membership.pk):
                raise cannot_apply
            student.membership = membership
            student.save(update_fields=["membership"])
    invitation.status = Invitation.Status.ACCEPTED
    invitation.accepted_membership = membership
    invitation.save(update_fields=["status", "accepted_membership"])
    return membership
