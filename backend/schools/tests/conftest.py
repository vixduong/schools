import pytest

from accounts.models import RoleAssignment
from accounts.tests.conftest import (  # noqa: F401
    PASSWORD,
    alice,
    as_app_role,
    make_account,
    member,
    owner_role,
    schools,
)


@pytest.fixture
def admin_a(schools):  # noqa: F811
    """School admin of School A (email admin-a@example.com)."""
    account = make_account("admin-a@example.com", display_name="Admin A")
    member(schools[0], account, RoleAssignment.Role.SCHOOL_ADMIN)
    return account


@pytest.fixture
def admin_b(schools):  # noqa: F811
    account = make_account("admin-b@example.com", display_name="Admin B")
    member(schools[1], account, RoleAssignment.Role.SCHOOL_ADMIN)
    return account
