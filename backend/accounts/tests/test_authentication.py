import pytest
from django.conf import settings
from django.test import Client

from .conftest import PASSWORD

pytestmark = pytest.mark.usefixtures("as_app_role")

A, B = "a.localhost", "b.localhost"


def sign_in(client, host):
    return client.post(
        "/api/auth/login/",
        {"identifier": "alice@example.com", "password": PASSWORD},
        HTTP_HOST=host,
    )


def test_session_from_one_school_is_rejected_on_another_even_for_a_member_of_both(
    client, alice_in_both
):
    assert sign_in(client, A).status_code == 200
    # Replay the same cookie value against School B, where Alice also has a Membership.
    assert client.get("/api/auth/me/", HTTP_HOST=B).status_code == 403
    assert client.get("/api/auth/me/", HTTP_HOST=A).status_code == 200


def test_signing_in_on_each_school_gives_each_its_own_session(client, alice_in_both):
    sign_in(client, A)
    sign_in(client, B)
    assert client.get("/api/auth/me/", HTTP_HOST=B).json()["school"]["subdomain"] == "b"
    # The browser keeps one cookie per host; this client shares one jar, so A's is gone.
    assert client.get("/api/auth/me/", HTTP_HOST=A).status_code == 403


@pytest.mark.urls("accounts.tests.urls")
def test_csrf_is_enforced_on_post_for_session_authenticated_requests(alice):
    client = Client(enforce_csrf_checks=True)
    client.get("/api/auth/csrf/", HTTP_HOST=A)
    token = client.cookies[settings.CSRF_COOKIE_NAME].value
    sign_in_headers = {"HTTP_HOST": A, "HTTP_X_CSRFTOKEN": token}
    client.post(
        "/api/auth/login/",
        {"identifier": "alice@example.com", "password": PASSWORD},
        **sign_in_headers,
    )
    assert client.post("/api/echo/", HTTP_HOST=A).status_code == 403
    token = client.cookies[settings.CSRF_COOKIE_NAME].value
    assert client.post("/api/echo/", HTTP_HOST=A, HTTP_X_CSRFTOKEN=token).status_code == 200


@pytest.mark.urls("accounts.tests.urls")
def test_default_permission_needs_a_membership_not_just_a_session(client, alice, schools):
    from accounts.models import Account

    bob = Account(email="bob@example.com", display_name="Bob")
    bob.set_password(PASSWORD)
    bob.save()
    client.force_login(bob)
    session = client.session
    session["school_id"] = schools[0].pk
    session.save()
    assert client.post("/api/echo/", HTTP_HOST=A).status_code == 403
