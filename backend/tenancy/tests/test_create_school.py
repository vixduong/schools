"""Slice 9: the operator opens a School; its first admin joins by invitation."""

import re
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from accounts.models import Account, Invitation, RoleAssignment
from audit.models import AuditEvent
from tenancy.models import School
from tenancy.rls import school_scope
from testing import owner_role

ARGS = {
    "name": "THCS Mẫu",
    "admin": "Hieu.Truong@Example.com",
    "admin_name": "Cô Hà",
    "operator": "Op",
}


def create(subdomain="mau", **extra):
    out = StringIO()
    with owner_role():
        call_command("create_school", subdomain, **(ARGS | extra), stdout=out)
    return re.search(r"Code .*: (\S+)", out.getvalue()).group(1), out.getvalue()


def activate(code, identifier="hieu.truong@example.com", host="mau.localhost"):
    body = {"code": code, "identifier": identifier, "password": "new password 1"}
    return Client().post(
        "/api/auth/activate/", body, content_type="application/json", HTTP_HOST=host
    )


def test_a_new_school_and_its_first_admin_end_to_end(transactional_db):
    code, out = create()
    assert "http://mau.localhost/activate" in out
    school = School.objects.get(subdomain="mau")
    assert school.name == "THCS Mẫu" and not Account.objects.exists()  # ADR 0002
    response = activate(code)
    assert response.status_code == 200, response.json()
    assert [r["role"] for r in response.json()["role_assignments"]] == ["school_admin"]
    with owner_role(), school_scope(school.pk):
        assert AuditEvent.objects.filter(actor="operator:Op", target_table="accounts_invitation")
    with pytest.raises(CommandError, match="already has a School admin"):
        create()


def test_running_again_before_activation_replaces_the_code(transactional_db):
    first, _ = create()
    second, out = create()
    assert out.startswith("Existing School")
    assert activate(first).status_code == 400
    assert activate(second).status_code == 200
    with owner_role(), school_scope(School.objects.get().pk):
        assert Invitation.objects.filter(status="revoked").count() == 1


@pytest.mark.parametrize("subdomain", ["www", "Mau", "a.b", "x-", "x" * 64])
def test_unusable_subdomains_are_refused(transactional_db, subdomain):
    with pytest.raises(CommandError, match="not a usable subdomain"):
        create(subdomain)
    assert not School.objects.exists()


def test_the_admin_is_an_email_or_a_vn_mobile(transactional_db):
    with pytest.raises(CommandError, match="neither an email"):
        create(admin="12345")
    code, _ = create(admin="+84 912 345 678")
    assert activate(code, identifier="0912345678").status_code == 200
    with owner_role(), school_scope(School.objects.get().pk):
        assert RoleAssignment.objects.get().role == "school_admin"
