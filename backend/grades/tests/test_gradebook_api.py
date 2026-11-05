"""Opening, reading and releasing gradebooks, subject loads and who may do what."""

import threading
import time
from datetime import timedelta

import pytest
from django.db import connections
from django.utils import timezone

from accounts.models import RoleAssignment
from audit.models import AuditEvent
from grades.models import Gradebook, GradebookColumn
from schools.models import AssessmentProfileVersion, SubjectLoad
from schools.tests.factories import make_primary_class, make_subject
from tenancy.rls import school_scope
from testing import owner_role

TODAY = timezone.localdate()
DAY = timedelta(days=1)


def shape(book):
    """The columns of a gradebook's JSON as {kind: count}."""
    counts = {}
    for column in book["columns"]:
        counts[column["kind"]] = counts.get(column["kind"], 0) + 1
    return counts


def set_periods(a, w, subject, periods):
    with school_scope(a.pk):
        SubjectLoad.objects.filter(subject=subject).update(periods_per_year=periods)


# --- opening ---------------------------------------------------------------------------------


def test_the_subject_teacher_opens_a_gradebook_with_the_columns_the_profile_gives(
    schools, w, book, call, client_of
):
    # 70 periods a year: three regular columns, then the mid-term and the end-term test.
    assert shape(book) == {"regular": 3, "mid_term": 1, "end_term": 1}
    assert [(c["kind"], c["index"]) for c in book["columns"]] == [
        ("regular", 1),
        ("regular", 2),
        ("regular", 3),
        ("mid_term", 1),
        ("end_term", 1),
    ]
    assert (book["status"], book["term_name"], book["class_name"], book["subject_name"]) == (
        "draft",
        "HK I",
        "7A",
        "MATH",
    )
    assert book["profile_source"].startswith("Circular 22/2021")
    assert all(c["released_at"] is None for c in book["columns"])
    # Opening it again finds it (200), with the same columns.
    again = call(
        client_of("t1@example.com"),
        "post",
        "gradebooks/",
        {"term": w["hk1"].pk, "subject": w["math"].pk, "school_class": w["7A"].pk},
    )
    assert (again.status_code, again.json()["id"]) == (200, book["id"])
    assert again.json()["columns"] == book["columns"]
    with school_scope(schools[0].pk):
        assert Gradebook.objects.count() == 1


@pytest.mark.parametrize(
    ("periods", "regular"),
    [(1, 2), (35, 2), (36, 3), (70, 3), (71, 4), (400, 4)],
)
def test_the_regular_columns_follow_the_periods_per_year(schools, w, open_book, periods, regular):
    set_periods(schools[0], w, w["math"], periods)
    assert shape(open_book()) == {"regular": regular, "mid_term": 1, "end_term": 1}


def test_a_comment_only_subject_gets_the_profiles_comment_only_count(schools, w, open_book):
    # 400 periods would give a scored subject four regular columns; the form decides.
    set_periods(schools[0], w, w["pe"], 400)
    book = open_book(subject=w["pe"])
    assert shape(book) == {"regular": 2, "mid_term": 1, "end_term": 1}
    assert book["assessment"] == "comment_only"


def test_a_missing_subject_load_or_profile_version_is_refused(schools, w, call, client_of):
    a, _ = schools
    # A subject with a teacher but no load.
    with school_scope(a.pk):
        lit = make_subject(a, "LIT")
        RoleAssignment.objects.create(
            school=a,
            membership=w["t1"],
            role=RoleAssignment.Role.SUBJECT_TEACHER,
            school_year=w["year"],
            subject=lit,
            school_class=w["7A"],
            valid_from=TODAY - 30 * DAY,
        )
    body = {"term": w["hk1"].pk, "subject": lit.pk, "school_class": w["7A"].pk}
    response = call(client_of("t1@example.com"), "post", "gradebooks/", body)
    assert (response.status_code, response.json()) == (400, {"gradebook": ["no_subject_load"]})
    # No version of the profile in force on the school year's first day.
    with owner_role():
        AssessmentProfileVersion.objects.all().delete()
    response = call(
        client_of("t1@example.com"),
        "post",
        "gradebooks/",
        {"term": w["hk1"].pk, "subject": w["math"].pk, "school_class": w["7A"].pk},
    )
    assert (response.status_code, response.json()) == (400, {"gradebook": ["no_profile_version"]})
    with school_scope(a.pk):
        assert Gradebook.objects.count() == 0


def test_the_version_is_the_one_in_force_on_the_years_first_day_and_never_changes(
    schools, w, open_book, call, client_of
):
    old = AssessmentProfileVersion.objects.get(level_kind="lower_secondary")
    # A later version starts tomorrow; the year began a month ago, so it still gets the old one.
    with owner_role():
        AssessmentProfileVersion.objects.filter(pk=old.pk).update(effective_to=TODAY)
        AssessmentProfileVersion.objects.create(
            level_kind="lower_secondary",
            effective_from=TODAY + DAY,
            source="Circular 89/2026",
            rules=old.rules,
        )
    book = open_book()
    assert book["profile_source"] == old.source
    again = call(client_of("t1@example.com"), "get", f"gradebooks/{book['id']}/")
    assert again.json()["profile_source"] == old.source
    with school_scope(schools[0].pk):
        assert Gradebook.objects.get().profile_version_id == old.pk


def test_a_primary_class_or_a_term_of_another_year_is_refused(schools, w, call, client_of):
    a, _ = schools
    with school_scope(a.pk):
        primary = make_primary_class(a, w["year"], "3A")
        SubjectLoad.objects.create(
            school=a,
            school_year=w["year"],
            grade=primary.grade,
            subject=w["math"],
            periods_per_year=70,
        )
        RoleAssignment.objects.create(
            school=a,
            membership=w["t1"],
            role=RoleAssignment.Role.SUBJECT_TEACHER,
            school_year=w["year"],
            subject=w["math"],
            school_class=primary,
            valid_from=TODAY - 30 * DAY,
        )
    response = call(
        client_of("t1@example.com"),
        "post",
        "gradebooks/",
        {"term": w["hk1"].pk, "subject": w["math"].pk, "school_class": primary.pk},
    )
    # Circular 22/2021 has no profile for Primary (the trigger `gradebook_secondary_level` holds
    # the rule for anything that reaches the table another way).
    assert (response.status_code, response.json()) == (400, {"gradebook": ["no_profile_version"]})


# --- who may do what -------------------------------------------------------------------------


def test_the_teacher_of_the_pair_opens_and_nobody_else(
    schools, w, call, client_of, board_member, guardian_of_an
):
    body = {"term": w["hk1"].pk, "subject": w["math"].pk, "school_class": w["7A"].pk}
    # t2 teaches MATH in 7B, alice is the homeroom teacher of 7A, the board and the School admin
    # do not teach, the Guardian has no right to scores at all.
    for who in (
        "t2@example.com",
        "alice@example.com",
        board_member,
        "admin-a@example.com",
        guardian_of_an,
    ):
        client = client_of(who)
        assert call(client, "post", "gradebooks/", body).status_code == 403, who
    with school_scope(schools[0].pk):
        assert Gradebook.objects.count() == 0
    assert call(client_of("t3@example.com"), "post", "gradebooks/", body).status_code == 201


def test_teachers_and_the_board_read_it_but_the_school_admin_and_guardians_do_not(
    schools, w, book, call, client_of, board_member, guardian_of_an
):
    for who in ("t2@example.com", "alice@example.com", board_member):
        client = client_of(who)
        detail = call(client, "get", f"gradebooks/{book['id']}/")
        assert detail.status_code == 200, who
        assert detail.json()["can_enter"] is False
        assert call(client, "get", "gradebooks/").json()[0]["id"] == book["id"]
        column = book["columns"][0]["id"]
        history = f"gradebooks/{book['id']}/history/?column={column}&student={w['an'].pk}"
        assert call(client, "get", history).status_code == 200
        assert (
            call(client, "put", f"gradebooks/{book['id']}/cells/", {"cells": []}).status_code == 403
        )
        release = call(
            client, "post", f"gradebooks/{book['id']}/columns/{book['columns'][0]['id']}/release/"
        )
        assert release.status_code == 403
    for who in ("admin-a@example.com", guardian_of_an):
        client = client_of(who)
        assert call(client, "get", f"gradebooks/{book['id']}/").status_code == 403, who
        assert call(client, "get", "gradebooks/").status_code == 403, who
        assert call(client, "get", "gradebooks/mine/").status_code == 403, who
    assert call(client_of("t1@example.com"), "get", f"gradebooks/{book['id']}/").json()["can_enter"]


def test_a_gradebook_of_another_school_is_not_found(schools, w, book, call, admin_b):
    from testing import B, sign_in

    client = sign_in(B, "admin-b@example.com")
    response = client.get(f"/api/setup/gradebooks/{book['id']}/", HTTP_HOST=B)
    assert response.status_code in (403, 404)


# --- reading ---------------------------------------------------------------------------------


def test_the_grid_lists_every_student_enrolled_during_the_term_with_who_is_still_in(
    schools, w, book, call, client_of
):
    detail = call(client_of("alice@example.com"), "get", f"gradebooks/{book['id']}/").json()
    rows = [(s["name"], s["in_class"]) for s in detail["students"]]
    # An (setup), Bao, Dung (left three days ago, kept, read only) and Eve (arrived three days
    # ago); Binh is in 7B and Chi in a Primary class.
    assert rows == [("An", True), ("Bao", True), ("Dung", False), ("Eve", True)]
    assert all(s["cells"] == [] for s in detail["students"])


def test_the_gradebooks_list_filters_by_term_class_and_subject(
    schools, w, book, open_book, call, client_of
):
    other = open_book(term=w["hk2"])
    pe = open_book(subject=w["pe"])
    client = client_of("t2@example.com")  # any teacher reads them all
    listed = lambda query: sorted(  # noqa: E731
        g["id"] for g in call(client, "get", f"gradebooks/?{query}").json()
    )
    assert listed("") == sorted([book["id"], other["id"], pe["id"]])
    assert listed(f"term={w['hk2'].pk}") == [other["id"]]
    assert listed(f"subject={w['pe'].pk}") == [pe["id"]]
    assert listed(f"school_class={w['7B'].pk}") == []
    assert call(client, "get", "gradebooks/?term=x").status_code == 400


def test_mine_lists_the_teachers_pairs_this_year_with_each_terms_gradebook(
    schools, w, book, call, client_of
):
    with school_scope(schools[0].pk):  # a Primary class has no gradebook: it is not listed
        primary = make_primary_class(schools[0], w["year"], "3A")
        RoleAssignment.objects.create(
            school=schools[0],
            membership=w["t1"],
            role=RoleAssignment.Role.SUBJECT_TEACHER,
            school_year=w["year"],
            subject=w["math"],
            school_class=primary,
            valid_from=TODAY - 30 * DAY,
        )
    mine = call(client_of("t1@example.com"), "get", "gradebooks/mine/").json()
    assert [(p["subject_name"], p["class_name"]) for p in mine] == [("MATH", "7A"), ("PE", "7A")]
    math, pe = mine
    assert [(t["term_name"], t["gradebook"], t["status"]) for t in math["terms"]] == [
        ("HK I", book["id"], "draft"),
        ("HK II", None, None),
    ]
    assert all(t["gradebook"] is None for t in pe["terms"])
    only_7b = call(client_of("t2@example.com"), "get", "gradebooks/mine/").json()
    assert [(p["subject_name"], p["class_name"]) for p in only_7b] == [("MATH", "7B")]
    assert call(client_of("alice@example.com"), "get", "gradebooks/mine/").json() == []


# --- releasing a column ----------------------------------------------------------------------


def release(call, client, book, column):
    return call(client, "post", f"gradebooks/{book['id']}/columns/{column}/release/")


def test_a_column_is_released_once_when_every_student_still_in_the_class_has_a_score(
    schools, w, book, columns, save, call, client_of
):
    first = columns(book)["regular", 1]
    t1 = client_of("t1@example.com")

    def put(student, value, expected):
        cell = {"column": first, "student": w[student].pk, "value": value, "expected": expected}
        response = save(book["id"], [cell])
        assert response.status_code == 200, response.content
        return response.json()["cells"][0]["entry"]

    put("an", 7, None)
    # Bao and Eve have no score; Dung left the class, so he is not asked for one.
    refused = release(call, t1, book, first)
    assert refused.status_code == 400
    assert refused.json()["column"] == ["incomplete"]
    assert [s["name"] for s in refused.json()["students"]] == ["Bao", "Eve"]
    put("eve", 9, None)
    cleared = put("bao", None, put("bao", 8, None))  # a cleared cell is no score
    result = release(call, t1, book, first)
    assert [s["name"] for s in result.json().get("students", [])] == ["Bao"], result.content
    put("bao", 8, cleared)
    released = release(call, t1, book, first)
    assert released.status_code == 200
    assert released.json()["released_at"] is not None
    # Once: a second release is refused and the first stays.
    again = release(call, t1, book, first)
    assert (again.status_code, again.json()) == (400, {"column": ["already_released"]})
    with school_scope(schools[0].pk):
        column = GradebookColumn.objects.get(pk=first)
    assert column.released_by_id == w["t1"].pk
    assert column.released_at is not None
    # The grid shows it released; the other columns are not.
    detail = call(t1, "get", f"gradebooks/{book['id']}/").json()
    assert [c["released_at"] is not None for c in detail["columns"]] == [
        True,
        False,
        False,
        False,
        False,
    ]


def test_only_the_teacher_of_the_pair_releases_and_a_column_of_another_gradebook_is_not_found(
    schools, w, book, columns, call, client_of
):
    assert (
        release(call, client_of("t2@example.com"), book, columns(book)["regular", 1]).status_code
        == 403
    )
    assert release(call, client_of("t1@example.com"), book, 999999).status_code == 404


# --- audit -----------------------------------------------------------------------------------


def test_opening_and_releasing_are_audited_and_no_score_reaches_the_log(
    schools, w, book, columns, save, call, client_of
):
    a, _ = schools
    cols = columns(book)
    t1 = client_of("t1@example.com")
    for student in ("an", "bao", "eve"):
        save(
            book["id"],
            [
                {
                    "column": cols["regular", 1],
                    "student": w[student].pk,
                    "value": 7.5,
                    "expected": None,
                }
            ],
        )
    assert release(call, t1, book, cols["regular", 1]).status_code == 200
    with school_scope(a.pk):
        events = list(AuditEvent.objects.filter(target_table__startswith="grades_"))
    kinds = sorted((e.target_table, e.action) for e in events)
    assert kinds == [("grades_gradebook", "insert"), ("grades_gradebookcolumn", "update")]
    # Who released it, when; no score anywhere in the log, and no entry of one.
    assert "7.5" not in str([e.details for e in events])
    with school_scope(a.pk):
        assert not AuditEvent.objects.filter(target_table="grades_scoreentry").exists()
        assert "7.5" not in str(list(AuditEvent.objects.values_list("details", flat=True)))


# --- opening, concurrently -------------------------------------------------------------------


def test_two_openings_at_once_make_one_gradebook(schools, w, call, client_of):
    gate = threading.Barrier(2)
    results = {}
    body = {"term": w["hk1"].pk, "subject": w["math"].pk, "school_class": w["7A"].pk}

    def go(who):
        def run():
            try:
                client = client_of(who)
                gate.wait()
                results[who] = call(client, "post", "gradebooks/", body)
            finally:
                connections.close_all()

        return threading.Thread(target=run)

    threads = [go("t1@example.com"), go("t3@example.com")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert sorted(r.status_code for r in results.values()) == [200, 201]
    assert len({r.json()["id"] for r in results.values()}) == 1
    with school_scope(schools[0].pk):
        assert Gradebook.objects.count() == 1
        assert GradebookColumn.objects.count() == 5


def test_opening_waits_for_an_edit_of_the_subject_load_and_uses_what_it_committed(
    schools, w, call, client_of, app_conn
):
    """The load decides the columns and freezes once a gradebook exists: an edit in flight holds
    the row, the opening waits for it and opens with the edited load."""
    a, _ = schools
    app_conn.execute("BEGIN")
    app_conn.execute("SELECT set_config('app.school_id', %s, true)", [str(a.pk)])
    app_conn.execute(
        "UPDATE schools_subjectload SET periods_per_year = 71 WHERE subject_id = %s", [w["math"].pk]
    )
    results = {}

    def open_():
        try:
            results["book"] = call(
                client_of("t1@example.com"),
                "post",
                "gradebooks/",
                {"term": w["hk1"].pk, "subject": w["math"].pk, "school_class": w["7A"].pk},
            )
        finally:
            connections.close_all()

    thread = threading.Thread(target=open_)
    thread.start()
    time.sleep(0.5)
    assert thread.is_alive()
    app_conn.execute("COMMIT")
    thread.join(10)
    assert results["book"].status_code == 201
    assert shape(results["book"].json()) == {"regular": 4, "mid_term": 1, "end_term": 1}
