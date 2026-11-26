"""Averages on the gradebook's rows (docs/slices/1b-slice-1.md, Part A): the detail's `averages`
in draft, submitted and approved books, the year average of a semester 2 book, the carried
`previous_semester_average` (API and database), and a carried cell filling an empty one for
`gradebook_incomplete`. The calculation itself is in `test_averages.py`."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from grades.models import CarriedResult, GradebookStep
from grades.tests.conftest import TODAY, staff
from schools.models import Enrollment, Student, Term
from schools.tests.factories import make_student
from tenancy.rls import school_scope
from testing import enroll

DAY = timedelta(days=1)
HOMEROOM = "alice@example.com"
TEACHER = "t1@example.com"
REVIEWER = "gl@example.com"
# Case A of the fixture, and the two semesters of case C (fixtures/averages_cases.json).
CASE_A = {"regular 1": 8, "regular 2": 7, "regular 3": 9, "mid_term 1": 6.5, "end_term 1": 7.5}
C_FIRST = {"regular 1": 6, "regular 2": 6, "regular 3": 6, "mid_term 1": 6.5, "end_term 1": 7}
C_SECOND = {"regular 1": 6, "regular 2": 6, "regular 3": 9, "mid_term 1": 8, "end_term 1": 8}
ALL_8 = dict.fromkeys(CASE_A, 8)
PREVIOUS = "previous_semester_average"


def key(name):
    """ "regular 1" -> ("regular", 1)."""
    kind, index = name.split()
    return kind, int(index)


@pytest.fixture
def fill(w, save, columns):
    """`fill(book, {student: {"regular 1": 8, ...}})`: t1 saves those cells (asserts a 200)."""

    def put(book, scores):
        ids = columns(book)
        cells = [
            {"column": ids[key(name)], "student": w[who].pk, "value": value, "expected": None}
            for who, values in scores.items()
            for name, value in values.items()
        ]
        response = save(book["id"], cells)
        assert response.status_code == 200, response.content
        return response

    return put


@pytest.fixture
def take(call, client_of):
    """`take(who, book, "submit")`: a step through the API (a response)."""
    return lambda who, book, action: call(
        client_of(who), "post", f"gradebooks/{book['id']}/{action}/", {}
    )


@pytest.fixture
def carry(call, client_of):
    return lambda book, student, results: call(
        client_of(HOMEROOM),
        "put",
        f"gradebooks/{book['id']}/students/{student.pk}/carried/",
        {"results": results},
    )


def averages_of(book, student):
    return next(r for r in book["students"] if r["id"] == student.pk)["averages"]


def detail(call, client_of, book, who=TEACHER):
    response = call(client_of(who), "get", f"gradebooks/{book['id']}/")
    assert response.status_code == 200, response.content
    return response.json()


@pytest.fixture
def second_semester(schools, w):
    """The same world with today inside HK II: HK I ended ten days ago, so Eve (in 7A since three
    days ago, a transfer in) arrived in HK II and has no semester 1 gradebook."""
    with school_scope(schools[0].pk):
        Term.objects.filter(pk=w["hk1"].pk).update(ends_on=TODAY - 10 * DAY)
        Term.objects.filter(pk=w["hk2"].pk).update(starts_on=TODAY - 9 * DAY)
        w["hk1"].refresh_from_db()
        w["hk2"].refresh_from_db()
    return w


# --- the grid ------------------------------------------------------------------------------------


def test_the_grid_carries_averages_in_draft_submitted_and_approved_books(
    w, book, fill, take, call, client_of, reviewers
):
    fill(book, {"an": CASE_A, "bao": ALL_8, "eve": ALL_8})
    an = averages_of(detail(call, client_of, book), w["an"])
    assert an["semester"] == {
        "value": 7.4,
        "result": None,
        "state": "provisional",
        "missing": [],
        "carried": False,
        "reason": None,
    }
    assert an["year"] is None  # HK I is the first of two terms
    dung = averages_of(detail(call, client_of, book), w["dung"])["semester"]
    assert (dung["state"], dung["value"]) == ("left", None)
    submitted = take(TEACHER, book, "submit")
    assert submitted.status_code == 200, submitted.content
    assert averages_of(submitted.json(), w["an"])["semester"]["state"] == "provisional"
    approved = take(REVIEWER, book, "approve")
    assert approved.status_code == 200, approved.content
    assert averages_of(approved.json(), w["an"])["semester"]["state"] == "final"
    assert averages_of(approved.json(), w["bao"])["semester"]["value"] == 8.0


def test_an_empty_cell_lists_the_column_and_a_comment_only_subject_gives_a_result(
    w, book, open_book, fill, columns, call, client_of
):
    fill(book, {"an": {k: v for k, v in CASE_A.items() if k != "end_term 1"}})
    an = averages_of(detail(call, client_of, book), w["an"])["semester"]
    assert (an["state"], an["value"]) == ("missing", None)
    assert an["missing"] == [{"kind": "end_term", "index": 1}]
    pe = open_book(subject=w["pe"])
    ids = columns(pe)
    cells = [
        {"column": ids["regular", i], "student": w["an"].pk, "result": r, "expected": None}
        for i, r in ((1, "pass"), (2, "fail"))
    ]
    assert (
        call(
            client_of(TEACHER), "put", f"gradebooks/{pe['id']}/cells/", {"cells": cells}
        ).status_code
        == 200
    )
    result = averages_of(detail(call, client_of, pe), w["an"])["semester"]
    assert (result["value"], result["result"], result["state"]) == (None, "fail", "provisional")


def test_a_student_on_two_gradebooks_of_the_subject_and_term_is_split(
    schools, w, book, open_book, call, client_of
):
    with school_scope(schools[0].pk):  # Dung went to 7B three days ago
        Enrollment.objects.create(
            school=schools[0],
            student=w["dung"],
            school_year=w["year"],
            school_class=w["7B"],
            valid_from=TODAY - 2 * DAY,
            reason_started=Enrollment.ReasonStarted.CLASS_CHANGE,
        )
    open_book(klass=w["7B"], client=client_of("t2@example.com"))
    dung = averages_of(detail(call, client_of, book), w["dung"])["semester"]
    assert dung["state"] == "split"


def test_a_student_or_a_guardian_reaches_no_gradebook(
    schools, w, book, call, client_of, guardian_of_an
):
    s_an = staff(schools[0], "s_an@example.com")
    with school_scope(schools[0].pk):
        Student.objects.filter(pk=w["an"].pk).update(membership=s_an)
    for who in ("s_an@example.com", guardian_of_an):
        assert call(client_of(who), "get", f"gradebooks/{book['id']}/").status_code == 403, who


# --- the year average ----------------------------------------------------------------------------


@pytest.fixture
def first_approved(second_semester, open_book, fill, take, reviewers):
    """MATH 7A HK I approved: An case C's first semester (6.5), Bao 8."""
    w = second_semester
    first = open_book(term=w["hk1"])
    fill(first, {"an": C_FIRST, "bao": ALL_8})
    assert take(TEACHER, first, "submit").status_code == 200
    assert take(REVIEWER, first, "approve").status_code == 200
    return first


def test_a_semester_2_book_shows_the_year_from_the_rounded_semesters(
    second_semester, first_approved, open_book, fill, carry, call, client_of
):
    w = second_semester
    second = open_book(term=w["hk2"])
    fill(second, {"an": C_SECOND, "eve": ALL_8})
    rows = detail(call, client_of, second)
    an = averages_of(rows, w["an"])
    assert an["semester"]["value"] == 7.6
    assert (an["year"]["value"], an["year"]["state"]) == (7.2, "provisional")
    bao = averages_of(rows, w["bao"])["year"]  # semester 2 is still empty
    assert (bao["value"], bao["state"]) == (None, "missing")
    eve = averages_of(rows, w["eve"])["year"]
    assert (eve["value"], eve["state"], eve["reason"]) == (None, "missing", "no_previous_average")
    saved = carry(second, w["eve"], [{"kind": PREVIOUS, "index": 1, "value": 6.9}])
    assert saved.status_code == 200, saved.content
    eve = averages_of(saved.json(), w["eve"])["year"]
    assert (eve["value"], eve["state"], eve["carried"]) == (7.6, "provisional", True)
    # The grid's per-column carried cells ignore it; the row's carried list shows it.
    row = next(r for r in saved.json()["students"] if r["id"] == w["eve"].pk)
    assert row["carried"] == [{"kind": PREVIOUS, "index": 1, "value": 6.9, "result": None}]


def test_a_year_with_three_terms_has_no_year_average(
    schools, second_semester, open_book, call, client_of
):
    w = second_semester
    with school_scope(schools[0].pk):
        Term.objects.filter(pk=w["hk2"].pk).update(ends_on=TODAY + 100 * DAY)
        Term.objects.create(
            school=schools[0],
            school_year=w["year"],
            name="HK III",
            starts_on=TODAY + 101 * DAY,
            ends_on=w["year"].ends_on,
        )
    year = averages_of(detail(call, client_of, open_book(term=w["hk2"])), w["an"])["year"]
    assert (year["state"], year["reason"]) == ("unavailable", "terms")


# --- the previous semester average ---------------------------------------------------------------


def test_a_previous_semester_average_round_trips_its_25_character_kind(
    schools, second_semester, open_book, carry
):
    w = second_semester
    second = open_book(term=w["hk2"])
    assert len(PREVIOUS) == 25
    assert (
        carry(second, w["eve"], [{"kind": PREVIOUS, "index": 1, "value": 6.9}]).status_code == 200
    )
    with school_scope(schools[0].pk):
        stored = CarriedResult.objects.get()
    assert (stored.kind, stored.index, stored.value) == (PREVIOUS, 1, Decimal("6.9"))


def test_the_api_takes_a_previous_average_only_for_a_scored_subject_of_a_later_term(
    second_semester, open_book, carry
):
    w = second_semester
    first, pe = open_book(term=w["hk1"]), open_book(term=w["hk2"], subject=w["pe"])
    second = open_book(term=w["hk2"])
    refused = [{"kind": PREVIOUS, "index": 1, "code": "unknown_column"}]
    with school_scope(w["a"].pk):  # Eve arrived in HK I in this copy, for the first-term case
        Enrollment.objects.filter(student=w["eve"]).update(valid_from=w["hk1"].ends_on - 2 * DAY)
    response = carry(first, w["eve"], [{"kind": PREVIOUS, "index": 1, "value": 6.9}])
    assert (response.status_code, response.json()) == (400, {"results": refused})
    with school_scope(w["a"].pk):
        Enrollment.objects.filter(student=w["eve"]).update(valid_from=TODAY - 3 * DAY)
    response = carry(pe, w["eve"], [{"kind": PREVIOUS, "index": 1, "result": "pass"}])
    assert (response.status_code, response.json()) == (400, {"results": refused})
    response = carry(second, w["eve"], [{"kind": PREVIOUS, "index": 2, "value": 6.9}])
    assert response.json() == {
        "results": [{"kind": PREVIOUS, "index": 2, "code": "unknown_column"}]
    }
    response = carry(second, w["an"], [{"kind": PREVIOUS, "index": 1, "value": 6.9}])
    assert response.json() == {"student": ["not_arrived"]}
    assert (
        carry(second, w["eve"], [{"kind": PREVIOUS, "index": 1, "value": 6.9}]).status_code == 200
    )


def previous(a, w, **kw):
    fields = {"student": w["eve"], "term": w["hk2"], "subject": w["math"], "kind": PREVIOUS}
    fields |= {"index": 1, "value": Decimal("6.9"), "entered_by": w["t1"]} | kw
    return CarriedResult.objects.create(school=a, **fields)


def test_the_database_takes_a_previous_average_only_for_a_scored_subject_of_a_later_term(
    schools, second_semester, refused
):
    a, w = schools[0], second_semester
    refused("carriedresult_previous_average_fits", a, lambda: previous(a, w, term=w["hk1"]))
    refused(
        "carriedresult_previous_average_fits",
        a,
        lambda: previous(a, w, subject=w["pe"], value=None, result="pass"),
    )
    refused("carriedresult_student_arrived_in_term", a, lambda: previous(a, w, student=w["an"]))
    refused("carriedresult_periodic_is_single", a, lambda: previous(a, w, index=2))
    with school_scope(a.pk):
        previous(a, w)


# --- a carried cell fills an empty one -----------------------------------------------------------


def test_a_carried_cell_counts_as_filled_for_submit_and_an_empty_one_is_still_refused(
    schools, w, book, fill, carry, columns, take, refused, call, client_of
):
    a = schools[0]
    fill(book, {"an": CASE_A, "bao": CASE_A})
    # Case E of the fixture: regular 1 carried, the rest local (end-term first left empty).
    fill(book, {"eve": {"regular 2": 8, "regular 3": 9, "mid_term 1": 6.5}})
    assert carry(book, w["eve"], [{"kind": "regular", "index": 1, "value": 7}]).status_code == 200
    ids = columns(book)
    response = take(TEACHER, book, "submit")
    assert response.status_code == 400
    assert response.json() == {
        "cells": [{"column": ids["end_term", 1], "student": w["eve"].pk, "code": "incomplete"}]
    }

    def step():  # straight to the database, past the API's own check
        return GradebookStep.objects.create(
            school=a, gradebook_id=book["id"], action="submit", by=w["t1"]
        )

    refused("gradebook_incomplete", a, step)
    fill(book, {"eve": {"end_term 1": 7.5}})
    with school_scope(a.pk):
        step()  # the carried regular 1 fills Eve's cell in the database too
    eve = averages_of(detail(call, client_of, book), w["eve"])["semester"]
    assert (eve["value"], eve["state"], eve["carried"]) == (7.4, "provisional", True)


# --- bounded queries -----------------------------------------------------------------------------


def test_the_query_count_does_not_grow_with_the_roster(
    schools, second_semester, first_approved, open_book, fill, call, client_of
):
    a, w = schools[0], second_semester
    second = open_book(term=w["hk2"])
    fill(second, {"an": C_SECOND})
    client = client_of(TEACHER)

    def count():
        with CaptureQueriesContext(connection) as queries:
            assert call(client, "get", f"gradebooks/{second['id']}/").status_code == 200
        return len(queries)

    before = count()
    with school_scope(a.pk):
        for n in range(27):  # 30 students in 7A
            enroll(a, make_student(a, f"S{n:02}"), w["7A"])
        assert Enrollment.objects.filter(school_class=w["7A"], valid_to__isnull=True).count() == 30
    assert count() == before
