import pytest
from django.db import IntegrityError

from accounts.models import Account, RoleAssignment, normalize_phone
from tenancy.rls import school_scope

from .conftest import member

pytestmark = pytest.mark.usefixtures("as_app_role")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0912 345 678", "0912345678"),
        ("+84 912.345.678", "0912345678"),
        ("84912345678", "0912345678"),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_email_is_unique_case_insensitively(schools):
    Account(email="x@example.com", display_name="X").save()
    with pytest.raises(IntegrityError):
        Account(email="X@EXAMPLE.com", display_name="Y").save()


def test_account_needs_an_email_or_a_phone(schools):
    with pytest.raises(IntegrityError):
        Account(display_name="Nobody").save()


def test_role_assignment_cannot_point_at_a_membership_of_another_school(schools):
    a, b = schools
    other = Account(email="o@example.com", display_name="O")
    other.save()
    membership_in_b = member(b, other)
    with pytest.raises(IntegrityError, match="roleassignment_membership_same_school"):
        with school_scope(a.pk):
            RoleAssignment.objects.create(
                school=a,
                membership=membership_in_b,
                role=RoleAssignment.Role.GUARDIAN,
                school_year="2025-2026",
                valid_from="2025-09-01",
            )


def test_school_wide_role_assignment_is_unique_despite_null_scope(schools, alice):
    a, _ = schools
    fields = dict(
        school=a,
        role=RoleAssignment.Role.SCHOOL_ADMIN,
        school_year="2025-2026",
        valid_from="2025-09-01",
    )
    with school_scope(a.pk):
        membership = a.membership_set.get()
    with pytest.raises(IntegrityError):
        with school_scope(a.pk):
            RoleAssignment.objects.create(membership=membership, **fields)
            RoleAssignment.objects.create(membership=membership, **fields)
