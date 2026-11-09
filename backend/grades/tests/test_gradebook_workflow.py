"""The gradebook workflow through the API: who takes each step, from which status, what each
answers, and what the detail, `?to_review=1` and `mine/` show of it. The rules the database holds
under it are in `test_gradebook_rules.py`."""

import threading

import pytest
from django.db import connections

from audit.models import AuditEvent
from grades.models import GradebookColumn, GradebookStep, ScoreEntry
from tenancy.rls import school_scope

TEACHER, GROUP_LEADER, BOSS, BOARD = (
    "t1@example.com",
    "gl@example.com",
    "boss@example.com",
    "board@example.com",
)


@pytest.fixture
def step(call, client_of):
    """`step(who, book, "submit", body=None)`: POST that step as `who` (a response)."""

    def post(who, book, action, body=None):
        return call(client_of(who), "post", f"gradebooks/{book['id']}/{action}/", body or {})

    return post


@pytest.fixture
def filled(w, book, columns, save):
    """MATH, 7A, HK I with a score for An, Bao and Eve (those in the class) in every column."""
    cells = [
        {"column": column, "student": w[student].pk, "value": 7, "expected": None}
        for column in columns(book).values()
        for student in ("an", "bao", "eve")
    ]
    response = save(book["id"], cells)
    assert response.status_code == 200, response.content
    return book


@pytest.fixture
def submitted(filled, step):
    assert step(TEACHER, filled, "submit").status_code == 200
    return filled


@pytest.fixture
def detail_of(call, client_of):
    return lambda who, book: call(client_of(who), "get", f"gradebooks/{book['id']}/").json()


# --- submit and withdraw ---------------------------------------------------------------------


def test_the_subject_teacher_submits_a_complete_gradebook_and_takes_it_back(
    schools, w, filled, step, call, client_of, columns
):
    submit = step(TEACHER, filled, "submit")
    assert submit.status_code == 200, submit.content
    body = submit.json()
    assert body["status"] == "submitted"
    assert [(s["action"], s["by_name"], s["comment"]) for s in body["steps"]] == [
        ("submit", TEACHER, "")
    ]
    # Locked: the cells refuse a save, release stays open.
    cell = {"column": columns(filled)["regular", 1], "student": w["an"].pk, "value": 9}
    saved = call(
        client_of(TEACHER),
        "put",
        f"gradebooks/{filled['id']}/cells/",
        {"cells": [cell | {"expected": 1}]},
    )
    assert (saved.status_code, saved.json()) == (400, {"gradebook": ["not_draft"]})
    released = call(
        client_of(TEACHER),
        "post",
        f"gradebooks/{filled['id']}/columns/{columns(filled)['regular', 1]}/release/",
    )
    assert released.status_code == 200, released.content
    withdrawn = step(TEACHER, filled, "withdraw")
    assert (withdrawn.status_code, withdrawn.json()["status"]) == (200, "draft")
    assert [s["action"] for s in withdrawn.json()["steps"]] == ["submit", "withdraw"]


def test_only_the_subject_teacher_of_the_pair_submits_or_withdraws(
    schools, w, filled, step, reviewers, board_member, guardian_of_an, detail_of
):
    outsiders = ("t2@example.com", "alice@example.com", board_member, GROUP_LEADER, BOSS)
    for who in (*outsiders, "admin-a@example.com", guardian_of_an):
        assert step(who, filled, "submit").status_code == 403, who
    assert detail_of(TEACHER, filled)["status"] == "draft"
    # t3 teaches MATH in 7A too: a subject teacher of the pair may take it, and take it back.
    assert step("t3@example.com", filled, "submit").status_code == 200
    for who in (*outsiders, "admin-a@example.com", guardian_of_an):
        assert step(who, filled, "withdraw").status_code == 403, who
    assert detail_of(TEACHER, filled)["status"] == "submitted"
    assert step(TEACHER, filled, "withdraw").status_code == 200


def test_a_step_from_the_wrong_status_is_refused_as_wrong_state(
    schools, w, filled, step, reviewers, board_member
):
    wrong = {"status": ["wrong_state"]}
    by_action = {
        "withdraw": TEACHER,
        "approve": GROUP_LEADER,
        "return": GROUP_LEADER,
        "reopen": BOSS,
    }
    for action, who in by_action.items():  # a draft: only a submit
        response = step(who, filled, action, {"comment": "x", "reason": "x"})
        assert (response.status_code, response.json()) == (400, wrong), action
    assert step(TEACHER, filled, "submit").status_code == 200
    for action, who in (("submit", TEACHER), ("reopen", BOSS)):  # submitted: not these
        response = step(who, filled, action, {"reason": "x"})
        assert (response.status_code, response.json()) == (400, wrong), action
    assert step(GROUP_LEADER, filled, "approve").status_code == 200
    for action, who in (
        ("submit", TEACHER),
        ("withdraw", TEACHER),
        ("return", GROUP_LEADER),
        ("approve", GROUP_LEADER),
    ):  # approved: only a reopen
        response = step(who, filled, action, {"comment": "x"})
        assert (response.status_code, response.json()) == (400, wrong), action
    with school_scope(schools[0].pk):
        assert GradebookStep.objects.count() == 2


def test_submit_names_the_empty_cells_of_students_still_in_the_class(
    schools, w, book, columns, save, step
):
    cols = columns(book)
    first, last = cols["regular", 1], cols["end_term", 1]
    save(
        book["id"],
        [
            {"column": column, "student": w[student].pk, "value": 6, "expected": None}
            for column in cols.values()
            for student in ("an", "bao", "eve")
            if (column, student) not in ((first, "bao"), (last, "eve"))
        ],
    )
    response = step(TEACHER, book, "submit")
    assert response.status_code == 400
    assert response.json() == {
        "cells": [
            {"column": first, "student": w["bao"].pk, "code": "incomplete"},
            {"column": last, "student": w["eve"].pk, "code": "incomplete"},
        ]
    }
    with school_scope(schools[0].pk):
        assert not GradebookStep.objects.exists()


# --- return, approve, reopen -----------------------------------------------------------------


def test_the_group_leader_returns_with_a_comment_and_the_teacher_sees_it_until_resubmitting(
    schools, w, submitted, step, reviewers, detail_of, call, client_of
):
    for body in ({}, {"comment": ""}, {"comment": "   "}, {"comment": None}):
        refused = step(GROUP_LEADER, submitted, "return", body)
        assert (refused.status_code, refused.json()) == (400, {"comment": ["required"]}), body
    assert step(GROUP_LEADER, submitted, "return", {"comment": "x" * 501}).status_code == 400
    returned = step(GROUP_LEADER, submitted, "return", {"comment": "Check the mid-term"})
    assert returned.status_code == 200, returned.content
    assert returned.json()["status"] == "draft"
    assert returned.json()["return_comment"] == "Check the mid-term"
    assert detail_of(TEACHER, submitted)["return_comment"] == "Check the mid-term"
    assert detail_of(TEACHER, submitted)["steps"][-1]["by_name"] == GROUP_LEADER
    mine = call(client_of(TEACHER), "get", "gradebooks/mine/").json()
    math = next(p for p in mine if p["subject_name"] == "MATH")
    assert [(t["status"], t["returned"]) for t in math["terms"]] == [("draft", True), (None, False)]
    # Resubmitted: the comment goes, the steps stay.
    resubmitted = step(TEACHER, submitted, "submit")
    assert resubmitted.json()["return_comment"] is None
    assert [s["action"] for s in resubmitted.json()["steps"]] == ["submit", "return", "submit"]
    mine = call(client_of(TEACHER), "get", "gradebooks/mine/").json()
    math = next(p for p in mine if p["subject_name"] == "MATH")
    assert (math["terms"][0]["status"], math["terms"][0]["returned"]) == ("submitted", False)


def test_only_a_reviewer_returns_or_approves_and_never_the_teacher(
    schools, w, submitted, step, reviewers, board_member, guardian_of_an
):
    for who in ("t2@example.com", "t3@example.com", "alice@example.com", "admin-a@example.com"):
        assert step(who, submitted, "approve").status_code == 403, who
        assert step(who, submitted, "return", {"comment": "no"}).status_code == 403, who
    assert step(TEACHER, submitted, "approve").status_code == 403
    assert step(guardian_of_an, submitted, "approve").status_code == 403
    # The board reviews the whole School (no duty needed).
    assert step(board_member, submitted, "return", {"comment": "again"}).status_code == 200
    assert step(TEACHER, submitted, "submit").status_code == 200
    assert step(GROUP_LEADER, submitted, "approve").status_code == 200


def test_the_group_leader_of_another_subject_does_not_review(
    schools, w, submitted, step, reviewers
):
    assert step("gl2@example.com", submitted, "approve").status_code == 403
    assert step("gl2@example.com", submitted, "return", {"comment": "no"}).status_code == 403


def test_nobody_reviews_their_own_gradebook_even_as_group_leader(
    schools, w, submitted, step, reviewers, lead_math
):
    lead_math(w["t1"])
    refused = step(TEACHER, submitted, "return", {"comment": "mine"})
    assert (refused.status_code, refused.json()) == (400, {"status": ["own_submission"]})
    refused = step(TEACHER, submitted, "approve")
    assert (refused.status_code, refused.json()) == (400, {"status": ["own_submission"]})
    # Another reviewer may; a teacher who did not submit may review it if they lead the group.
    assert step(GROUP_LEADER, submitted, "approve").status_code == 200


def test_approving_releases_the_columns_still_unreleased_in_the_approvers_name(
    schools, w, submitted, step, reviewers, columns, call, client_of
):
    first = columns(submitted)["regular", 1]
    released = call(
        client_of(TEACHER), "post", f"gradebooks/{submitted['id']}/columns/{first}/release/"
    )
    assert released.status_code == 200
    earlier = released.json()["released_at"]
    approved = step(GROUP_LEADER, submitted, "approve")
    assert approved.status_code == 200, approved.content
    assert approved.json()["status"] == "approved"
    cols = approved.json()["columns"]
    assert all(c["released_at"] is not None for c in cols)
    assert next(c for c in cols if c["id"] == first)["released_at"] == earlier  # not moved
    with school_scope(schools[0].pk):
        by = {
            c.pk: c.released_by_id
            for c in GradebookColumn.objects.filter(gradebook=submitted["id"])
        }
        times = {c.released_at for c in GradebookColumn.objects.exclude(pk=first)}
    assert by[first] == w["t1"].pk
    assert {v for k, v in by.items() if k != first} == {reviewers["gl"].pk}
    assert len(times) == 1  # the clock was read once
    with school_scope(schools[0].pk):  # every release is later than every score
        latest = ScoreEntry.objects.latest("entered_at").entered_at
        assert min(times) >= latest


def test_reopening_needs_the_duty_and_a_reason_and_edits_after_it_are_logged(
    schools, w, submitted, step, reviewers, board_member, columns, call, client_of, detail_of
):
    assert step(GROUP_LEADER, submitted, "approve").status_code == 200
    for who in (TEACHER, GROUP_LEADER, board_member, "alice@example.com", "admin-a@example.com"):
        assert step(who, submitted, "reopen", {"reason": "typo"}).status_code == 403, who
    for body in ({}, {"reason": ""}, {"reason": "  "}):
        refused = step(BOSS, submitted, "reopen", body)
        assert (refused.status_code, refused.json()) == (400, {"reason": ["required"]}), body
    reopened = step(BOSS, submitted, "reopen", {"reason": "Bao's mid-term was mistyped"})
    assert reopened.status_code == 200, reopened.content
    body = reopened.json()
    assert body["status"] == "draft"
    assert body["return_comment"] is None  # a reopen is no return
    assert (body["steps"][-1]["action"], body["steps"][-1]["comment"]) == (
        "reopen",
        "Bao's mid-term was mistyped",
    )
    # Editable again; every column was released, so a change shows as after the release.
    cell = {
        "column": columns(submitted)["regular", 1],
        "student": w["bao"].pk,
        "value": 8,
        "expected": next(
            c["entry"]
            for s in body["students"]
            if s["id"] == w["bao"].pk
            for c in s["cells"]
            if c["column"] == columns(submitted)["regular", 1]
        ),
    }
    saved = call(
        client_of(TEACHER), "put", f"gradebooks/{submitted['id']}/cells/", {"cells": [cell]}
    )
    assert saved.status_code == 200, saved.content
    after = detail_of(TEACHER, submitted)
    bao = next(s for s in after["students"] if s["name"] == "Bao")
    assert [c["changed_after_release"] for c in bao["cells"] if c["column"] == cell["column"]] == [
        True
    ]


# --- the detail, the review list and mine ----------------------------------------------------


def test_the_detail_lists_the_steps_and_what_this_member_may_take_now(
    schools, w, filled, step, reviewers, board_member, detail_of, guardian_of_an
):
    can = lambda who: detail_of(who, filled)["can"]  # noqa: E731
    assert can(TEACHER) == ["submit"]
    assert can("t2@example.com") == []
    assert can(GROUP_LEADER) == []
    step(TEACHER, filled, "submit")
    assert can(TEACHER) == ["withdraw"]
    assert sorted(can(GROUP_LEADER)) == ["approve", "return"]
    assert sorted(can(BOARD)) == ["approve", "return"]
    assert sorted(can(BOSS)) == ["approve", "return"]
    assert can("alice@example.com") == []
    step(GROUP_LEADER, filled, "approve")
    assert can(TEACHER) == [] and can(GROUP_LEADER) == [] and can(BOARD) == []
    assert can(BOSS) == ["reopen"]


def test_can_leaves_out_a_review_of_ones_own_submission(
    schools, w, filled, step, reviewers, lead_math, detail_of
):
    lead_math(w["t1"])
    step(TEACHER, filled, "submit")
    assert detail_of(TEACHER, filled)["can"] == ["withdraw"]
    assert sorted(detail_of(GROUP_LEADER, filled)["can"]) == ["approve", "return"]


def test_to_review_lists_the_submitted_gradebooks_the_member_may_review_newest_first(
    schools,
    w,
    filled,
    open_book,
    step,
    reviewers,
    lead_math,
    board_member,
    call,
    client_of,
    save,
    columns,
):
    pe = open_book(subject=w["pe"])
    other = open_book(term=w["hk2"])
    review = lambda who: [  # noqa: E731
        g["id"] for g in call(client_of(who), "get", "gradebooks/?to_review=1").json()
    ]
    assert review(GROUP_LEADER) == review(BOARD) == []  # nothing submitted yet
    for book in (other, filled):  # `filled` is submitted last: newest first
        if book is other:
            cells = [
                {"column": c, "student": w[s].pk, "value": 5, "expected": None}
                for c in columns(other).values()
                for s in ("an", "bao", "eve")
            ]
            assert save(other["id"], cells).status_code == 200
        assert step(TEACHER, book, "submit").status_code == 200
    assert review(GROUP_LEADER) == [filled["id"], other["id"]]
    assert review(BOARD) == [filled["id"], other["id"]]
    # Not reviewers: a teacher of another class, the homeroom teacher; a draft is not listed.
    assert review("t2@example.com") == review("alice@example.com") == []
    assert pe["id"] not in review(BOARD)
    # Each item says who submitted it and when (the ticket "Nộp bởi …").
    listed = call(client_of(GROUP_LEADER), "get", "gradebooks/?to_review=1").json()
    assert {g["submitted_by_name"] for g in listed} == {TEACHER}  # accounts are named by email
    assert all(g["submitted_at"] for g in listed)
    # Not the ones the member submitted themselves.
    lead_math(w["t1"])
    assert review(TEACHER) == []
    assert call(client_of(BOARD), "get", "gradebooks/").json()  # plain list unchanged
    assert call(client_of(GROUP_LEADER), "get", "gradebooks/?to_review=0").status_code in (200, 400)


# --- concurrency, audit and the whole cycle --------------------------------------------------


def test_a_save_that_waited_behind_a_submit_fails_with_not_draft(
    schools, w, filled, columns, save, call, client_of, app_conn, lock_wait
):
    a, _ = schools
    first = columns(filled)["regular", 1]
    app_conn.execute("BEGIN")
    app_conn.execute("SELECT set_config('app.school_id', %s, true)", [str(a.pk)])
    app_conn.execute(
        "INSERT INTO grades_gradebookstep (school_id, gradebook_id, action, by_id, comment)"
        " VALUES (%s, %s, 'submit', %s, '')",
        [a.pk, filled["id"], w["t1"].pk],
    )
    results = {}

    def put():
        try:
            results["saved"] = save(
                filled["id"],
                [{"column": first, "student": w["an"].pk, "value": 9, "expected": 1}],
            )
        finally:
            connections.close_all()

    thread = threading.Thread(target=put)
    thread.start()
    lock_wait()
    assert thread.is_alive()
    app_conn.execute("COMMIT")
    thread.join(10)
    saved = results["saved"]
    assert (saved.status_code, saved.json()) == (400, {"gradebook": ["not_draft"]})


def test_a_reason_reaches_the_steps_but_not_the_audit_log(
    schools, w, submitted, step, reviewers, detail_of
):
    step(GROUP_LEADER, submitted, "approve")
    step(BOSS, submitted, "reopen", {"reason": "secret reason about a score"})
    with school_scope(schools[0].pk):
        events = AuditEvent.objects.filter(target_table="grades_gradebookstep")
        assert [e.details["action"] for e in events.order_by("id")] == [
            "submit",
            "approve",
            "reopen",
        ]
        assert "secret" not in str(list(AuditEvent.objects.values_list("details", flat=True)))
        assert [e.actor for e in events.order_by("id")] == ["member"] * 3
    assert detail_of(TEACHER, submitted)["steps"][-1]["comment"] == "secret reason about a score"


def test_the_whole_cycle_runs_through_the_api_each_step_by_its_role(
    schools, w, filled, step, reviewers, board_member, detail_of
):
    plan = [
        (TEACHER, "submit", None, "submitted"),
        (GROUP_LEADER, "return", {"comment": "Check column 2"}, "draft"),
        (TEACHER, "submit", None, "submitted"),
        (TEACHER, "withdraw", None, "draft"),
        (TEACHER, "submit", None, "submitted"),
        (GROUP_LEADER, "approve", None, "approved"),
        (BOSS, "reopen", {"reason": "A mark was mistyped"}, "draft"),
        (TEACHER, "submit", None, "submitted"),
        (BOARD, "approve", None, "approved"),
    ]
    for who, action, body, expected in plan:
        response = step(who, filled, action, body)
        assert response.status_code == 200, (action, response.content)
        assert response.json()["status"] == expected, action
    final = detail_of(TEACHER, filled)
    assert [s["action"] for s in final["steps"]] == [p[1] for p in plan]
    assert final["can"] == []
