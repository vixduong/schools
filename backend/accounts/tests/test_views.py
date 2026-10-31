from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone

from accounts.models import Account, Membership, RoleAssignment
from tenancy.rls import school_scope
from tenancy.tests.conftest import owner_role

from .conftest import PASSWORD

pytestmark = pytest.mark.usefixtures("as_app_role")

A, B = "a.localhost", "b.localhost"
LOGIN, LOGOUT, ME, CSRF = (f"/api/auth/{p}/" for p in ("login", "logout", "me", "csrf"))


def sign_in(client, host=A, identifier="alice@example.com", password=PASSWORD):
    return client.post(LOGIN, {"identifier": identifier, "password": password}, HTTP_HOST=host)


def test_login_on_a_member_school_returns_me_and_sets_the_session(client, alice):
    response = sign_in(client)
    assert response.status_code == 200
    body = response.json()
    assert body["account"] == {"id": alice.pk, "display_name": "Alice"}
    assert body["school"] == {"name": "A", "subdomain": "a"}
    assert [r["role"] for r in body["role_assignments"]] == ["homeroom_teacher"]
    session = response.cookies[settings.SESSION_COOKIE_NAME]
    assert session["httponly"] and session["samesite"] == "Lax" and not session["domain"]
    assert session["secure"] == (settings.SECURE_COOKIES or "")
    assert client.get(ME, HTTP_HOST=A).json() == body


@pytest.mark.parametrize("identifier", ["ALICE@Example.com", "0912 345 678", "+84912345678"])
def test_login_identifier_is_normalized(client, alice, identifier):
    assert sign_in(client, identifier=identifier).status_code == 200


def test_me_lists_only_role_assignments_in_force(client, alice, schools):
    with school_scope(schools[0].pk):
        RoleAssignment.objects.update(valid_to=timezone.localdate() - timedelta(days=1))
    sign_in(client)
    assert client.get(ME, HTTP_HOST=A).json()["role_assignments"] == []


def test_membership_of_one_school_cannot_sign_in_on_another(client, alice):
    wrong_password = sign_in(client, password="nope")
    other_school = sign_in(client, host=B)
    unknown = sign_in(client, identifier="nobody@example.com")
    assert wrong_password.status_code == other_school.status_code == unknown.status_code == 400
    assert wrong_password.json() == other_school.json() == unknown.json()
    assert settings.SESSION_COOKIE_NAME not in other_school.cookies


def test_inactive_membership_cannot_sign_in(client, alice, schools):
    with school_scope(schools[0].pk):
        Membership.objects.update(status=Membership.Status.INACTIVE)
    assert sign_in(client).status_code == 400


def test_inactive_account_cannot_sign_in(client, alice):
    with owner_role():
        Account.objects.update(is_active=False)
    assert sign_in(client).status_code == 400


def test_login_rotates_the_session_key(client, alice):
    session = client.session
    session["anonymous"] = True
    session.save()
    before = session.session_key
    assert sign_in(client).status_code == 200
    after = client.session.session_key
    assert after != before
    assert not Session.objects.filter(pk=before).exists()
    assert Session.objects.filter(pk=after).exists()


def test_me_requires_sign_in(client, alice):
    assert client.get(ME, HTTP_HOST=A).status_code == 403


def test_logout_clears_the_session(client, alice):
    sign_in(client)
    assert Session.objects.count() == 1
    assert client.post(LOGOUT, HTTP_HOST=A).status_code == 204
    assert Session.objects.count() == 0
    assert client.get(ME, HTTP_HOST=A).status_code == 403


def test_csrf_endpoint_sets_the_cookie(client):
    response = client.get(CSRF, HTTP_HOST=A)
    assert response.status_code == 204
    assert settings.CSRF_COOKIE_NAME in response.cookies


def test_login_and_logout_enforce_csrf(alice):
    client = Client(enforce_csrf_checks=True)
    creds = {"identifier": "alice@example.com", "password": PASSWORD}
    assert client.post(LOGIN, creds, HTTP_HOST=A).status_code == 403
    client.get(CSRF, HTTP_HOST=A)
    token = client.cookies[settings.CSRF_COOKIE_NAME].value
    assert client.post(LOGIN, creds, HTTP_HOST=A, HTTP_X_CSRFTOKEN=token).status_code == 200
    assert client.post(LOGOUT, HTTP_HOST=A).status_code == 403
    token = client.cookies[settings.CSRF_COOKIE_NAME].value
    assert client.post(LOGOUT, HTTP_HOST=A, HTTP_X_CSRFTOKEN=token).status_code == 204


def test_me_lists_the_capabilities_of_the_member(client, alice, schools):
    """Alice is homeroom teacher of 7A: she signs for the class and sees its profiles, and
    nothing else reaches the School."""
    sign_in(client)
    body = client.get(ME, HTTP_HOST=A).json()
    klass = body["role_assignments"][0]["school_class"]
    caps = {c["action"]: c["scopes"] for c in body["capabilities"]}
    assert caps["report_card.sign_class"] == [
        {
            "kind": "homeroom_class",
            "access": "write",
            "once_released": False,
            "school_classes": [klass],
        }
    ]
    assert caps["student_profile.view"][0]["access"] == "read"
    assert "school.configure" not in caps and "accounts.manage" not in caps
    assert sign_in(client).json()["capabilities"] == body["capabilities"]
