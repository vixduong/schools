from datetime import date

import pytest

from accounts.models import Account, Membership, RoleAssignment
from tenancy.models import School
from tenancy.rls import school_scope
from tenancy.tests.conftest import as_app_role, owner_role  # noqa: F401

PASSWORD = "correct horse"


@pytest.fixture
def schools(transactional_db):
    """Two Schools, committed. Shadows tenancy's fixture of the same name (no probes needed)."""
    return School.objects.create(name="A", subdomain="a"), School.objects.create(
        name="B", subdomain="b"
    )


def make_account(email=None, phone=None, display_name="Test", password=PASSWORD):
    """The app role cannot create Accounts, so this runs as the owner."""
    account = Account(email=email, phone=phone, display_name=display_name)
    account.set_password(password)
    with owner_role():
        account.save()
    return account


def member(school, account, role=RoleAssignment.Role.HOMEROOM_TEACHER):
    with school_scope(school.pk):
        membership = Membership.objects.create(school=school, account=account)
        RoleAssignment.objects.create(
            school=school,
            membership=membership,
            role=role,
            scope_kind="class",
            scope_id=7,
            school_year="2025-2026",
            valid_from=date(2025, 9, 1),
        )
    return membership


@pytest.fixture
def alice(schools):
    """Member of School A only."""
    account = make_account("alice@example.com", "0912345678", "Alice")
    member(schools[0], account)
    return account


@pytest.fixture
def alice_in_both(alice, schools):
    member(schools[1], alice)
    return alice
