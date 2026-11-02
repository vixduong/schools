import pytest
from django.test import Client

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
from schools.models import Enrollment
from tenancy.rls import school_scope

from .factories import make_class, make_primary_class, make_student, make_subject, make_year


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


A, B = "a.localhost", "b.localhost"
INVALID = {"non_field_errors": ["Invalid or expired invitation."]}


def sign_in(host, email):
    client = Client()
    response = client.post(
        "/api/auth/login/", {"identifier": email, "password": PASSWORD}, HTTP_HOST=host
    )
    assert response.status_code == 200, response.json()
    return client


def post(client, host, path, body=None):
    return client.post(f"/api/{path}", body or {}, content_type="application/json", HTTP_HOST=host)


def activate(host, code, identifier, password="new password 1", **extra):
    client = Client()
    body = {"code": code, "identifier": identifier, "password": password, **extra}
    return client, post(client, host, "auth/activate/", body)


def enroll(school, student, klass):
    return Enrollment.objects.create(
        school=school,
        student=student,
        school_year=klass.school_year,
        school_class=klass,
        valid_from=klass.school_year.starts_on,
        reason_started=Enrollment.ReasonStarted.NEW_YEAR,
    )


@pytest.fixture
def admin(admin_a):  # noqa: F811
    return sign_in(A, "admin-a@example.com")


@pytest.fixture
def setup(schools, alice):  # noqa: F811
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
