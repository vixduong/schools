import json
from datetime import date, timedelta
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.models import Membership, RoleAssignment
from schools.models import (
    AssessmentProfileVersion,
    Enrollment,
    Grade,
    Level,
    Room,
    SchoolClass,
    SchoolYear,
    Student,
    StudentStatusEvent,
    Subject,
)
from tenancy.rls import school_scope
from testing import PASSWORD, make_account, member, owner_role

from .factories import (
    make_class,
    make_group,
    make_primary_class,
    make_student,
    make_subject,
)

pytestmark = pytest.mark.usefixtures("as_app_role")

A, B = "a.localhost", "b.localhost"
ENDPOINTS = [
    "school-years",
    "terms",
    "levels",
    "grades",
    "subject-groups",
    "subjects",
    "rooms",
    "classes",
    "role-assignments",
    "students",
    "enrollments",
    "guardian-links",
]


def url(name, pk=None):
    return f"/api/setup/{name}/" + (f"{pk}/" if pk else "")


def sign_in(client, host, email):
    response = client.post(
        "/api/auth/login/", {"identifier": email, "password": PASSWORD}, HTTP_HOST=host
    )
    assert response.status_code == 200
    return client


def post(client, host, name, body):
    return client.post(url(name), body, content_type="application/json", HTTP_HOST=host)


def patch(client, host, name, pk, body):
    return client.patch(url(name, pk), body, content_type="application/json", HTTP_HOST=host)


@pytest.fixture
def admin(client, admin_a):
    return sign_in(client, A, "admin-a@example.com")


def test_school_admin_sets_up_a_year_end_to_end(admin, alice, schools):
    a, _ = schools
    year = post(
        admin,
        A,
        "school-years",
        {"name": "2040-2041", "starts_on": "2040-09-01", "ends_on": "2041-08-31"},
    )
    assert year.status_code == 201, year.json()
    year = year.json()
    assert "school" not in year  # the School comes from the host, never from the body

    term = post(
        admin,
        A,
        "terms",
        {
            "school_year": year["id"],
            "name": "HK I",
            "starts_on": "2040-09-01",
            "ends_on": "2041-01-15",
        },
    )
    level = post(admin, A, "levels", {"kind": "primary"}).json()
    grade = post(admin, A, "grades", {"level": level["id"], "number": 3}).json()
    group = post(admin, A, "subject-groups", {"name": "Toán"}).json()
    subject = post(
        admin, A, "subjects", {"name": "Toán", "code": "MATH", "subject_group": group["id"]}
    ).json()
    room = post(admin, A, "rooms", {"name": "P101"}).json()
    klass = post(
        admin,
        A,
        "classes",
        {"school_year": year["id"], "grade": grade["id"], "name": "3A", "room": room["id"]},
    ).json()
    assert term.status_code == 201
    assert subject["assessment"] == "scored" and subject["is_active"] is True

    with school_scope(a.pk):
        membership = Membership.objects.get(account=alice)
    teaching = post(
        admin,
        A,
        "role-assignments",
        {
            "membership": membership.pk,
            "role": "subject_teacher",
            "school_year": year["id"],
            "subject": subject["id"],
            "school_class": klass["id"],
            "valid_from": "2040-09-01",
        },
    )
    assert teaching.status_code == 201, teaching.json()

    assert [r["name"] for r in admin.get(url("classes"), HTTP_HOST=A).json()] == ["7A", "3A"]
    assert admin.get(url("classes", klass["id"]), HTTP_HOST=A).json()["room"] == room["id"]
    # Deactivate instead of delete; rename; reassign.
    assert patch(admin, A, "rooms", room["id"], {"is_active": False}).json()["is_active"] is False
    assert patch(admin, A, "subjects", subject["id"], {"is_active": False}).status_code == 200
    assert patch(admin, A, "classes", klass["id"], {"room": None}).json()["room"] is None
    put = admin.put(
        url("rooms", room["id"]),
        {"name": "P102", "is_active": True},
        content_type="application/json",
        HTTP_HOST=A,
    )
    assert put.json()["name"] == "P102"


@pytest.mark.parametrize("name", ENDPOINTS)
def test_no_endpoint_deletes(admin, name):
    assert admin.delete(url(name, 1), HTTP_HOST=A).status_code == 405


@pytest.mark.parametrize("name", ENDPOINTS)
def test_a_member_without_the_school_admin_role_gets_403(client, alice, name):
    """Alice is a homeroom teacher: HasMembership passes, IsSchoolAdmin does not."""
    sign_in(client, A, "alice@example.com")
    assert client.get(url(name), HTTP_HOST=A).status_code == 403
    assert client.get(url(name, 1), HTTP_HOST=A).status_code == 403
    assert post(client, A, name, {}).status_code == 403
    assert patch(client, A, name, 1, {}).status_code == 403


def test_setup_endpoints_refuse_anonymous_requests(client, schools):
    assert client.get(url("classes"), HTTP_HOST=A).status_code == 403


def test_a_school_admin_whose_role_ended_loses_access(admin, schools):
    with school_scope(schools[0].pk):
        RoleAssignment.objects.update(valid_to=timezone.localdate() - timedelta(days=1))
    assert admin.get(url("classes"), HTTP_HOST=A).status_code == 403


def test_school_b_cannot_see_or_touch_school_a_classes(client, admin_a, admin_b, schools):
    a, b = schools
    with school_scope(a.pk):
        klass = make_class(a)
        year_a = klass.school_year_id
        grade_a = klass.grade_id
    sign_in(client, B, "admin-b@example.com")
    assert client.get(url("classes"), HTTP_HOST=B).json() == []
    assert client.get(url("classes", klass.pk), HTTP_HOST=B).status_code == 404
    assert patch(client, B, "classes", klass.pk, {"name": "hacked"}).status_code == 404
    # Referencing A's year and grade from B fails validation: B cannot even see them.
    cross = post(client, B, "classes", {"school_year": year_a, "grade": grade_a, "name": "9Z"})
    assert cross.status_code == 400
    with school_scope(a.pk):
        assert SchoolClass.objects.get(pk=klass.pk).name == "7A"


def test_a_rule_only_the_database_checks_answers_400_with_the_constraint(admin):
    year = {"name": "2040-2041", "starts_on": "2040-09-01", "ends_on": "2041-08-31"}
    pk = post(admin, A, "school-years", year).json()["id"]
    overlap = post(
        admin,
        A,
        "school-years",
        {**year, "name": "x", "starts_on": "2041-08-31", "ends_on": "2042-08-31"},
    )
    assert overlap.status_code == 400
    assert overlap.json() == {"constraint": ["schoolyear_no_overlap"]}
    outside = post(
        admin,
        A,
        "terms",
        {"school_year": pk, "name": "HK I", "starts_on": "2040-08-01", "ends_on": "2041-01-01"},
    )
    assert outside.json() == {"constraint": ["term_inside_school_year"]}
    # The failed insert did not poison the request transaction.
    assert len(admin.get(url("school-years"), HTTP_HOST=A).json()) == 1


def test_duplicate_subject_code_is_a_field_error(admin):
    body = {"name": "Toán", "code": "MATH"}
    assert post(admin, A, "subjects", body).status_code == 201
    again = post(admin, A, "subjects", body)
    assert again.status_code == 400
    assert "code" in str(again.json()) or "non_field_errors" in again.json()


def test_role_ends_and_resumes_through_the_api(admin, alice, schools):
    a, _ = schools
    with school_scope(a.pk):
        klass = make_class(a, name="7B")
        membership = Membership.objects.get(account=alice)
        year = klass.school_year
    base = {
        "membership": membership.pk,
        "role": "homeroom_teacher",
        "school_year": year.pk,
        "school_class": klass.pk,
    }
    today = timezone.localdate()
    first = post(
        admin, A, "role-assignments", {**base, "valid_from": str(today - timedelta(days=20))}
    ).json()
    # Alice is already homeroom teacher of 7A from the fixture; 7B overlaps nothing.
    ended = patch(
        admin, A, "role-assignments", first["id"], {"valid_to": str(today - timedelta(days=10))}
    )
    assert ended.status_code == 200
    # Scope and role cannot be rewritten afterwards.
    rewrite = patch(
        admin, A, "role-assignments", first["id"], {"role": "principal_board", "school_class": None}
    )
    assert rewrite.status_code == 400
    assert rewrite.json() == {"role": ["immutable"], "school_class": ["immutable"]}
    resumed = post(
        admin, A, "role-assignments", {**base, "valid_from": str(today - timedelta(days=5))}
    )
    assert resumed.status_code == 201
    overlapping = post(admin, A, "role-assignments", {**base, "valid_from": str(today)})
    assert overlapping.json() == {"constraint": ["roleassignment_no_overlapping_periods"]}


def test_student_and_guardian_are_no_role_assignments(admin, alice, schools):
    """Their rights come from Student.membership + Enrollment and from GuardianLink."""
    a, _ = schools
    with school_scope(a.pk):
        membership = Membership.objects.get(account=alice)
    for role in ("student", "guardian"):
        response = post(
            admin,
            A,
            "role-assignments",
            {"membership": membership.pk, "role": role, "valid_from": "2026-09-01"},
        )
        assert response.status_code == 400 and list(response.json()) == ["role"]


def test_openapi_schema_is_valid():
    call_command(
        "spectacular", "--validate", "--fail-on-warn", stdout=StringIO(), stderr=StringIO()
    )


def test_committed_schema_matches_the_api():
    """The SPA's contract (frontend/src/api/openapi.json) is regenerated with the API: run
    `make api-client` and review the diff."""
    out = StringIO()
    call_command("spectacular", "--format", "openapi-json", stdout=out, stderr=StringIO())
    committed = Path(__file__).resolve().parents[3] / "frontend/src/api/openapi.json"
    assert json.loads(committed.read_text()) == json.loads(out.getvalue()), "run make api-client"


# --- Fixes from the slice 4a review -------------------------------------------------------------

Role = RoleAssignment.Role
Status = RoleAssignment.Status


def assignment_of(school, email, role):
    with school_scope(school.pk):
        return RoleAssignment.objects.get(membership__account__email=email, role=role)


def second_admin(school, email="admin2@example.com"):
    """Another School admin, in force since a month. Returns their Membership."""
    return member(school, make_account(email), Role.SCHOOL_ADMIN)


def test_a_class_never_moves_to_another_year_or_grade(admin, schools):
    a, _ = schools
    with school_scope(a.pk):
        klass = make_class(a)
        other_grade = Grade.objects.create(school=a, level=klass.grade.level, number=8)
        other_year = SchoolYear.objects.create(
            school=a, name="other", starts_on="2090-09-01", ends_on="2091-05-31"
        )
    refused = patch(
        admin,
        A,
        "classes",
        klass.pk,
        {"name": "7Z", "grade": other_grade.pk, "school_year": other_year.pk},
    )
    assert refused.status_code == 400
    assert refused.json() == {"grade": ["immutable"], "school_year": ["immutable"]}
    # Sending the stored values back is fine, and the rest of the row still changes.
    same = {"name": "7Z", "grade": klass.grade_id, "school_year": klass.school_year_id}
    changed = patch(admin, A, "classes", klass.pk, same)
    assert changed.status_code == 200 and changed.json()["name"] == "7Z"


def test_a_grade_never_changes_number_or_level(admin, schools):
    a, _ = schools
    with school_scope(a.pk):
        grade = make_class(a).grade
        other_level = Level.objects.create(school=a, kind=Level.Kind.PRIMARY)
    refused = patch(admin, A, "grades", grade.pk, {"number": 3, "level": other_level.pk})
    assert refused.status_code == 400
    assert refused.json() == {"number": ["immutable"], "level": ["immutable"]}
    same = {"number": grade.number, "level": grade.level_id}
    assert patch(admin, A, "grades", grade.pk, same).status_code == 200


def test_inactive_rooms_subjects_and_memberships_are_no_new_targets(admin, alice, schools):
    a, _ = schools
    ghost = member(a, make_account("ghost@example.com"))  # opens its own scope
    with school_scope(a.pk):
        klass = make_class(a, name="7B")
        room = Room.objects.create(school=a, name="old", is_active=False)
        subject = make_subject(a)
        Subject.objects.filter(pk=subject.pk).update(is_active=False)
        teacher = Membership.objects.get(account=alice)
        Membership.objects.filter(pk=ghost.pk).update(status=Membership.Status.INACTIVE)
        year = klass.school_year_id
    new_class = {"school_year": year, "grade": klass.grade_id, "name": "7C", "room": room.pk}
    assert post(admin, A, "classes", new_class).json() == {"room": ["room_inactive"]}
    assert patch(admin, A, "classes", klass.pk, {"room": room.pk}).status_code == 400
    with school_scope(a.pk):
        SchoolClass.objects.filter(pk=klass.pk).update(room=room)
    assert patch(admin, A, "classes", klass.pk, {"name": "7D"}).status_code == 200  # keeps its room
    base = {"role": "subject_teacher", "school_year": year, "school_class": klass.pk}
    base["valid_from"] = str(timezone.localdate())
    teaching = {**base, "membership": teacher.pk, "subject": subject.pk}
    assert post(admin, A, "role-assignments", teaching).json() == {"subject": ["subject_inactive"]}
    ghost_row = {**teaching, "membership": ghost.pk}
    assert post(admin, A, "role-assignments", ghost_row).json()["membership"] == [
        "membership_inactive"
    ]


def test_a_class_role_needs_a_class_of_its_own_year_through_the_api(admin, alice, schools):
    a, _ = schools
    with school_scope(a.pk):
        klass = make_class(a, name="7B")
        other_year = SchoolYear.objects.create(
            school=a, name="other", starts_on="2090-09-01", ends_on="2091-05-31"
        )
        teacher = Membership.objects.get(account=alice).pk
    body = {
        "membership": teacher,
        "role": "homeroom_teacher",
        "school_class": klass.pk,
        "valid_from": "2090-09-01",
    }
    refused = post(admin, A, "role-assignments", {**body, "school_year": other_year.pk})
    assert refused.json() == {"constraint": ["accounts_roleassignment_school_class_in_school_year"]}
    assert (
        post(
            admin, A, "role-assignments", {**body, "school_year": klass.school_year_id}
        ).status_code
        == 201
    )
    # School-wide roles take no year.
    wide = {"membership": teacher, "role": "group_leader", "valid_from": "2090-09-01"}
    bad = post(admin, A, "role-assignments", {**wide, "school_year": other_year.pk})
    assert bad.json() == {"constraint": ["roleassignment_scope_matches_role"]}


def test_role_history_is_kept(admin, alice, schools):
    a, _ = schools
    today = timezone.localdate()
    row = assignment_of(a, "alice@example.com", Role.HOMEROOM_TEACHER)

    def end(pk, **body):
        return patch(admin, A, "role-assignments", pk, body)

    # valid_from never changes.
    assert end(row.pk, valid_from=str(today)).json() == {"valid_from": ["immutable"]}
    assert end(row.pk, valid_from=str(row.valid_from)).status_code == 200
    # valid_to may not precede valid_from.
    before = end(row.pk, valid_to=str(row.valid_from - timedelta(days=1)))
    assert before.json() == {"valid_to": ["valid_to_before_valid_from"]}
    # An open period can be ended, later moved while still current, but never cleared.
    future = str(today + timedelta(days=10))
    assert end(row.pk, valid_to=future).status_code == 200
    assert end(row.pk, valid_to=str(today + timedelta(days=20))).status_code == 200
    assert end(row.pk, valid_to=None).json() == {"valid_to": ["valid_to_cannot_be_cleared"]}
    # A period that already ended is history: closed.
    with school_scope(a.pk):
        RoleAssignment.objects.filter(pk=row.pk).update(valid_to=today - timedelta(days=1))
    closed = end(row.pk, valid_to=str(today))
    assert closed.json() == {"valid_to": ["period_already_ended"]}
    assert end(row.pk, valid_to=None).json() == {"valid_to": ["valid_to_cannot_be_cleared"]}


def test_the_last_school_admin_cannot_end_their_role(admin, schools):
    a, _ = schools
    mine = assignment_of(a, "admin-a@example.com", Role.SCHOOL_ADMIN)
    yesterday = str(timezone.localdate() - timedelta(days=1))
    refused = patch(admin, A, "role-assignments", mine.pk, {"valid_to": yesterday})
    assert refused.status_code == 400 and refused.json() == {"valid_to": ["last_school_admin"]}
    future = str(timezone.localdate() + timedelta(days=30))
    assert patch(admin, A, "role-assignments", mine.pk, {"valid_to": future}).status_code == 400
    # A second admin who is not in force yet (pending or future-dated) does not unlock it.
    other = second_admin(a)
    theirs = assignment_of(a, "admin2@example.com", Role.SCHOOL_ADMIN)
    with school_scope(a.pk):
        RoleAssignment.objects.filter(pk=theirs.pk).update(
            status=Status.PENDING_CONFIRMATION, requested_by=other
        )
    assert patch(admin, A, "role-assignments", mine.pk, {"valid_to": yesterday}).status_code == 400
    with school_scope(a.pk):
        RoleAssignment.objects.filter(pk=theirs.pk).update(
            status=Status.ACTIVE,
            requested_by=None,
            valid_from=timezone.localdate() + timedelta(days=5),
        )
    assert patch(admin, A, "role-assignments", mine.pk, {"valid_to": yesterday}).status_code == 400
    # Once the second admin is in force, the first can hand over; nobody can end the last one then.
    with school_scope(a.pk):
        RoleAssignment.objects.filter(pk=theirs.pk).update(valid_from=timezone.localdate())
    assert patch(admin, A, "role-assignments", mine.pk, {"valid_to": yesterday}).status_code == 200
    assert admin.get(url("classes"), HTTP_HOST=A).status_code == 403  # the first admin is out now


def test_ending_a_school_admin_row_locks_the_in_force_admin_rows_before_counting(admin, schools):
    """Two admins ending each other's rows at once must serialize on these row locks."""
    a, _ = schools
    second_admin(a)
    theirs = assignment_of(a, "admin2@example.com", Role.SCHOOL_ADMIN)
    yesterday = str(timezone.localdate() - timedelta(days=1))
    with CaptureQueriesContext(connection) as queries:
        patch(admin, A, "role-assignments", theirs.pk, {"valid_to": yesterday})
    locks = [q["sql"] for q in queries if "FOR UPDATE" in q["sql"]]
    assert len(locks) == 1
    assert 'FOR UPDATE OF "accounts_roleassignment"' in locks[0]
    assert 'ORDER BY "accounts_roleassignment"."id"' in locks[0]


def test_ending_another_admins_role_keeps_one_admin_in_force(admin, schools):
    a, _ = schools
    second_admin(a)
    theirs = assignment_of(a, "admin2@example.com", Role.SCHOOL_ADMIN)
    yesterday = str(timezone.localdate() - timedelta(days=1))
    assert (
        patch(admin, A, "role-assignments", theirs.pk, {"valid_to": yesterday}).status_code == 200
    )
    mine = assignment_of(a, "admin-a@example.com", Role.SCHOOL_ADMIN)
    assert patch(admin, A, "role-assignments", mine.pk, {"valid_to": yesterday}).status_code == 400


def test_two_admins_cannot_each_set_a_future_end_on_the_other_and_leave_a_gap(admin, schools):
    a, _ = schools
    second_admin(a)
    second = sign_in(Client(), A, "admin2@example.com")
    mine = assignment_of(a, "admin-a@example.com", Role.SCHOOL_ADMIN)
    theirs = assignment_of(a, "admin2@example.com", Role.SCHOOL_ADMIN)
    today = timezone.localdate()
    soon, later = str(today + timedelta(days=30)), str(today + timedelta(days=60))

    def end(client, row, valid_to):
        return patch(client, A, "role-assignments", row.pk, {"valid_to": valid_to})

    assert end(admin, theirs, soon).status_code == 200  # my open-ended row covers the gap
    # Mine would end the same day as theirs: nobody left after it.
    refused = end(second, mine, soon)
    assert refused.status_code == 400 and refused.json() == {"valid_to": ["last_school_admin"]}
    assert end(second, mine, str(today + timedelta(days=20))).status_code == 200  # theirs outlasts
    # Now theirs may not end before... mine ends sooner, so nothing would cover days 21 to 25.
    shorter = str(today + timedelta(days=25))
    assert end(admin, theirs, shorter).json() == {"valid_to": ["last_school_admin"]}
    # A third admin with a longer period unlocks it.
    second_admin(a, "admin3@example.com")
    third = assignment_of(a, "admin3@example.com", Role.SCHOOL_ADMIN)
    with school_scope(a.pk):
        RoleAssignment.objects.filter(pk=third.pk).update(valid_to=later)
    assert end(admin, theirs, shorter).status_code == 200


def grant_principal_board(client, host, membership_pk):
    return post(
        client,
        host,
        "role-assignments",
        {
            "membership": membership_pk,
            "role": "principal_board",
            "valid_from": str(timezone.localdate()),
        },
    )


def test_an_admin_granting_themselves_principal_board_needs_a_second_person(admin, schools):
    a, _ = schools
    with school_scope(a.pk):
        mine = Membership.objects.get(account__email="admin-a@example.com").pk
    other = second_admin(a)
    granted = grant_principal_board(admin, A, mine)
    assert granted.status_code == 201
    pending = granted.json()
    assert (pending["status"], pending["requested_by"]) == ("pending_confirmation", mine)
    with school_scope(a.pk):
        assert not RoleAssignment.objects.in_force().filter(role=Role.PRINCIPAL_BOARD).exists()
    me = admin.get("/api/auth/me/", HTTP_HOST=A).json()
    assert [r["role"] for r in me["role_assignments"]] == ["school_admin"]
    # The requester cannot confirm their own request.
    confirm = f"{url('role-assignments', pending['id'])}confirm/"
    assert admin.post(confirm, HTTP_HOST=A).status_code == 403
    # A second admin can; the row is then active with who and when.
    second = sign_in(Client(), A, "admin2@example.com")
    done = second.post(confirm, HTTP_HOST=A)
    assert done.status_code == 200, done.json()
    assert (done.json()["status"], done.json()["confirmed_by"]) == ("active", other.pk)
    with school_scope(a.pk):
        assert RoleAssignment.objects.in_force().filter(role=Role.PRINCIPAL_BOARD).exists()
    # Already confirmed: nothing left to confirm.
    assert second.post(confirm, HTTP_HOST=A).json() == {"status": ["not_pending_confirmation"]}


def test_a_principal_board_member_can_confirm(admin, schools):
    a, _ = schools
    with school_scope(a.pk):
        mine = Membership.objects.get(account__email="admin-a@example.com").pk
    member(a, make_account("board@example.com"), Role.PRINCIPAL_BOARD)
    pending = grant_principal_board(admin, A, mine).json()
    confirm = f"{url('role-assignments', pending['id'])}confirm/"
    assert sign_in(Client(), A, "board@example.com").post(confirm, HTTP_HOST=A).status_code == 200


def test_the_assignee_cannot_confirm_a_request_made_in_their_name(admin, schools):
    """An admin's own self-grant is the only pending case the API creates, so the assignee is
    the requester; the object permission also refuses a distinct assignee (checked on the row)."""
    a, _ = schools
    other = second_admin(a)
    pending = grant_principal_board(sign_in(Client(), A, "admin2@example.com"), A, other.pk).json()
    with school_scope(a.pk):  # a request filed by the first admin for the second one's membership
        mine = Membership.objects.get(account__email="admin-a@example.com")
        RoleAssignment.objects.filter(pk=pending["id"]).update(requested_by=mine)
    confirm = f"{url('role-assignments', pending['id'])}confirm/"
    assert sign_in(Client(), A, "admin2@example.com").post(confirm, HTTP_HOST=A).status_code == 403
    assert admin.post(confirm, HTTP_HOST=A).status_code == 403


def test_other_grants_are_active_immediately(admin, alice, schools):
    a, _ = schools
    with school_scope(a.pk):
        teacher = Membership.objects.get(account=alice).pk
        mine = Membership.objects.get(account__email="admin-a@example.com").pk
        group = make_group(a).pk
    for_someone_else = grant_principal_board(admin, A, teacher)
    assert for_someone_else.json()["status"] == "active"
    assert for_someone_else.json()["requested_by"] is None
    own = {"membership": mine, "role": "group_leader", "subject_group": group}
    own["valid_from"] = str(timezone.localdate())
    granted = post(admin, A, "role-assignments", own)
    assert granted.status_code == 201 and granted.json()["status"] == "active"


def test_a_pending_request_can_be_withdrawn_by_ending_it(admin, schools):
    a, _ = schools
    with school_scope(a.pk):
        mine = Membership.objects.get(account__email="admin-a@example.com").pk
    pending = grant_principal_board(admin, A, mine).json()
    ended = patch(
        admin,
        A,
        "role-assignments",
        pending["id"],
        {"valid_to": str(timezone.localdate() - timedelta(days=0))},
    )
    assert ended.status_code == 200


# --- Slice 4b: students, enrollments, Guardian links, assessment profiles -----------------------

STUDENT = {"full_name": "Nguyen An", "date_of_birth": "2012-05-01", "gender": "male"}
NATIONAL_ID = "012345678901"


def get(client, host, name, pk=None, suffix=""):
    return client.get(url(name, pk) + suffix, HTTP_HOST=host)


def new_membership(school, email):
    account = make_account(email)  # switches DB role, so before any school_scope
    with school_scope(school.pk):
        return Membership.objects.create(school=school, account=account)


def enroll_via_api(admin, student_id, klass, host=A, start=None, reason="new_year", **extra):
    return post(
        admin,
        host,
        "enrollments",
        {
            "student": student_id,
            "school_year": klass.school_year_id,
            "school_class": klass.pk,
            "valid_from": str(start or klass.school_year.starts_on),
            "reason_started": reason,
            **extra,
        },
    )


def test_school_admin_enrolls_a_student_and_links_a_guardian_end_to_end(admin, alice, schools):
    a, _ = schools
    kid = new_membership(a, "kid@example.com")
    with school_scope(a.pk):
        klass = make_class(a)
        guardian = Membership.objects.get(account=alice)
    student = post(admin, A, "students", {**STUDENT, "ministry_student_id": "", "national_id": ""})
    assert student.status_code == 201, student.json()
    student = student.json()
    assert "school" not in student and student["status"] == "studying"
    assert (student["ministry_student_id"], student["national_id"]) == (None, None)

    # A sign-in is for Lower and Upper Secondary students: refused until enrolled in such a class.
    early = patch(admin, A, "students", student["id"], {"membership": kid.pk})
    assert early.json() == {"constraint": ["student_membership_needs_secondary_level"]}
    enrollment = enroll_via_api(admin, student["id"], klass)
    assert enrollment.status_code == 201, enrollment.json()
    assert (enrollment.json()["valid_to"], enrollment.json()["reason_ended"]) == (None, None)
    signed_in = patch(admin, A, "students", student["id"], {"membership": kid.pk})
    assert signed_in.status_code == 200 and signed_in.json()["membership"] == kid.pk

    link = post(
        admin,
        A,
        "guardian-links",
        {
            "membership": guardian.pk,
            "student": student["id"],
            "relation": "grandparent",
            "valid_from": "2026-09-01",
        },
    )
    assert link.status_code == 201, link.json()
    assert [s["id"] for s in get(admin, A, "students").json()] == [student["id"]]


def test_student_ids_are_unique_per_school_and_blank_ones_never_clash(admin, client, schools):
    ids = {"ministry_student_id": "M-1", "national_id": NATIONAL_ID}
    assert post(admin, A, "students", {**STUDENT, **ids}).status_code == 201
    for field in ids:
        clash = post(admin, A, "students", {**STUDENT, field: ids[field]})
        assert clash.status_code == 400, field
        assert field in clash.json() or "non_field_errors" in clash.json()
    for _ in range(2):  # blank, missing or null: all mean "unknown"
        assert post(admin, A, "students", {**STUDENT, "national_id": " "}).status_code == 201
    assert post(admin, A, "students", {**STUDENT, "national_id": None}).status_code == 201
    # Another School's admin may use the same identifiers.
    member(schools[1], make_account("admin-b2@example.com"), Role.SCHOOL_ADMIN)
    sign_in(client, B, "admin-b2@example.com")
    assert post(client, B, "students", {**STUDENT, **ids}).status_code == 201


def test_a_student_is_created_without_ministry_id_national_id_or_membership(admin):
    created = post(admin, A, "students", STUDENT)
    assert created.status_code == 201, created.json()
    student = created.json()
    assert (student["ministry_student_id"], student["national_id"], student["membership"]) == (
        None,
        None,
        None,
    )
    bad = post(admin, A, "students", {**STUDENT, "national_id": "12345"})
    assert bad.status_code == 400 and bad.json() == {"national_id": ["invalid_national_id"]}


def test_the_student_list_masks_the_national_id_and_one_student_shows_it_in_full(admin):
    ids = {"ministry_student_id": "M-1", "national_id": NATIONAL_ID}
    full = post(admin, A, "students", {**STUDENT, **ids}).json()
    post(admin, A, "students", {**STUDENT, "full_name": "Zed"})  # no national ID
    assert full["national_id"] == NATIONAL_ID
    listed = get(admin, A, "students").json()
    assert [s["national_id"] for s in listed] == ["*********901", None]
    assert get(admin, A, "students", full["id"]).json()["national_id"] == NATIONAL_ID
    assert listed[0]["ministry_student_id"] == "M-1"  # only the national ID is hidden


def test_student_status_is_derived_and_only_a_return_is_posted_as_an_event(admin, schools):
    a, _ = schools
    student = post(admin, A, "students", {**STUDENT, "status": "graduated"}).json()
    assert (student["status"], student["scheduled_change"]) == ("studying", None)
    pk = student["id"]
    refused = patch(admin, A, "students", pk, {"status": "graduated", "full_name": "Changed"})
    assert refused.status_code == 400 and refused.json() == {"status": ["immutable"]}
    patched = patch(admin, A, "students", pk, {"status": "studying", "full_name": "Fixed"})
    assert patched.json()["full_name"] == "Fixed"

    events = f"{url('students', pk)}status-events/"

    def record(**body):
        return admin.post(events, body, content_type="application/json", HTTP_HOST=A)

    # Leaving goes through `leave/`, so the enrollment ends with the status.
    for leaving in ("transferred_out", "dropped_out", "graduated"):
        refused = record(status=leaving, on="2026-01-10")
        assert refused.status_code == 400 and refused.json() == {"status": ["use_leave"]}
    assert record(status="expelled", on="2026-01-10").status_code == 400

    with school_scope(a.pk):
        mine = Membership.objects.get(account__email="admin-a@example.com")
    spoof = {"recorded_by": 999, "student": 999}
    created = record(status="studying", on="2026-02-01", reason="returned", **spoof)
    assert created.status_code == 201, created.json()
    assert (created.json()["recorded_by"], created.json()["student"]) == (mine.pk, pk)
    # A scheduled return may be dated in the future; history is append-only.
    later = str(timezone.localdate() + timedelta(days=5))
    assert record(status="studying", on=later).status_code == 201
    history = admin.get(events, HTTP_HOST=A).json()
    assert [(e["status"], e["on"]) for e in history] == [
        ("studying", "2026-02-01"),
        ("studying", later),
    ]
    assert admin.delete(events, HTTP_HOST=A).status_code == 405
    assert get(admin, A, "students", pk).json()["status"] == "studying"


def test_school_b_cannot_read_or_extend_school_a_students_history(
    client, admin_a, admin_b, schools
):
    a, _ = schools
    with school_scope(a.pk):
        student = make_student(a)
    sign_in(client, B, "admin-b@example.com")
    events = f"{url('students', student.pk)}status-events/"
    assert client.get(events, HTTP_HOST=B).status_code == 404
    body = {"status": "graduated", "on": "2026-06-01"}
    posted = client.post(events, body, content_type="application/json", HTTP_HOST=B)
    assert posted.status_code == 404
    # B cannot even name A's student, class or Membership in its own rows.
    with school_scope(a.pk):
        klass = make_class(a)
    cross = enroll_via_api(client, student.pk, klass, B)
    assert cross.status_code == 400 and set(cross.json()) >= {"student", "school_class"}


def test_enrollment_rules_through_the_api(admin, schools):
    a, _ = schools
    with school_scope(a.pk):
        klass = make_class(a)
        other_class = make_class(a, name="7B")
        other_year = SchoolYear.objects.create(
            school=a, name="other", starts_on="2090-09-01", ends_on="2091-05-31"
        )
        student, newcomer = make_student(a), make_student(a, "Newcomer")
    row = enroll_via_api(admin, student.pk, klass)
    assert row.status_code == 201
    pk = row.json()["id"]
    # The class must belong to the year, the period inside it, and periods never overlap.
    wrong_year = post(
        admin,
        A,
        "enrollments",
        {
            "student": newcomer.pk,
            "school_year": other_year.pk,
            "school_class": klass.pk,
            "valid_from": "2090-09-01",
            "reason_started": "new_year",
        },
    )
    assert wrong_year.json() == {"constraint": ["schools_enrollment_class_in_school_year"]}
    overlap = enroll_via_api(admin, student.pk, other_class, start=klass.school_year.starts_on)
    assert overlap.json() == {"constraint": ["enrollment_no_overlapping_periods"]}
    outside = enroll_via_api(admin, student.pk, other_class, start="1999-01-01")
    assert outside.json() == {"constraint": ["enrollment_inside_school_year"]}
    # Student, year, start and reason never change.
    swap = patch(
        admin,
        A,
        "enrollments",
        pk,
        {"student": 999, "school_year": other_year.pk, "valid_from": "2000-01-01"},
    )
    assert swap.json() == {
        "student": ["immutable"],
        "school_year": ["immutable"],
        "valid_from": ["immutable"],
    }
    assert patch(admin, A, "enrollments", pk, {"reason_started": "return"}).status_code == 400
    # An end needs its reason, and a period is ended, not cleared.
    year_end = str(klass.school_year.ends_on)
    bare = patch(admin, A, "enrollments", pk, {"valid_to": year_end})
    assert bare.json() == {"reason_ended": ["required_with_valid_to"]}
    # Only the year's end is a reason given here: leaving and class changes have their own routes.
    for reason in ("transfer_out", "dropped_out", "graduated", "class_change"):
        wrong = patch(admin, A, "enrollments", pk, {"valid_to": year_end, "reason_ended": reason})
        assert wrong.json() == {"reason_ended": ["only_year_end"]}, reason
    # The class of a period that has started changes through `move/`, not in place.
    in_place = patch(admin, A, "enrollments", pk, {"school_class": other_class.pk})
    assert in_place.json() == {"school_class": ["use_move"]}
    ended = patch(admin, A, "enrollments", pk, {"valid_to": year_end, "reason_ended": "year_end"})
    assert ended.status_code == 200 and ended.json()["reason_ended"] == "year_end"
    assert patch(admin, A, "enrollments", pk, {"valid_to": None}).json() == {
        "valid_to": ["valid_to_cannot_be_cleared"]
    }
    # A student with a sign-in (secondary) cannot be enrolled in a primary class.
    kid = new_membership(a, "kid@example.com")
    with school_scope(a.pk):
        Student.objects.filter(pk=student.pk).update(membership=kid)
        primary = make_primary_class(a, other_year)
    refused = enroll_via_api(admin, student.pk, primary)
    assert refused.json() == {"constraint": ["enrollment_fits_student_membership"]}
    assert admin.delete(url("enrollments", pk), HTTP_HOST=A).status_code == 405


def test_moving_class_mid_year_ends_one_row_and_starts_the_next(admin, schools):
    a, _ = schools
    with school_scope(a.pk):
        klass, other = make_class(a), make_class(a, name="7B")
        student = make_student(a)
    start = klass.school_year.starts_on
    row = enroll_via_api(admin, student.pk, klass).json()
    move_on = start + timedelta(days=10)
    move_url = f"{url('enrollments', row['id'])}move/"

    def move(**body):
        return admin.post(move_url, body, content_type="application/json", HTTP_HOST=A)

    assert move(school_class=klass.pk, on=str(move_on)).json() == {"school_class": ["same_class"]}
    assert move(school_class=other.pk, on=str(start)).json() == {"on": ["must_be_after_valid_from"]}
    moved = move(school_class=other.pk, on=str(move_on))
    assert moved.status_code == 201, moved.json()
    new = moved.json()
    assert (new["school_class"], new["valid_from"], new["valid_to"]) == (
        other.pk,
        str(move_on),
        None,
    )
    assert new["reason_started"] == "class_change" and new["school_year"] == row["school_year"]
    old = get(admin, A, "enrollments", row["id"]).json()
    assert (old["valid_to"], old["reason_ended"]) == (
        str(move_on - timedelta(days=1)),
        "class_change",
    )
    # An ended row keeps its class, and its reason changes only together with `valid_to`.
    assert patch(admin, A, "enrollments", row["id"], {"school_class": other.pk}).json() == {
        "school_class": ["use_move"]
    }
    assert patch(admin, A, "enrollments", row["id"], {"reason_ended": "year_end"}).json() == {
        "reason_ended": ["set_with_valid_to"]
    }
    # Contiguous, no gap and no overlap; the old row cannot be moved again.
    assert date.fromisoformat(new["valid_from"]) - date.fromisoformat(old["valid_to"]) == timedelta(
        1
    )
    assert move(school_class=other.pk, on=str(move_on)).json() == {"enrollment": ["already_ended"]}

    # The class list on a date shows the student in the class they were in that day.
    def class_list(klass, day):
        listed = get(admin, A, "enrollments", suffix=f"?school_class={klass.pk}&on={day}")
        return [r["student"] for r in listed.json()]

    assert class_list(klass, move_on - timedelta(days=1)) == [student.pk]
    assert class_list(klass, move_on) == []
    assert class_list(other, move_on - timedelta(days=1)) == []
    assert class_list(other, move_on) == [student.pk]
    assert get(admin, A, "enrollments", suffix="?on=not-a-date").status_code == 400


def leave_url(student, suffix="leave/"):
    return f"{url('students', student.pk)}{suffix}"


def post_to(client, path, **body):
    return client.post(path, body, content_type="application/json", HTTP_HOST=A)


def history_of(admin, student):
    events = admin.get(f"{url('students', student.pk)}status-events/", HTTP_HOST=A).json()
    return [(e["status"], e["on"]) for e in events]


def test_leave_ends_the_enrollment_and_records_the_event_in_one_transaction(
    admin, schools, monkeypatch
):
    a, _ = schools
    with school_scope(a.pk):
        klass = make_class(a)
        student = make_student(a)
    row = enroll_via_api(admin, student.pk, klass).json()
    today = timezone.localdate()
    day = today - timedelta(days=3)  # backdated: the student has already left
    leave = leave_url(student)

    def state():
        enrollment = get(admin, A, "enrollments", row["id"]).json()
        return (
            enrollment["valid_to"],
            get(admin, A, "students", student.pk).json()["status"],
            history_of(admin, student),
        )

    # A reason from the list, and a destination for a transfer out only.
    assert post_to(admin, leave, reason="transfer_out", on=str(day)).json() == {
        "destination": ["required"]
    }
    assert post_to(admin, leave, reason="expelled", on=str(day)).status_code == 400
    assert post_to(admin, leave, reason="graduated").status_code == 400  # no date

    # Neither half sticks when the other fails: the event insert fails ...
    def fail_to_insert(**kwargs):
        raise IntegrityError("simulated")

    monkeypatch.setattr(StudentStatusEvent.objects, "create", fail_to_insert)
    failed = post_to(admin, leave, reason="transfer_out", on=str(day), destination="THCS B")
    assert failed.json() == {"constraint": ["unknown"]}
    assert state() == (None, "studying", [])
    monkeypatch.undo()
    # ... or the enrollment update fails (a date outside the school year).
    late = str(klass.school_year.ends_on + timedelta(days=1))
    failed = post_to(admin, leave, reason="dropped_out", on=late)
    assert failed.json() == {"constraint": ["enrollment_inside_school_year"]}
    assert state() == (None, "studying", [])
    early = str(klass.school_year.starts_on - timedelta(days=1))
    assert post_to(admin, leave, reason="dropped_out", on=early).json() == {
        "on": ["before_enrollment_start"]
    }

    done = post_to(admin, leave, reason="transfer_out", on=str(day), destination="THCS B, Hue")
    assert done.status_code == 200, done.json()
    assert (done.json()["status"], done.json()["scheduled_change"]) == ("transferred_out", None)
    assert state() == (str(day), "transferred_out", [("transferred_out", str(day))])
    events = admin.get(f"{url('students', student.pk)}status-events/", HTTP_HOST=A).json()
    assert events[0]["reason"] == "Transferred out to THCS B, Hue"
    assert get(admin, A, "enrollments", row["id"]).json()["reason_ended"] == "transfer_out"
    # Records stay: the student and the enrollment are still there, but not in the class after.
    in_class = f"?school_class={klass.pk}&on="
    assert [
        r["student"] for r in get(admin, A, "enrollments", suffix=in_class + str(day)).json()
    ] == [student.pk]
    after = day + timedelta(days=1)
    assert get(admin, A, "enrollments", suffix=in_class + str(after)).json() == []
    again = post_to(admin, leave, reason="graduated", on=str(day))
    assert again.json() == {"status": ["not_studying"]}


def test_every_leave_reason_ends_the_enrollment_with_the_matching_status(admin, schools):
    a, _ = schools
    today = timezone.localdate()
    with school_scope(a.pk):
        klass = make_class(a)
        students = {
            reason: make_student(a, reason)
            for reason in ("transfer_out", "dropped_out", "graduated")
        }
    expected = {
        "transfer_out": "transferred_out",
        "dropped_out": "dropped_out",
        "graduated": "graduated",
    }
    for reason, student in students.items():
        row = enroll_via_api(admin, student.pk, klass).json()
        body = {"destination": "THCS B"} if reason == "transfer_out" else {}
        done = post_to(admin, leave_url(student), reason=reason, on=str(today), **body)
        assert done.status_code == 200, done.json()
        assert done.json()["status"] == expected[reason]
        ended = get(admin, A, "enrollments", row["id"]).json()
        assert (ended["valid_to"], ended["reason_ended"]) == (str(today), reason)
    # The old route is gone, and the list can be filtered by today's status.
    assert post_to(admin, leave_url(students["graduated"], "transfer-out/")).status_code == 404
    only = get(admin, A, "students", suffix="?status=graduated").json()
    assert [s["full_name"] for s in only] == ["graduated"]
    assert get(admin, A, "students", suffix="?status=studying").json() == []
    assert get(admin, A, "students", suffix="?status=expelled").status_code == 400


def test_a_scheduled_leave_keeps_the_student_in_class_until_the_day(admin, schools, monkeypatch):
    a, _ = schools
    with school_scope(a.pk):
        klass = make_class(a)
        student = make_student(a)
    today = timezone.localdate()
    row = enroll_via_api(admin, student.pk, klass).json()
    friday = today + timedelta(days=7)
    scheduled = post_to(
        admin, leave_url(student), reason="transfer_out", on=str(friday), destination="THCS B"
    )
    assert scheduled.status_code == 200, scheduled.json()
    assert scheduled.json()["status"] == "studying"
    assert scheduled.json()["scheduled_change"] == {"status": "transferred_out", "on": str(friday)}
    ended = get(admin, A, "enrollments", row["id"]).json()
    assert (ended["valid_to"], ended["reason_ended"]) == (str(friday), "transfer_out")

    def in_class(day):
        listed = get(admin, A, "enrollments", suffix=f"?school_class={klass.pk}&on={day}")
        return [r["student"] for r in listed.json()]

    def listed_as(status):
        return [s["id"] for s in get(admin, A, "students", suffix=f"?status={status}").json()]

    # Today and on the last day: still studying and in the class; the day after, out.
    assert in_class(today) == in_class(friday) == [student.pk]
    assert in_class(friday + timedelta(days=1)) == []
    assert (listed_as("studying"), listed_as("transferred_out")) == ([student.pk], [])
    listed = get(admin, A, "students").json()[0]
    assert listed["scheduled_change"] == {"status": "transferred_out", "on": str(friday)}
    assert history_of(admin, student) == [("transferred_out", str(friday))]
    # It cannot be scheduled twice while the enrollment is already ending.
    earlier = str(friday - timedelta(days=1))
    twice = post_to(admin, leave_url(student), reason="graduated", on=earlier)
    assert twice.json() == {"enrollment": ["no_open_enrollment"]}
    same_day = post_to(admin, leave_url(student), reason="graduated", on=str(friday))
    assert same_day.json() == {"status": ["not_studying"]}

    # The day after, with nothing else changed: transferred out, nothing scheduled.
    monkeypatch.setattr(timezone, "localdate", lambda: friday + timedelta(days=1))
    now = get(admin, A, "students", student.pk).json()
    assert (now["status"], now["scheduled_change"]) == ("transferred_out", None)
    assert (listed_as("transferred_out"), listed_as("studying")) == ([student.pk], [])


def test_a_scheduled_leave_can_be_cancelled_until_its_day(admin, schools, monkeypatch):
    a, _ = schools
    with school_scope(a.pk):
        klass = make_class(a)
        student = make_student(a)
    today = timezone.localdate()
    row = enroll_via_api(admin, student.pk, klass).json()
    cancel = leave_url(student, "leave/cancel/")
    assert post_to(admin, cancel).json() == {"leave": ["no_leave"]}
    friday = today + timedelta(days=7)
    body = {"reason": "dropped_out", "on": str(friday)}
    assert post_to(admin, leave_url(student), **body).status_code == 200

    cancelled = post_to(admin, cancel)
    assert cancelled.status_code == 200, cancelled.json()
    assert (cancelled.json()["status"], cancelled.json()["scheduled_change"]) == ("studying", None)
    reopened = get(admin, A, "enrollments", row["id"]).json()
    assert (reopened["valid_to"], reopened["reason_ended"]) == (None, None)
    # History is kept: the leave and its cancellation, the later event winning on the same day.
    assert history_of(admin, student) == [("dropped_out", str(friday)), ("studying", str(friday))]
    listed = get(admin, A, "enrollments", suffix=f"?school_class={klass.pk}&on={friday}")
    assert [r["student"] for r in listed.json()] == [student.pk]
    assert post_to(admin, cancel).json() == {"leave": ["no_leave"]}  # nothing left to cancel
    # The same student can be scheduled to leave again afterwards, and again cancelled.
    assert post_to(admin, leave_url(student), **body).status_code == 200
    assert post_to(admin, cancel).status_code == 200
    assert post_to(admin, leave_url(student), **body).status_code == 200

    # On the day (or after) the leave is a fact: nothing to cancel.
    monkeypatch.setattr(timezone, "localdate", lambda: friday)
    assert post_to(admin, cancel).json() == {"leave": ["leave_already_effective"]}
    assert get(admin, A, "students", student.pk).json()["status"] == "dropped_out"
    reopened = get(admin, A, "enrollments", row["id"]).json()
    assert (reopened["valid_to"], reopened["reason_ended"]) == (str(friday), "dropped_out")


def test_a_continuing_student_can_leave_and_cancel_during_the_break(admin, schools, monkeypatch):
    a, _ = schools
    with school_scope(a.pk):
        klass = make_class(a)
        student = make_student(a)
    row = enroll_via_api(admin, student.pk, klass).json()
    year_end = klass.school_year.ends_on
    assert (
        admin.post(f"{url('school-years', klass.school_year_id)}close/", HTTP_HOST=A).status_code
        == 200
    )
    closed = get(admin, A, "enrollments", row["id"]).json()
    assert (closed["valid_to"], closed["reason_ended"]) == (str(year_end), "year_end")

    leave, cancel = leave_url(student), leave_url(student, "leave/cancel/")
    assert post_to(admin, cancel).json() == {"leave": ["no_leave"]}
    early = post_to(admin, leave, reason="graduated", on=str(year_end - timedelta(days=1)))
    assert early.json() == {"on": ["before_enrollment_end"]}

    left_on = year_end + timedelta(days=10)
    done = post_to(admin, leave, reason="dropped_out", on=str(left_on))
    assert done.status_code == 200, done.json()
    assert done.json()["scheduled_change"] == {"status": "dropped_out", "on": str(left_on)}
    # No enrollment is touched, and a second leave is refused.
    same = get(admin, A, "enrollments", row["id"]).json()
    assert (same["valid_to"], same["reason_ended"]) == (str(year_end), "year_end")
    again = post_to(admin, leave, reason="graduated", on=str(left_on + timedelta(days=1)))
    assert again.json() == {"status": ["not_studying"]}

    # Cancelling appends the `studying` event and nothing else.
    cancelled = post_to(admin, cancel)
    assert cancelled.status_code == 200, cancelled.json()
    assert cancelled.json()["scheduled_change"] is None
    assert history_of(admin, student) == [
        ("dropped_out", str(left_on)),
        ("studying", str(left_on)),
    ]
    assert get(admin, A, "enrollments", row["id"]).json() == same
    assert post_to(admin, cancel).json() == {"leave": ["no_leave"]}

    # Leave again; once its day has come it is a fact.
    assert post_to(admin, leave, reason="dropped_out", on=str(left_on)).status_code == 200
    monkeypatch.setattr(timezone, "localdate", lambda: left_on)
    assert post_to(admin, cancel).json() == {"leave": ["leave_already_effective"]}


def test_a_backdated_leave_cannot_be_cancelled(admin, schools):
    a, _ = schools
    with school_scope(a.pk):
        klass = make_class(a)
        student = make_student(a)
    enroll_via_api(admin, student.pk, klass)
    yesterday = str(timezone.localdate() - timedelta(days=1))
    assert post_to(admin, leave_url(student), reason="graduated", on=yesterday).status_code == 200
    cancel = post_to(admin, leave_url(student, "leave/cancel/"))
    assert cancel.json() == {"leave": ["leave_already_effective"]}
    assert get(admin, A, "students", student.pk).json()["status"] == "graduated"


def test_a_student_who_left_can_return_and_a_transfer_in_starts_mid_year(admin, schools):
    a, _ = schools
    with school_scope(a.pk):
        klass = make_class(a)
        student = make_student(a)
    start = klass.school_year.starts_on
    enroll_via_api(admin, student.pk, klass)
    out_on = start + timedelta(days=20)
    body = {"reason": "transfer_out", "on": str(out_on), "destination": "THCS B"}
    assert post_to(admin, leave_url(student), **body).status_code == 200
    back_on = start + timedelta(days=60)  # a scheduled return
    # Back in this School: first a `studying` event, then a `return` period.
    refused = enroll_via_api(admin, student.pk, klass, start=back_on, reason="return")
    assert refused.json() == {"student": ["student_not_studying"]}
    events = f"{url('students', student.pk)}status-events/"
    event = {"status": "studying", "on": str(back_on), "reason": "returned"}
    assert (
        admin.post(events, event, content_type="application/json", HTTP_HOST=A).status_code == 201
    )
    returned = enroll_via_api(admin, student.pk, klass, start=back_on, reason="return")
    assert returned.status_code == 201, returned.json()
    rows = get(admin, A, "enrollments", suffix=f"?student={student.pk}").json()
    assert [(r["reason_started"], r["reason_ended"]) for r in rows] == [
        ("new_year", "transfer_out"),
        ("return", None),
    ]
    now = get(admin, A, "students", student.pk).json()
    if back_on > timezone.localdate():
        assert now["scheduled_change"] == {"status": "studying", "on": str(back_on)}
    # A student arriving from another School mid-year is a new student with a transfer_in period.
    newcomer = post(admin, A, "students", {**STUDENT, "full_name": "Tran Binh"}).json()
    arrived = enroll_via_api(
        admin, newcomer["id"], klass, start=start + timedelta(days=100), reason="transfer_in"
    )
    assert arrived.status_code == 201 and arrived.json()["reason_started"] == "transfer_in"


def test_closing_a_school_year_ends_its_open_enrollments(admin, schools):
    a, _ = schools
    with school_scope(a.pk):
        klass = make_class(a)
        year = klass.school_year
        next_year = SchoolYear.objects.create(
            school=a,
            name="next",
            starts_on=year.ends_on + timedelta(days=1),
            ends_on=year.ends_on + timedelta(days=366),
        )
        next_class = make_class(a, next_year, "8A")
        continuing, leaver = make_student(a), make_student(a, "Leaver")
    enroll_via_api(admin, continuing.pk, klass)
    left = enroll_via_api(admin, leaver.pk, klass).json()
    leave_on = str(timezone.localdate())
    post_to(admin, leave_url(leaver), reason="graduated", on=leave_on)
    after_year = year.ends_on + timedelta(days=1)

    # An unclosed row is open-ended but not in force once its year is over.
    listed = get(admin, A, "enrollments", suffix=f"?school_class={klass.pk}&on={year.ends_on}")
    assert [r["student"] for r in listed.json()] == [continuing.pk]
    listed = get(admin, A, "enrollments", suffix=f"?school_class={klass.pk}&on={after_year}")
    assert listed.json() == []
    with school_scope(a.pk):
        assert not Enrollment.objects.in_force(after_year).exists()
        assert Enrollment.objects.in_force(year.ends_on).count() == 1
    # While it is unclosed, the continuing student cannot start next year's period ...
    blocked = enroll_via_api(admin, continuing.pk, next_class, start=next_year.starts_on)
    assert blocked.json() == {"constraint": ["enrollment_no_overlapping_periods"]}

    close = f"{url('school-years', year.pk)}close/"
    closed = admin.post(close, HTTP_HOST=A)
    assert closed.status_code == 200, closed.json()
    assert closed.json()["id"] == year.pk
    rows = get(admin, A, "enrollments", suffix=f"?student={continuing.pk}").json()
    assert [(r["valid_to"], r["reason_ended"]) for r in rows] == [(str(year.ends_on), "year_end")]
    # ... and can after it. The leaver's row keeps its own end and reason.
    started = enroll_via_api(admin, continuing.pk, next_class, start=next_year.starts_on)
    assert started.status_code == 201, started.json()
    untouched = get(admin, A, "enrollments", left["id"]).json()
    assert (untouched["valid_to"], untouched["reason_ended"]) == (leave_on, "graduated")

    # Closing again changes nothing.
    snapshot = get(admin, A, "enrollments").json()
    assert admin.post(close, HTTP_HOST=A).status_code == 200
    assert get(admin, A, "enrollments").json() == snapshot
    assert admin.post(f"{url('school-years', 999999)}close/", HTTP_HOST=A).status_code == 404


def test_only_a_school_admin_closes_a_school_year(client, alice, admin_b, schools):
    a, _ = schools
    with school_scope(a.pk):
        year = make_class(a).school_year
    sign_in(client, A, "alice@example.com")  # a homeroom teacher
    close = f"{url('school-years', year.pk)}close/"
    assert client.post(close, HTTP_HOST=A).status_code == 403
    client.logout()
    sign_in(client, B, "admin-b@example.com")
    assert client.post(close, HTTP_HOST=B).status_code == 404


def test_membership_kinds_stay_apart(admin, alice, schools):
    a, _ = schools
    kid = new_membership(a, "kid@example.com")
    parent = new_membership(a, "parent@example.com")
    with school_scope(a.pk):
        klass = make_class(a)
        student, sibling = make_student(a), make_student(a, "Sibling")
        staff = Membership.objects.get(account=alice)
        mine = Membership.objects.get(account__email="admin-a@example.com")
    enroll_via_api(admin, student.pk, klass)
    link = {"student": sibling.pk, "relation": "mother", "valid_from": "2026-01-01"}
    assert post(admin, A, "guardian-links", {**link, "membership": parent.pk}).status_code == 201

    # A student's sign-in: not the requester's, not a staff member's, not a Guardian's.
    for membership, code in (
        (mine, "membership_is_requester"),
        (staff, "membership_has_role_assignment"),
        (parent, "membership_has_guardian_link"),
    ):
        refused = patch(admin, A, "students", student.pk, {"membership": membership.pk})
        assert refused.json() == {"membership": [code]}, code
    assert patch(admin, A, "students", student.pk, {"membership": kid.pk}).status_code == 200

    # ... and a student's sign-in holds neither a Guardian link nor a staff role.
    as_guardian = post(admin, A, "guardian-links", {**link, "membership": kid.pk})
    assert as_guardian.json() == {"membership": ["membership_is_student"]}
    role = {"membership": kid.pk, "role": "school_admin", "valid_from": "2026-09-01"}
    assert post(admin, A, "role-assignments", role).json() == {
        "membership": ["membership_is_student"]
    }
    # Staff may be a Guardian.
    as_staff = post(admin, A, "guardian-links", {**link, "membership": staff.pk})
    assert as_staff.status_code == 201, as_staff.json()


def test_a_guardian_links_relation_is_frozen_once_the_link_has_ended(admin, alice, schools):
    a, _ = schools
    today = timezone.localdate()
    with school_scope(a.pk):
        student = make_student(a)
        guardian = Membership.objects.get(account=alice)
    base = {"membership": guardian.pk, "student": student.pk, "relation": "mother"}
    past = post(
        admin,
        A,
        "guardian-links",
        {
            **base,
            "valid_from": str(today - timedelta(days=100)),
            "valid_to": str(today - timedelta(days=10)),
        },
    )
    assert past.status_code == 201, past.json()
    frozen = patch(admin, A, "guardian-links", past.json()["id"], {"relation": "father"})
    assert frozen.json() == {"relation": ["period_already_ended"]}
    same = patch(admin, A, "guardian-links", past.json()["id"], {"relation": "mother"})
    assert same.status_code == 200
    # Ending today or later leaves the relation open to correction.
    current = post(
        admin,
        A,
        "guardian-links",
        {**base, "valid_from": str(today - timedelta(days=5)), "valid_to": str(today)},
    )
    corrected = patch(admin, A, "guardian-links", current.json()["id"], {"relation": "father"})
    assert corrected.status_code == 200 and corrected.json()["relation"] == "father"


def test_guardian_links_end_with_valid_to_and_never_overlap(admin, alice, schools):
    a, _ = schools
    with school_scope(a.pk):
        student = make_student(a)
        guardian = Membership.objects.get(account=alice)
    base = {"membership": guardian.pk, "student": student.pk, "relation": "mother"}
    first = post(admin, A, "guardian-links", {**base, "valid_from": "2026-01-01"})
    assert first.status_code == 201
    pk = first.json()["id"]
    overlap = post(admin, A, "guardian-links", {**base, "valid_from": "2026-06-01"})
    assert overlap.json() == {"constraint": ["guardianlink_no_overlapping_periods"]}
    assert admin.delete(url("guardian-links", pk), HTTP_HOST=A).status_code == 405
    # Only valid_to changes (and the relation may be corrected): the pair and start stay.
    frozen = patch(admin, A, "guardian-links", pk, {"valid_from": "2026-01-02", "student": 999})
    assert frozen.json() == {"valid_from": ["immutable"], "student": ["immutable"]}
    early = patch(admin, A, "guardian-links", pk, {"valid_to": "2025-12-31"})
    assert early.json() == {"valid_to": ["valid_to_before_valid_from"]}
    ended = patch(admin, A, "guardian-links", pk, {"valid_to": "2026-05-31", "relation": "other"})
    assert ended.status_code == 200 and ended.json()["relation"] == "other"
    assert patch(admin, A, "guardian-links", pk, {"valid_to": None}).json() == {
        "valid_to": ["valid_to_cannot_be_cleared"]
    }
    # Once ended, the same pair may be linked again after it.
    again = post(admin, A, "guardian-links", {**base, "valid_from": "2026-06-01"})
    assert again.status_code == 201


def test_every_member_reads_the_assessment_profiles_and_nobody_writes_them(alice, client, schools):
    with owner_role():
        AssessmentProfileVersion.objects.create(
            level_kind="primary",  # the secondary versions are seeded by migration
            effective_from="2030-01-01",
            source="test",
            rules={"schema": 1},
        )
    sign_in(client, A, "alice@example.com")  # a homeroom teacher, not a School admin
    listed = get(client, A, "assessment-profiles")
    assert listed.status_code == 200
    (profile,) = [p for p in listed.json() if p["level_kind"] == "primary"]
    assert profile["rules"] == {"schema": 1}
    assert get(client, A, "assessment-profiles", profile["id"]).status_code == 200
    assert post(client, A, "assessment-profiles", {}).status_code == 405
    assert patch(client, A, "assessment-profiles", profile["id"], {}).status_code == 405
    assert client.delete(url("assessment-profiles", profile["id"]), HTTP_HOST=A).status_code == 405
    client.logout()
    assert get(client, A, "assessment-profiles").status_code == 403


def board_member(school, email="board@example.com"):
    """A principal-board member; returns the Membership."""
    membership = member(school, make_account(email), RoleAssignment.Role.PRINCIPAL_BOARD)
    return membership


def test_a_principal_board_member_reads_the_setup_but_cannot_change_it(client, admin_a, schools):
    """The matrix gives the principal board 👁 on configuring the School: every setup endpoint
    answers its GETs and refuses every write (`read=True` is for safe methods only)."""
    board_member(schools[0])
    sign_in(client, A, "board@example.com")
    for name in ENDPOINTS:
        assert client.get(url(name), HTTP_HOST=A).status_code == 200, name
        assert client.options(url(name), HTTP_HOST=A).status_code == 200, name
        assert post(client, A, name, {}).status_code == 403, name
        assert patch(client, A, name, 1, {}).status_code == 403, name
        assert client.delete(url(name, 1), HTTP_HOST=A).status_code == 403, name
    assert client.get(f"{url('students', 1)}status-events/", HTTP_HOST=A).status_code == 404
    for action in ("leave/", "leave/cancel/"):
        assert client.post(f"{url('students', 1)}{action}", HTTP_HOST=A).status_code == 403
    assert client.post(f"{url('school-years', 1)}close/", HTTP_HOST=A).status_code == 403
    assert client.post(f"{url('enrollments', 1)}move/", HTTP_HOST=A).status_code == 403


def test_a_teacher_cannot_read_the_setup(client, admin_a, alice, schools):
    sign_in(client, A, "alice@example.com")
    for name in ENDPOINTS:
        assert client.get(url(name), HTTP_HOST=A).status_code == 403, name


def test_principal_duties_are_set_up_through_the_role_assignment_api(admin, schools):
    a, _ = schools
    account = make_account("p@example.com")  # swaps DB roles: outside any School scope
    with school_scope(a.pk):
        teacher = Membership.objects.create(school=a, account=account)
    base = {
        "membership": teacher.pk,
        "role": "principal_board",
        "valid_from": str(timezone.localdate()),
        "title": "vice_principal",
        "can_reopen_gradebooks": True,
    }
    created = post(admin, A, "role-assignments", base)
    assert created.status_code == 201, created.json()
    body = created.json()
    assert (body["title"], body["can_reopen_gradebooks"], body["signs_for_principal"]) == (
        "vice_principal",
        True,
        False,
    )
    # A School admin may change the two flags with a normal PATCH ...
    patched = patch(
        admin,
        A,
        "role-assignments",
        body["id"],
        {"can_reopen_gradebooks": False, "signs_for_principal": True},
    )
    assert patched.status_code == 200
    assert (patched.json()["can_reopen_gradebooks"], patched.json()["signs_for_principal"]) == (
        False,
        True,
    )
    # ... but the title is fixed like the other scope fields.
    retitled = patch(admin, A, "role-assignments", body["id"], {"title": "principal"})
    assert retitled.status_code == 400 and retitled.json() == {"title": ["immutable"]}


def test_principal_duties_are_refused_on_other_roles_and_unknown_titles(admin, alice, schools):
    a, _ = schools
    with school_scope(a.pk):
        membership = Membership.objects.get(account=alice)
        klass = make_class(a, name="7C")
    today = str(timezone.localdate() + timedelta(days=1))
    homeroom = {
        "membership": membership.pk,
        "role": "homeroom_teacher",
        "school_year": klass.school_year_id,
        "school_class": klass.pk,
        "valid_from": today,
    }
    for duty in (
        {"title": "principal"},
        {"can_reopen_gradebooks": True},
        {"signs_for_principal": True},
    ):
        refused = post(admin, A, "role-assignments", {**homeroom, **duty})
        assert refused.json() == {"constraint": ["roleassignment_duties_only_on_principal_board"]}
    board = {"membership": membership.pk, "role": "principal_board", "valid_from": today}
    assert post(admin, A, "role-assignments", {**board, "title": "caretaker"}).status_code == 400


def test_the_second_person_who_confirms_may_be_the_principal_board_but_no_one_else(
    admin, alice, schools
):
    """Alice (homeroom) cannot confirm; the board member can (accounts.manage 👁)."""
    a, _ = schools
    with school_scope(a.pk):
        mine = Membership.objects.get(account__email="admin-a@example.com").pk
    board_member(a, "board2@example.com")
    pending = grant_principal_board(admin, A, mine).json()
    confirm = f"{url('role-assignments', pending['id'])}confirm/"
    assert sign_in(Client(), A, "alice@example.com").post(confirm, HTTP_HOST=A).status_code == 403
    assert sign_in(Client(), A, "board2@example.com").post(confirm, HTTP_HOST=A).status_code == 200


def own_membership(school, email="admin-a@example.com"):
    with school_scope(school.pk):
        return Membership.objects.get(account__email=email).pk


def test_nobody_turns_on_a_named_duty_for_their_own_row(admin, schools):
    a, _ = schools
    mine = own_membership(a)
    second_admin(a)
    base = {"membership": mine, "role": "principal_board", "valid_from": str(timezone.localdate())}
    for duty in (
        {"can_reopen_gradebooks": True},
        {"signs_for_principal": True},
        {"title": "principal"},
    ):
        refused = post(admin, A, "role-assignments", {**base, **duty})
        assert refused.status_code == 400, duty
        assert refused.json() == {next(iter(duty)): ["self_duty_change"]}
    # A vice principal title, or no duty, is not sensitive: the row is created, pending.
    pending = post(admin, A, "role-assignments", {**base, "title": "vice_principal"})
    assert pending.status_code == 201, pending.json()
    row = pending.json()
    # On a pending row the duties cannot change at all: the owner is refused as the owner, ...
    own = patch(admin, A, "role-assignments", row["id"], {"signs_for_principal": True})
    assert own.json() == {"signs_for_principal": ["self_duty_change"]}
    # ... another admin as a change to a row that waits for its confirmation.
    other = sign_in(Client(), A, "admin2@example.com")
    waiting = patch(other, A, "role-assignments", row["id"], {"signs_for_principal": True})
    assert waiting.status_code == 400
    assert waiting.json() == {"signs_for_principal": ["pending_confirmation"]}
    # Sending the stored values back is no change.
    same = patch(other, A, "role-assignments", row["id"], {"can_reopen_gradebooks": False})
    assert same.status_code == 200
    # Once the second person confirmed, another admin sets the duties; the owner still cannot.
    assert (
        other.post(f"{url('role-assignments', row['id'])}confirm/", HTTP_HOST=A).status_code == 200
    )
    done = patch(other, A, "role-assignments", row["id"], {"can_reopen_gradebooks": True})
    assert done.status_code == 200 and done.json()["can_reopen_gradebooks"] is True
    again = patch(admin, A, "role-assignments", row["id"], {"signs_for_principal": True})
    assert again.json() == {"signs_for_principal": ["self_duty_change"]}
    # Turning a duty off on their own row is allowed.
    off = patch(admin, A, "role-assignments", row["id"], {"can_reopen_gradebooks": False})
    assert off.status_code == 200 and off.json()["can_reopen_gradebooks"] is False


def test_the_title_is_set_once_and_there_is_one_principal_at_a_time(admin, alice, schools):
    a, _ = schools
    teacher = Membership_pk(a, alice)
    first = grant_principal_board(admin, A, teacher).json()
    assert first["title"] is None
    named = patch(admin, A, "role-assignments", first["id"], {"title": "vice_principal"})
    assert named.status_code == 200 and named.json()["title"] == "vice_principal"
    changed = patch(admin, A, "role-assignments", first["id"], {"title": "principal"})
    assert changed.json() == {"title": ["immutable"]}
    cleared = patch(admin, A, "role-assignments", first["id"], {"title": None})
    assert cleared.json() == {"title": ["immutable"]}
    # Two principals at once are refused by the database; a vice principal beside one is fine.
    today = str(timezone.localdate())
    boss = second_admin(a)
    principal = post(
        admin,
        A,
        "role-assignments",
        {
            "membership": boss.pk,
            "role": "principal_board",
            "valid_from": today,
            "title": "principal",
        },
    )
    assert principal.status_code == 201, principal.json()
    third = board_member(a, "board3@example.com")
    with school_scope(a.pk):
        row = RoleAssignment.objects.get(membership=third)
    clash = patch(admin, A, "role-assignments", row.pk, {"title": "principal"})
    assert clash.json() == {"constraint": ["roleassignment_one_principal_at_a_time"]}
    vice = patch(admin, A, "role-assignments", row.pk, {"title": "vice_principal"})
    assert vice.status_code == 200


def Membership_pk(school, account):
    with school_scope(school.pk):
        return Membership.objects.get(account=account).pk
