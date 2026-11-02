"""Fixtures shared by every app's tests; helpers are in `testing.py`. An app's own conftest may
override one (tenancy's `schools` adds probes)."""

import psycopg
import pytest
from django.conf import settings
from django.db import connection

from accounts.models import RoleAssignment
from schools.tests.factories import (
    make_class,
    make_primary_class,
    make_student,
    make_subject,
    make_year,
)
from tenancy.models import School
from tenancy.rls import school_scope
from testing import A, db_role, enroll, make_account, member, sign_in


@pytest.fixture
def schools(transactional_db):
    """Two Schools, committed. Shadows tenancy's fixture of the same name (no probes needed)."""
    return School.objects.create(name="A", subdomain="a"), School.objects.create(
        name="B", subdomain="b"
    )


@pytest.fixture
def app_conn(schools):
    """Raw autocommit connection to the test database as the NOBYPASSRLS app role."""
    d = connection.settings_dict
    conn = psycopg.connect(
        dbname=d["NAME"],
        host=d["HOST"],
        port=d["PORT"],
        user=settings.APP_DB_USER,
        password=settings.APP_DB_PASSWORD,
        autocommit=True,
    )
    yield conn
    conn.close()


@pytest.fixture
def as_app_role(schools):
    """Run Django's own connection as the app role, like production requests do."""
    with db_role(settings.APP_DB_USER, settings.APP_DB_PASSWORD):
        yield


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


@pytest.fixture
def admin_a(schools):
    """School admin of School A (email admin-a@example.com)."""
    account = make_account("admin-a@example.com", display_name="Admin A")
    member(schools[0], account, RoleAssignment.Role.SCHOOL_ADMIN)
    return account


@pytest.fixture
def admin_b(schools):
    account = make_account("admin-b@example.com", display_name="Admin B")
    member(schools[1], account, RoleAssignment.Role.SCHOOL_ADMIN)
    return account


@pytest.fixture
def admin(admin_a):
    return sign_in(A, "admin-a@example.com")


@pytest.fixture
def setup(schools, alice):
    """School A: class 7A (alice is its homeroom teacher) with student An, class 7B with Binh,
    primary class 3A with Chi, and an inactive subject."""
    a = schools[0]
    with school_scope(a.pk):
        year = make_year(a)
        k7a, k7b = make_class(a, year, "7A"), make_class(a, year, "7B")
        an, binh, chi = (make_student(a, n) for n in ("An", "Binh", "Chi"))
        enroll(a, an, k7a)
        enroll(a, binh, k7b)
        enroll(a, chi, make_primary_class(a, year))
        retired = make_subject(a, "OLD")
        retired.is_active = False
        retired.save()
    return {"year": year, "7A": k7a, "7B": k7b, "an": an, "binh": binh, "chi": chi}
