"""Test helpers shared by every app's tests (fixtures live in `conftest.py` beside this)."""

from contextlib import contextmanager
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.test import Client
from django.utils import timezone

from accounts.models import Account, Membership, RoleAssignment
from schools.models import Enrollment
from schools.tests.factories import make_class, make_year
from tenancy.rls import school_scope

PASSWORD = "correct horse"


A, B = "a.localhost", "b.localhost"


INVALID = {"non_field_errors": ["Invalid or expired invitation."]}


@contextmanager
def db_role(user, password):
    """Run Django's own connection as another DB role for the duration of the block."""
    d = connection.settings_dict
    previous = (d["USER"], d["PASSWORD"])
    connection.close()
    d["USER"], d["PASSWORD"] = user, password
    try:
        yield
    finally:
        connection.close()
        d["USER"], d["PASSWORD"] = previous


def owner_role():
    """For test setup the app role may not do (it cannot create or edit Accounts)."""
    return db_role(settings.OWNER_DB_USER, settings.OWNER_DB_PASSWORD)


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


def sign_in(host, email):
    client = Client()
    response = client.post(
        "/api/auth/login/",
        {"identifier": email, "password": PASSWORD},
        content_type="application/json",
        HTTP_HOST=host,
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
