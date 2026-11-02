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


def test_a_number_counts_as_the_same_identifier(schools):
    """DRF's CharField reads 84912345678 as text, and the Account lookup normalises it to
    0912345678: the limiter must count it as that identifier."""
    for n in range(LIMITS["identifier"]):
        login(84912345678 if n % 2 else "0912345678", "wrong")
    assert login("0912345678", "wrong").status_code == 429


def test_sign_in_takes_json_only(alice):
    """A form body would hide the identifier from the limiter."""
    body = {"identifier": "alice@example.com", "password": PASSWORD}
    assert Client().post("/api/auth/login/", body, HTTP_HOST=A).status_code == 415


def test_real_sign_ins_do_not_use_up_the_budget(alice):
    """One school network shares an address: successes give their attempt back."""
    for _ in range(LIMITS["identifier"] + 2):
        assert login("alice@example.com", PASSWORD).status_code == 200
    assert login("alice@example.com", "wrong").status_code == 400


def test_the_count_commits_before_the_schools_transaction():
    """Placed before TenantMiddleware: no counter row stays locked through the password check."""
    from django.conf import settings

    order = settings.MIDDLEWARE
    assert order.index("accounts.ratelimit.SignInRateLimitMiddleware") < order.index(
        "tenancy.middleware.TenantMiddleware"
    )
