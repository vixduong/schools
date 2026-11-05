"""SubjectLoad: the periods a Grade has a subject per school year (School setup API and rules)."""

import pytest
from django.db import IntegrityError, ProgrammingError, connection

from schools.models import Grade, Level, SubjectLoad
from schools.tests.factories import make_subject
from tenancy.rls import school_scope
from testing import A, make_account, member, sign_in

pytestmark = pytest.mark.usefixtures("as_app_role")

URL = "/api/setup/subject-loads/"


def send(client, method, path, body=None):
    return getattr(client, method)(path, body, content_type="application/json", HTTP_HOST=A)


@pytest.fixture
def load_body(schools, setup):
    a, _ = schools
    with school_scope(a.pk):
        math = make_subject(a, "MATH")
        grade = setup["7A"].grade
    return {"school_year": setup["year"].pk, "grade": grade.pk, "subject": math.pk}


def test_the_school_admin_sets_a_load_and_changes_only_its_periods(admin, load_body):
    created = send(admin, "post", URL, {**load_body, "periods_per_year": 70})
    assert created.status_code == 201, created.content
    pk = created.json()["id"]
    changed = send(admin, "patch", f"{URL}{pk}/", {"periods_per_year": 105})
    assert (changed.status_code, changed.json()["periods_per_year"]) == (200, 105)
    # The same year, Grade and subject are accepted back; another is "immutable".
    assert send(admin, "patch", f"{URL}{pk}/", {"subject": load_body["subject"]}).status_code == 200
    other = send(admin, "patch", f"{URL}{pk}/", {"grade": load_body["grade"] + 1})
    assert (other.status_code, other.json()) == (400, {"grade": ["immutable"]})
    assert send(admin, "delete", f"{URL}{pk}/").status_code == 405
    listed = send(admin, "get", f"{URL}?school_year={load_body['school_year']}").json()
    assert [row["periods_per_year"] for row in listed] == [105]
    assert send(admin, "get", f"{URL}?school_year=0").json() == []


def test_a_load_is_once_per_year_grade_and_subject_between_1_and_400_periods(
    admin, load_body, schools
):
    assert send(admin, "post", URL, {**load_body, "periods_per_year": 70}).status_code == 201
    assert send(admin, "post", URL, {**load_body, "periods_per_year": 35}).status_code == 400
    a, _ = schools
    with pytest.raises(IntegrityError, match="subjectload_once_per_year_grade_subject"):
        with school_scope(a.pk):
            SubjectLoad.objects.create(
                school=a,
                school_year_id=load_body["school_year"],
                grade_id=load_body["grade"],
                subject_id=load_body["subject"],
                periods_per_year=35,
            )
    other = make_subject_in(a, "LIT")
    for periods in (0, 401):
        response = send(
            admin, "post", URL, {**load_body, "subject": other, "periods_per_year": periods}
        )
        assert (response.status_code, response.json()) == (
            400,
            {"constraint": ["subjectload_periods_in_1_to_400"]},
        )
    # The edges are fine.
    for periods in (1, 400):
        body = {**load_body, "subject": other, "periods_per_year": periods}
        created = send(admin, "post", URL, body)
        assert created.status_code == 201, created.content
        break
    assert (
        send(admin, "patch", f"{URL}{created.json()['id']}/", {"periods_per_year": 400}).status_code
        == 200
    )


def make_subject_in(school, code):
    with school_scope(school.pk):
        return make_subject(school, code).pk


def test_a_load_names_a_grade_year_and_subject_of_its_own_school(admin, load_body, schools, setup):
    a, b = schools
    with school_scope(b.pk):
        level = Level.objects.create(school=b, kind=Level.Kind.LOWER_SECONDARY)
        foreign = Grade.objects.create(school=b, level=level, number=7)
    with pytest.raises(IntegrityError, match="schools_subjectload_grade_id_same_school"):
        with school_scope(a.pk):
            SubjectLoad.objects.create(
                school=a,
                school_year_id=load_body["school_year"],
                grade_id=foreign.pk,
                subject_id=load_body["subject"],
                periods_per_year=70,
            )
    # Through the API it is simply not a known Grade.
    response = send(admin, "post", URL, {**load_body, "grade": foreign.pk, "periods_per_year": 70})
    assert response.status_code == 400


def test_the_board_reads_loads_and_nobody_else_but_the_admin_writes(
    schools, admin, load_body, setup
):
    a, _ = schools
    send(admin, "post", URL, {**load_body, "periods_per_year": 70})
    member(a, make_account("board@example.com", display_name="Board"), "principal_board")
    board = sign_in(A, "board@example.com")
    assert len(send(board, "get", URL).json()) == 1
    assert send(board, "post", URL, {**load_body, "periods_per_year": 35}).status_code == 403
    teacher = sign_in(A, "alice@example.com")  # the homeroom teacher of 7A
    assert send(teacher, "get", URL).status_code == 403


def test_the_app_role_never_deletes_a_load_or_moves_its_keys(schools, load_body):
    a, _ = schools
    with school_scope(a.pk):
        load = SubjectLoad.objects.create(
            school=a,
            school_year_id=load_body["school_year"],
            grade_id=load_body["grade"],
            subject_id=load_body["subject"],
            periods_per_year=70,
        )
        assert SubjectLoad.objects.filter(pk=load.pk).update(periods_per_year=71) == 1
    for sql in (
        "UPDATE schools_subjectload SET subject_id = subject_id",
        "DELETE FROM schools_subjectload",
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
            with connection.cursor() as cursor:
                cursor.execute(sql)
