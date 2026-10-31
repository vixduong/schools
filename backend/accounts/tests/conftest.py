from datetime import date

import pytest

from accounts.models import Account, Membership, RoleAssignment
from tenancy.models import School
from tenancy.rls import school_scope
from tenancy.tests.conftest import as_app_role  # noqa: F401

PASSWORD = "correct horse"


@pytest.fixture
def schools(transactional_db):
    """Two Schools, committed. Shadows tenancy's fixture of the same name (no probes needed)."""
    return School.objects.create(name="A", subdomain="a"), School.objects.create(
        name="B", subdomain="b"
    )


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
    account = Account(email="alice@example.com", phone="0912345678", display_name="Alice")
    account.set_password(PASSWORD)
    account.save()
    member(schools[0], account)
    return account


@pytest.fixture
def alice_in_both(alice, schools):
    member(schools[1], alice)
    return alice
