from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from accounts.models import Membership, RoleAssignment
from schools.models import Grade, Level, Room, SchoolClass, SchoolYear, Subject
from tenancy.rls import school_scope

from .conftest import PASSWORD, make_account, member
from .factories import make_class, make_group, make_subject

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
    ignored = patch(
        admin, A, "role-assignments", first["id"], {"role": "principal_board", "school_class": None}
    )
    assert (
        ignored.json()["role"] == "homeroom_teacher" and ignored.json()["school_class"] == klass.pk
    )
    resumed = post(
        admin, A, "role-assignments", {**base, "valid_from": str(today - timedelta(days=5))}
    )
    assert resumed.status_code == 201
    overlapping = post(admin, A, "role-assignments", {**base, "valid_from": str(today)})
    assert overlapping.json() == {"constraint": ["roleassignment_no_overlapping_periods"]}


def test_student_and_guardian_assignments_are_refused_until_4b(admin, alice, schools):
    a, _ = schools
    with school_scope(a.pk):
        membership = Membership.objects.get(account=alice)
        year = make_class(a).school_year
    for role in ("student", "guardian"):
        response = post(
            admin,
            A,
            "role-assignments",
            {
                "membership": membership.pk,
                "role": role,
                "school_year": year.pk,
                "valid_from": "2026-09-01",
            },
        )
        assert response.json() == {"constraint": ["roleassignment_scope_matches_role"]}


def test_openapi_schema_is_valid():
    call_command(
        "spectacular", "--validate", "--fail-on-warn", stdout=StringIO(), stderr=StringIO()
    )


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
    changed = patch(
        admin,
        A,
        "classes",
        klass.pk,
        {"name": "7Z", "grade": other_grade.pk, "school_year": other_year.pk},
    )
    assert changed.status_code == 200
    assert (changed.json()["name"], changed.json()["grade"]) == ("7Z", klass.grade_id)
    assert changed.json()["school_year"] == klass.school_year_id


def test_a_grade_never_changes_number_or_level(admin, schools):
    a, _ = schools
    with school_scope(a.pk):
        grade = make_class(a).grade
        other_level = Level.objects.create(school=a, kind=Level.Kind.PRIMARY)
    changed = patch(admin, A, "grades", grade.pk, {"number": 3, "level": other_level.pk})
    assert changed.status_code == 200
    assert (changed.json()["number"], changed.json()["level"]) == (grade.number, grade.level_id)


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
    assert end(row.pk, valid_from=str(today)).json()["valid_from"] == str(row.valid_from)
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
