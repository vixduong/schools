import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from accounts.models import Account, RoleAssignment, normalize_phone
from tenancy.rls import school_scope

from .conftest import member


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0912 345 678", "0912345678"),
        ("+84 912.345.678", "0912345678"),
        ("84912345678", "0912345678"),
        ("+84 332 345 678", "0332345678"),
        # Not mobile: left as typed for the validator and the database check to refuse.
        ("+84 212 345 678", "+84212345678"),
        ("84112345678", "84112345678"),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("phone", ["0212345678", "0112345678", "0412345678", "0612345678"])
def test_phone_must_be_a_vietnamese_mobile_number(schools, phone):
    with pytest.raises(ValidationError):
        Account(phone=phone, display_name="X").full_clean(exclude=["password"])
    with pytest.raises(IntegrityError, match="account_phone_is_normalized"):
        Account.objects.bulk_create([Account(phone=phone, display_name="X")])


@pytest.mark.parametrize("phone", ["0312345678", "0512345678", "0712345678", "0812345678"])
def test_phone_accepts_mobile_prefixes(schools, phone):
    account = Account(phone=phone, display_name="X")
    account.full_clean(exclude=["password"])
    account.save()


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
