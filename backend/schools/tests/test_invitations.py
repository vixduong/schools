"""Slice 6a: invitations, activation, membership lifecycle."""

import ast
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from accounts.models import Account, Invitation, Membership, RoleAssignment
from schools.models import GuardianLink, Student, Subject
from tenancy.rls import school_scope

from .conftest import (
    INVALID,
    PASSWORD,
    A,
    B,
    activate,
    make_account,
    member,
    owner_role,
    post,
    sign_in,
)
from .factories import make_subject

pytestmark = pytest.mark.usefixtures("as_app_role")


def staff_invitation(admin, setup, identifier="teacher@example.com", **role):
    role = role or {
        "role": "homeroom_teacher",
        "school_year": setup["year"].pk,
        "school_class": setup["7B"].pk,
        "valid_from": str(timezone.localdate()),
    }
    body = {"kind": "staff", "identifier": identifier, "display_name": "Co Lan", "roles": [role]}
    return post(admin, A, "setup/invitations/", body)


def test_a_new_person_activates_a_staff_invitation_and_lands_in_the_role(admin, setup, schools):
    issued = staff_invitation(admin, setup, identifier=" Teacher@Example.com ")
    assert issued.status_code == 201, issued.json()
    body = issued.json()
    assert body["identifier"] == "teacher@example.com" and body["status"] == "pending"
    assert len(body["code"]) == 11  # XXXXX-XXXXX
    with school_scope(schools[0].pk):
        stored = Invitation.objects.get(pk=body["id"])
    assert body["code"] not in stored.code_digest  # only a digest is kept

    client, response = activate(A, body["code"].lower().replace("-", " "), "teacher@example.com")
    assert response.status_code == 200, response.json()
    assert response.json()["account"]["display_name"] == "Co Lan"  # the invitation's name
    assert [r["role"] for r in response.json()["role_assignments"]] == ["homeroom_teacher"]
    assert client.get("/api/auth/me/", HTTP_HOST=A).status_code == 200  # signed in
    with school_scope(schools[0].pk):
        stored.refresh_from_db()
        assert stored.status == "accepted"
        assert stored.accepted_membership.account.email == "teacher@example.com"
    assert activate(A, body["code"], "teacher@example.com")[1].json() == INVALID  # once only


def test_an_existing_account_links_with_its_own_password_and_is_never_reset(
    admin_b, alice, setup, schools
):
    admin = sign_in(B, "admin-b@example.com")
    code = post(
        admin,
        B,
        "setup/invitations/",
        {"kind": "staff", "identifier": "0912345678", "display_name": "Alice", "roles": []},
    ).json()["code"]
    assert activate(B, code, "0912345678", "not her password")[1].json() == INVALID
    _, response = activate(B, code, "+84 912 345 678", PASSWORD, display_name="Renamed")
    assert response.status_code == 200, response.json()
    alice.refresh_from_db()
    assert alice.check_password(PASSWORD) and alice.display_name == "Alice"
    with school_scope(schools[1].pk):
        assert Membership.objects.filter(account=alice).exists()


def test_every_bad_code_gives_the_same_error(admin, setup, schools):
    def issue(identifier="x@example.com"):
        return staff_invitation(admin, setup, identifier=identifier).json()

    revoked, expired, used, bound = issue(), issue(), issue(), issue("bound@example.com")
    post(admin, A, f"setup/invitations/{revoked['id']}/revoke/")
    with school_scope(schools[0].pk):
        Invitation.objects.filter(pk=expired["id"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
    assert activate(A, used["code"], "x@example.com")[1].status_code == 200
    for code, identifier in (
        ("AAAAA-AAAAA", "x@example.com"),
        (revoked["code"], "x@example.com"),
        (expired["code"], "x@example.com"),
        (used["code"], "x@example.com"),
        (bound["code"], "other@example.com"),
    ):
        _, response = activate(A, code, identifier)
        assert (response.status_code, response.json()) == (400, INVALID)
    # Another School's code means nothing here.
    assert activate(B, bound["code"], "bound@example.com")[1].json() == INVALID
    assert admin.get(f"/api/setup/invitations/{expired['id']}/", HTTP_HOST=A).json()["status"] == (
        "expired"
    )


def test_a_new_account_needs_a_real_password(admin, setup):
    code = staff_invitation(admin, setup).json()["code"]
    _, response = activate(A, code, "teacher@example.com", password="1234567")
    assert list(response.json()) == ["password"]
    assert activate(A, code, "teacher@example.com")[1].status_code == 200  # code still usable


def test_a_rule_failing_at_acceptance_writes_nothing(admin, setup, schools):
    with school_scope(schools[0].pk):
        subject = make_subject(schools[0], "LIT")
    role = {
        "role": "subject_teacher",
        "school_year": setup["year"].pk,
        "school_class": setup["7A"].pk,
        "subject": subject.pk,
        "valid_from": str(timezone.localdate()),
    }
    code = staff_invitation(admin, setup, **role).json()["code"]
    with school_scope(schools[0].pk):
        subject.is_active = False
        subject.save()
    accounts = Account.objects.count()
    _, response = activate(A, code, "teacher@example.com")
    assert response.json() == {"invitation": ["cannot_apply"]}
    assert Account.objects.count() == accounts
    with school_scope(schools[0].pk):
        assert Invitation.objects.get().status == "pending"


def test_issue_time_checks(admin, setup):
    no_subject = staff_invitation(
        admin,
        setup,
        role="subject_teacher",
        school_year=setup["year"].pk,
        school_class=setup["7A"].pk,
        valid_from=str(timezone.localdate()),
    )
    assert no_subject.json() == {"constraint": ["invitationrole_scope_matches_role"]}
    wrong_scope = staff_invitation(
        admin, setup, role="school_admin", school_class=setup["7A"].pk, valid_from="2026-01-01"
    )
    assert wrong_scope.json() == {"constraint": ["invitationrole_scope_matches_role"]}
    primary = post(
        admin,
        A,
        "setup/invitations/",
        {"kind": "student", "display_name": "Chi", "student": setup["chi"].pk},
    )
    assert primary.json() == {"student": ["student_not_secondary"]}
    guardian = post(
        admin,
        A,
        "setup/invitations/",
        {"kind": "guardian", "display_name": "Me An", "student": setup["an"].pk, "roles": []},
    )
    assert guardian.json() == {"relation": ["required"]}
    bad_identifier = staff_invitation(admin, setup, identifier="0123")
    assert bad_identifier.json() == {"identifier": ["invalid_identifier"]}


def test_inactive_subject_is_refused_at_issue(admin, setup, schools):
    with school_scope(schools[0].pk):
        retired = Subject.objects.get(code="OLD")
    response = staff_invitation(
        admin,
        setup,
        role="subject_teacher",
        school_year=setup["year"].pk,
        school_class=setup["7A"].pk,
        subject=retired.pk,
        valid_from=str(timezone.localdate()),
    )
    assert response.json() == {"roles": {"0": {"subject": ["subject_inactive"]}}}


def test_homeroom_teacher_invites_guardians_of_own_class_only(alice, setup, schools):
    teacher = sign_in(A, "alice@example.com")

    def invite(kind, student, **extra):
        body = {"kind": kind, "display_name": "Me", "student": student.pk, **extra}
        return post(teacher, A, "setup/invitations/", body)

    printed = invite("guardian", setup["an"], relation="mother")
    assert printed.status_code == 201, printed.json()
    assert invite("guardian", setup["binh"], relation="mother").status_code == 403
    assert staff_invitation(teacher, setup).status_code == 403
    listed = teacher.get("/api/setup/invitations/", HTTP_HOST=A).json()
    assert [i["student_name"] for i in listed] == ["An"]

    # A printed code has no identifier: whoever holds it activates with their own phone.
    _, response = activate(A, printed.json()["code"], "0987654321", display_name="Me An")
    assert response.status_code == 200, response.json()
    with school_scope(schools[0].pk):
        link = GuardianLink.objects.get()
        assert (link.student, link.relation, link.valid_from) == (
            setup["an"],
            "mother",
            timezone.localdate(),
        )


def test_student_invitation_gives_the_student_their_sign_in(alice, setup, schools):
    teacher = sign_in(A, "alice@example.com")
    issued = post(
        teacher,
        A,
        "setup/invitations/",
        {"kind": "student", "display_name": "An", "student": setup["an"].pk},
    )
    assert issued.status_code == 201, issued.json()
    _, response = activate(A, issued.json()["code"], "an@example.com")
    assert response.status_code == 200, response.json()
    with school_scope(schools[0].pk):
        assert Student.objects.get(pk=setup["an"].pk).membership.account.email == "an@example.com"
    again = post(
        teacher,
        A,
        "setup/invitations/",
        {"kind": "student", "display_name": "An", "student": setup["an"].pk},
    )
    assert again.json() == {"student": ["student_has_membership"]}


def test_revoke_and_who_may(admin, setup, schools):
    board = make_account("board@example.com", display_name="Board")
    member(schools[0], board, RoleAssignment.Role.PRINCIPAL_BOARD)
    invitation = staff_invitation(admin, setup).json()
    board_client = sign_in(A, "board@example.com")
    assert [i["id"] for i in board_client.get("/api/setup/invitations/", HTTP_HOST=A).json()] == [
        invitation["id"]
    ]
    path = f"setup/invitations/{invitation['id']}/revoke/"
    assert post(board_client, A, path).status_code == 403
    assert post(admin, A, path).json()["status"] == "revoked"
    assert post(admin, A, path).json() == {"status": ["not_pending"]}
    assert activate(A, invitation["code"], "teacher@example.com")[1].json() == INVALID


def test_printing_a_class_list_issues_fresh_codes(alice, setup, schools):
    teacher = sign_in(A, "alice@example.com")
    first = post(
        teacher,
        A,
        "setup/invitations/",
        {
            "kind": "guardian",
            "display_name": "Bo An",
            "student": setup["an"].pk,
            "relation": "father",
        },
    ).json()
    printed = post(teacher, A, "setup/invitations/print/", {"school_class": setup["7A"].pk})
    assert printed.status_code == 200, printed.json()
    (row,) = printed.json()
    assert (row["student_name"], row["relation"], row["id"]) == ("An", "father", first["id"])
    assert row["code"] != first["code"] and row["expires_at"]
    assert activate(A, first["code"], "0987654321")[1].json() == INVALID
    assert activate(A, row["code"], "0987654321")[1].status_code == 200
    other = post(teacher, A, "setup/invitations/print/", {"school_class": setup["7B"].pk})
    assert other.status_code == 403


def test_deactivating_ends_roles_and_links_and_cuts_access(admin, alice, setup, schools):
    a = schools[0]
    teacher = sign_in(A, "alice@example.com")
    with school_scope(a.pk):
        membership = Membership.objects.get(account=alice)
        GuardianLink.objects.create(
            school=a,
            membership=membership,
            student=setup["binh"],
            relation="mother",
            valid_from=timezone.localdate() - timedelta(days=3),
        )
    response = post(admin, A, f"setup/memberships/{membership.pk}/deactivate/")
    assert response.json()["status"] == "inactive", response.json()
    assert teacher.get("/api/auth/me/", HTTP_HOST=A).status_code == 403
    today = timezone.localdate()
    with school_scope(a.pk):
        assert {r.valid_to for r in RoleAssignment.objects.filter(membership=membership)} == {today}
        assert GuardianLink.objects.get(membership=membership).valid_to == today
    response = post(admin, A, f"setup/memberships/{membership.pk}/reactivate/")
    assert response.json()["status"] == "active"
    with school_scope(a.pk):
        assert not RoleAssignment.objects.in_force(today + timedelta(days=1)).filter(
            membership=membership
        )


def test_the_last_school_admin_cannot_be_deactivated(admin, admin_a, schools):
    with school_scope(schools[0].pk):
        membership = Membership.objects.get(account=admin_a)
    response = post(admin, A, f"setup/memberships/{membership.pk}/deactivate/")
    assert response.json() == {"status": ["last_school_admin"]}
    with school_scope(schools[0].pk):
        membership.refresh_from_db()
        assert membership.status == "active"


def test_the_board_reads_memberships_but_cannot_deactivate(admin, alice, schools):
    board = make_account("board@example.com", display_name="Board")
    member(schools[0], board, RoleAssignment.Role.PRINCIPAL_BOARD)
    client = sign_in(A, "board@example.com")
    listed = client.get("/api/setup/memberships/", HTTP_HOST=A).json()
    assert {m["display_name"] for m in listed} == {"Admin A", "Alice", "Board"}
    assert "email" not in listed[0]
    alice_id = next(m["id"] for m in listed if m["display_name"] == "Alice")
    assert post(client, A, f"setup/memberships/{alice_id}/deactivate/").status_code == 403


ACCOUNT_CREATORS = {"accounts/views.py", "accounts/management/commands/create_dev_school.py"}


def test_only_activation_and_the_dev_command_create_accounts():
    """A School never creates an Account; only the person's activation does (and the owner-role
    dev command). Flags any `Account(...)` or `Account.objects.<create>` outside those files."""
    root = Path(settings.BASE_DIR)
    found = set()
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if "/tests/" in rel or "/migrations/" in rel or rel.startswith(".venv"):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            text = ast.unparse(node.func)
            if (
                text == "Account"
                or text.startswith("Account.objects.")
                and any(word in text for word in ("create", "bulk_"))
            ):
                found.add(rel)
    assert found == ACCOUNT_CREATORS


def test_an_admin_redeeming_their_own_principal_board_invitation_waits_for_confirmation(
    admin, admin_a, setup, schools
):
    code = staff_invitation(
        admin, setup, identifier="", role="principal_board", valid_from="2026-01-01"
    ).json()["code"]
    _, response = activate(A, code, "admin-a@example.com", PASSWORD)
    assert response.status_code == 200, response.json()
    assert "principal_board" not in [r["role"] for r in response.json()["role_assignments"]]
    with school_scope(schools[0].pk):
        row = RoleAssignment.objects.get(role="principal_board")
        assert (row.status, row.requested_by.account) == ("pending_confirmation", admin_a)


def test_a_blank_identifier_is_a_printed_code(admin, setup):
    issued = staff_invitation(admin, setup, identifier="").json()
    assert issued["identifier"] is None
    _, response = activate(A, issued["code"], "0987654321", display_name="")
    assert response.status_code == 200, response.json()
    assert response.json()["account"]["display_name"] == "Co Lan"


def test_an_existing_account_and_a_new_identifier_answer_alike(admin, alice, setup):
    code = staff_invitation(admin, setup, identifier="").json()["code"]
    weak = [
        activate(A, code, who, password="1")[1].json() for who in ("alice@example.com", "n@x.vn")
    ]
    assert list(weak[0]) == list(weak[1]) == ["password"]


def test_an_inactive_account_cannot_activate(admin, alice, setup):
    code = staff_invitation(admin, setup, identifier="alice@example.com").json()["code"]
    with owner_role():
        Account.objects.filter(pk=alice.pk).update(is_active=False)
    assert activate(A, code, "alice@example.com", PASSWORD)[1].json() == INVALID


def test_only_a_staff_invitation_takes_an_inactive_member_back(admin, alice, setup, schools):
    with school_scope(schools[0].pk):
        membership = Membership.objects.get(account=alice)
    post(admin, A, f"setup/memberships/{membership.pk}/deactivate/")
    guardian = post(
        admin,
        A,
        "setup/invitations/",
        {
            "kind": "guardian",
            "display_name": "Alice",
            "student": setup["binh"].pk,
            "relation": "mother",
        },
    ).json()["code"]
    assert activate(A, guardian, "alice@example.com", PASSWORD)[1].json() == {
        "invitation": ["cannot_apply"]
    }
    staff = staff_invitation(admin, setup, identifier="alice@example.com").json()["code"]
    _, response = activate(A, staff, "alice@example.com", PASSWORD)
    assert response.status_code == 200, response.json()
    with school_scope(schools[0].pk):
        membership.refresh_from_db()
        assert membership.status == "active"


def test_a_second_student_invitation_cannot_replace_the_sign_in(admin, setup):
    def invite():
        body = {"kind": "student", "display_name": "An", "student": setup["an"].pk}
        return post(admin, A, "setup/invitations/", body).json()["code"]

    first, second = invite(), invite()
    assert activate(A, first, "an@example.com")[1].status_code == 200
    assert activate(A, second, "an2@example.com")[1].json() == {"invitation": ["cannot_apply"]}


def test_deactivating_ends_a_future_role_on_its_first_day(admin, alice, setup, schools):
    start = timezone.localdate() + timedelta(days=10)
    with school_scope(schools[0].pk):
        membership = Membership.objects.get(account=alice)
        future = RoleAssignment.objects.create(
            school=schools[0],
            membership=membership,
            role="subject_teacher",
            school_year=setup["year"],
            school_class=setup["7B"],
            subject=make_subject(schools[0], "LIT"),
            valid_from=start,
        )
    post(admin, A, f"setup/memberships/{membership.pk}/deactivate/")
    with school_scope(schools[0].pk):
        future.refresh_from_db()
        assert future.valid_to == start


def test_an_outsider_learns_nothing_about_a_student_before_the_refusal(alice, setup):
    teacher = sign_in(A, "alice@example.com")
    body = {"kind": "student", "display_name": "Chi", "student": setup["chi"].pk}
    assert post(teacher, A, "setup/invitations/", body).status_code == 403
