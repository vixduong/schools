from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import Account, Membership, RoleAssignment
from schools.tests.factories import make_class, make_year
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
    """A Membership holding `role` (homeroom teacher of 7A by default), in force since a month."""
    with school_scope(school.pk):
        membership = Membership.objects.create(school=school, account=account)
        scope = {}
        if role == RoleAssignment.Role.HOMEROOM_TEACHER:
            year = make_year(school)
            scope = {"school_year": year, "school_class": make_class(school, year)}
        RoleAssignment.objects.create(
            school=school,
            membership=membership,
            role=role,
            valid_from=timezone.localdate() - timedelta(days=30),
            **scope,
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
