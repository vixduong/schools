from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from accounts.models import Membership, RoleAssignment
from schools.models import SchoolClass
from tenancy.rls import school_scope

from .conftest import PASSWORD
from .factories import make_class

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
    assert len(admin.get(url("school-years"), HTTP_HOST=A).json()) == 2  # and the admin's own


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
