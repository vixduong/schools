import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def test_creates_a_school_you_can_sign_in_to(client, schools, settings):
    # Runs as the owner role, like the command does in dev (no as_app_role).
    settings.DEBUG = True
    call_command("create_dev_school", "c", "c@example.com", "--password", "pw-for-c")
    call_command("create_dev_school", "c", "c@example.com")  # idempotent
    response = client.post(
        "/api/auth/login/",
        {"identifier": "c@example.com", "password": "pw-for-c"},
        HTTP_HOST="c.localhost",
    )
    assert [r["role"] for r in response.json()["role_assignments"]] == ["school_admin"]


def test_refuses_outside_debug(schools, settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="development only"):
        call_command("create_dev_school", "c", "c@example.com")
