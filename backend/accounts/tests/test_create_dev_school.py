from datetime import date

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from accounts.models import RoleAssignment
from schools.models import SchoolYear
from tenancy.models import School
from tenancy.rls import school_scope


def test_creates_a_school_you_can_sign_in_to(client, schools, settings):
    # Runs as the owner role, like the command does in dev (no as_app_role).
    settings.DEBUG = True
    call_command("create_dev_school", "c", "c@example.com", "--password", "pw-for-c")
    call_command("create_dev_school", "c", "c@example.com")  # idempotent
    response = client.post(
        "/api/auth/login/",
        {"identifier": "c@example.com", "password": "pw-for-c"},
        content_type="application/json",
        HTTP_HOST="c.localhost",
    )
    assert [r["role"] for r in response.json()["role_assignments"]] == ["school_admin"]


def test_refuses_outside_debug(schools, settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="development only"):
        call_command("create_dev_school", "c", "c@example.com")


def test_running_again_after_the_school_year_rolls_over_succeeds(schools, settings, monkeypatch):
    settings.DEBUG = True
    for today in (date(2026, 10, 31), date(2027, 9, 15)):
        monkeypatch.setattr(timezone, "localdate", lambda today=today: today)
        call_command("create_dev_school", "c", "c@example.com")
    with school_scope(School.objects.get(subdomain="c").pk):
        assert list(SchoolYear.objects.values_list("name", flat=True)) == ["2026-2027", "2027-2028"]
        # One open-ended admin role carries across years; no second row.
        (admin,) = RoleAssignment.objects.all()
        assert admin.school_year_id is None and admin.valid_to is None
