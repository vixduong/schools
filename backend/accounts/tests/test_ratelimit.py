"""Slice 9: sign-in and activation rate limits."""

import pytest
from django.test import Client, override_settings

from accounts.models import Attempt
from accounts.ratelimit import LIMITS
from testing import PASSWORD

pytestmark = pytest.mark.usefixtures("as_app_role")
A = "a.localhost"


def login(identifier, password, client=None, **meta):
    body = {"identifier": identifier, "password": password}
    return (client or Client()).post(
        "/api/auth/login/", body, content_type="application/json", HTTP_HOST=A, **meta
    )


def test_failed_logins_count_and_lock_the_identifier(alice):
    """The refusals roll back the view's savepoint; the count must survive it."""
    for _ in range(LIMITS["identifier"]):
        assert login("ALICE@example.com", "wrong").status_code == 400
    response = login("alice@example.com", PASSWORD)  # the right password, too late
    assert response.status_code == 429
    assert response.json() == {"detail": "too_many_attempts"}
    assert 0 < int(response["Retry-After"]) <= 15 * 60 + 1
    # Keys are HMACs: the table holds no identifier or address.
    assert not Attempt.objects.filter(key__contains="alice").exists()


def test_one_address_trying_many_identifiers_is_limited(schools):
    for n in range(LIMITS["client"]):
        assert login(f"x{n}@example.com", "wrong").status_code == 400
    assert login("someone@example.com", "wrong").status_code == 429


@override_settings(CLIENT_IP_HEADER="HTTP_CF_CONNECTING_IP")
def test_behind_the_proxy_the_client_address_comes_from_its_header(schools):
    for n in range(LIMITS["client"]):
        login(f"x{n}@example.com", "wrong", HTTP_CF_CONNECTING_IP="203.0.113.7")
    assert login("y@example.com", "wrong", HTTP_CF_CONNECTING_IP="203.0.113.7").status_code == 429
    assert login("y@example.com", "wrong", HTTP_CF_CONNECTING_IP="203.0.113.8").status_code == 400


def test_activation_is_limited_too(schools):
    body = {"code": "AAAAA-AAAAA", "identifier": "0912345678", "password": "new password 1"}
    for _ in range(LIMITS["identifier"]):
        Client().post("/api/auth/activate/", body, content_type="application/json", HTTP_HOST=A)
    response = Client().post(
        "/api/auth/activate/", body, content_type="application/json", HTTP_HOST=A
    )
    assert response.status_code == 429
