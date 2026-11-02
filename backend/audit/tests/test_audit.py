"""Slice 7: audit log and support access."""

from datetime import timedelta
from io import StringIO

import psycopg
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import InternalError
from django.utils import timezone

from accounts.models import Membership, RoleAssignment
from audit.models import AuditEvent, SupportGrant
from schools.models import Student
from schools.tests.conftest import A, B, activate, make_account, member, post, sign_in
from schools.tests.factories import make_student
from tenancy.rls import school_scope
from tenancy.tests.conftest import owner_role

pytestmark = pytest.mark.usefixtures("as_app_role")


def events(school, **filters):
    with school_scope(school.pk):
        return list(AuditEvent.objects.filter(**filters).order_by("id"))


def board_client(schools):
    member(schools[0], make_account("board@example.com", display_name="Board"), "principal_board")
    return sign_in(A, "board@example.com")


def test_a_role_change_is_logged_with_its_actor_and_changed_columns(admin, admin_a, alice, schools):
    with school_scope(schools[0].pk):
        role = RoleAssignment.objects.get(membership__account=alice)
        me = Membership.objects.get(account=admin_a)
    today = timezone.localdate().isoformat()
    path = f"/api/setup/role-assignments/{role.pk}/"
    response = admin.patch(path, {"valid_to": today}, content_type="application/json", HTTP_HOST=A)
    assert response.status_code == 200, response.json()
    (event,) = events(schools[0], target_table="accounts_roleassignment", action="update")
    assert (event.actor, event.actor_membership_id, event.target_id) == ("member", me.pk, role.pk)
    assert event.details == {"valid_to": [None, today]}
    # The same value again changes nothing and logs nothing.
    admin.patch(path, {"valid_to": today}, content_type="application/json", HTTP_HOST=A)
    assert len(events(schools[0], target_table="accounts_roleassignment", action="update")) == 1


def test_activation_is_logged_without_the_code(admin, setup, schools):
    body = {
        "kind": "guardian",
        "student": setup["an"].pk,
        "relation": "mother",
        "display_name": "M",
    }
    code = post(admin, A, "setup/invitations/", body).json()["code"]
    assert activate(A, code, "0987654321")[1].status_code == 200
    issued, accepted = events(schools[0], target_table="accounts_invitation")
    assert issued.action == "insert" and "code_digest" not in issued.details
    assert (accepted.actor, accepted.details["status"]) == ("activation", ["pending", "accepted"])
    assert events(schools[0], target_table="schools_guardianlink", action="insert")


def test_nothing_writes_edits_or_deletes_an_entry_but_the_functions(app_conn, schools):
    with school_scope(schools[0].pk):
        Student.objects.create(  # as the app role: the trigger still writes the entry
            school=schools[0], full_name="X", date_of_birth="2012-01-01", gender="male"
        )
    assert events(schools[0], target_table="schools_student")
    app_conn.execute("BEGIN")
    app_conn.execute("SELECT set_config('app.school_id', %s, true)", [str(schools[0].pk)])
    for sql in (
        "INSERT INTO audit_auditevent (school_id, at, actor, action, target_table, details)"
        f" VALUES ({schools[0].pk}, now(), 'x', 'x', '', '{{}}')",
        "UPDATE audit_auditevent SET actor = 'x'",
        "DELETE FROM audit_auditevent",
    ):
        app_conn.execute("SAVEPOINT s")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app_conn.execute(sql)
        app_conn.execute("ROLLBACK TO SAVEPOINT s")
    app_conn.execute("ROLLBACK")


def test_an_import_preview_leaves_no_entries(admin, setup, schools):
    from schools.tests.test_imports import upload, xlsx

    before = len(events(schools[0]))
    rows = [["HS2", None, "Em", "01/02/2013", "Nữ", "7A", None]]
    assert upload(admin, "students", xlsx("students", rows), setup["year"]).status_code == 201
    assert len(events(schools[0])) == before


def test_a_full_student_view_is_logged_and_a_list_is_not(admin, schools):
    with school_scope(schools[0].pk):
        student = make_student(schools[0], national_id="079212000001")
    admin.get("/api/setup/students/", HTTP_HOST=A)
    assert not events(schools[0], action="student.view_sensitive")
    admin.get(f"/api/setup/students/{student.pk}/", HTTP_HOST=A)
    (event,) = events(schools[0], action="student.view_sensitive")
    assert (event.target_table, event.target_id) == ("schools_student", student.pk)


def test_who_reads_the_log_and_only_their_schools(admin, alice, admin_b, schools):
    response = admin.get("/api/setup/audit-events/?target_table=accounts_membership", HTTP_HOST=A)
    assert response.status_code == 200
    rows = response.json()["results"]
    assert rows and {r["target_table"] for r in rows} == {"accounts_membership"}
    assert board_client(schools).get("/api/setup/audit-events/", HTTP_HOST=A).status_code == 200
    teacher = sign_in(A, "alice@example.com")
    assert teacher.get("/api/setup/audit-events/", HTTP_HOST=A).status_code == 403
    with school_scope(schools[0].pk):
        ids_a = set(AuditEvent.objects.values_list("id", flat=True))
    client_b = sign_in(B, "admin-b@example.com")
    ids_b = {
        r["id"] for r in client_b.get("/api/setup/audit-events/", HTTP_HOST=B).json()["results"]
    }
    assert ids_b and not ids_a & ids_b


def grant(client, hours=2):
    return post(client, A, "setup/support-grants/", {"hours": hours, "reason": "ticket 12"})


def test_grants_are_issued_bounded_revoked_and_logged(admin, alice, schools):
    assert grant(admin, hours=73).json() == {
        "hours": ["Ensure this value is less than or equal to 72."]
    }
    response = grant(board_client(schools))
    assert response.status_code == 201 and response.json()["in_force"]
    teacher = sign_in(A, "alice@example.com")
    assert grant(teacher).status_code == 403
    path = f"setup/support-grants/{response.json()['id']}/revoke/"
    assert post(admin, A, path).json()["in_force"] is False
    assert post(admin, A, path).json() == {"status": ["not_in_force"]}
    logged = events(schools[0], target_table="audit_supportgrant")
    assert [e.action for e in logged] == ["insert", "update"]


def support(command, school="a"):
    out = StringIO()
    call_command("support_session", school=school, operator="Op", command=command, stdout=out)
    return out


def test_support_session_needs_a_grant_in_force(admin, schools):
    with pytest.raises(CommandError, match="No support grant"):
        support("print(1)")
    grant(admin, hours=1)
    with school_scope(schools[0].pk):
        now = timezone.now()
        SupportGrant.objects.update(starts_at=now - timedelta(hours=2), ends_at=now)
    with pytest.raises(CommandError, match="No support grant"):
        support("print(1)")


def test_support_session_reads_only_and_logs_every_command(admin, schools, capsys):
    grant(admin)
    support("print(models['Student'].objects.count())")
    assert capsys.readouterr().out.strip() == "0"
    with pytest.raises(InternalError) as refused:
        support(f"models['Room'].objects.create(school_id={schools[0].pk}, name='x')")
    assert isinstance(refused.value.__cause__, psycopg.errors.ReadOnlySqlTransaction)
    logged = [(e.action, e.actor) for e in events(schools[0], action__startswith="support.")]
    assert (
        logged
        == [
            ("support.session_start", "operator:Op"),
            ("support.command", "operator:Op"),
            ("support.session_end", "operator:Op"),
        ]
        * 2
    )
    assert events(schools[0], action="support.command")[1].details["source"].startswith("models")


def test_support_session_refuses_the_owner_role(admin, schools):
    grant(admin)
    with owner_role(), pytest.raises(CommandError, match="app role"):
        support("print(1)")
