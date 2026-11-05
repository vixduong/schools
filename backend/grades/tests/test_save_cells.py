"""Saving the grid: no lost and no wrong scores. One transaction with the gradebook locked, a
per-cell `expected` check, all or nothing with a code per failing cell, unchanged cells write
nothing."""

import threading
import types
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection, connections
from django.utils import timezone

from grades.models import GradebookColumn, ScoreEntry
from schools.models import Enrollment
from tenancy.rls import school_scope

TODAY = timezone.localdate()
DAY = timedelta(days=1)
SECOND = timedelta(seconds=1)


@pytest.fixture
def cell(book, columns, w):
    """`cell("an", value, expected, kind="regular", index=1)`: one cell of the MATH grid."""

    def make(student, value=None, expected=None, kind="regular", index=1, **extra):
        return {
            "column": columns(book)[kind, index],
            "student": w[student].pk,
            "value": value,
            "expected": expected,
            **extra,
        }

    return make


def saved(response):
    assert response.status_code == 200, response.content
    return {(c["column"], c["student"]): c["entry"] for c in response.json()["cells"]}


def grid(call, client_of, book, who="t1@example.com"):
    """{(column, student name): (value, entry id)} of the cells that have a current entry."""
    detail = call(client_of(who), "get", f"gradebooks/{book['id']}/").json()
    return {
        (c["column"], s["name"]): (c["value"], c["entry"], c["result"])
        for s in detail["students"]
        for c in s["cells"]
    }


# --- what a save writes ----------------------------------------------------------------------


def test_a_save_appends_an_entry_per_cell_and_returns_each_cells_entry_id(
    w, book, cell, save, stored, columns
):
    response = save(
        book["id"],
        [cell("an", 7.5), cell("bao", 10), cell("eve", 0), cell("an", 5, kind="mid_term")],
    )
    entries = saved(response)
    cols = columns(book)
    assert stored() == [
        (cols["regular", 1], w["an"].pk, Decimal("7.5"), None),
        (cols["regular", 1], w["bao"].pk, Decimal("10"), None),
        (cols["regular", 1], w["eve"].pk, Decimal("0"), None),
        (cols["mid_term", 1], w["an"].pk, Decimal("5"), None),
    ]
    assert len(set(entries.values())) == 4 and None not in entries.values()


def test_unchanged_cells_write_nothing_and_changed_ones_are_appended_in_order(
    w, book, cell, save, stored, call, client_of, columns
):
    first = saved(save(book["id"], [cell("an", 7.5), cell("bao", 6)]))
    an, bao = (
        first[columns(book)["regular", 1], w["an"].pk],
        first[columns(book)["regular", 1], w["bao"].pk],
    )
    assert len(stored()) == 2
    # Same value with the entry the client holds: nothing is written, the ids stay.
    again = saved(save(book["id"], [cell("an", "7.50", an), cell("bao", 6.0, bao)]))
    assert len(stored()) == 2
    assert list(again.values()) == [an, bao]
    # One changed and one not: only the change is appended.
    third = saved(save(book["id"], [cell("an", 8, an), cell("bao", 6, bao)]))
    assert [(e[1], e[2]) for e in stored()] == [
        (w["an"].pk, Decimal("7.5")),
        (w["bao"].pk, Decimal("6")),
        (w["an"].pk, Decimal("8")),
    ]
    new_an = third[columns(book)["regular", 1], w["an"].pk]
    assert new_an > an and third[columns(book)["regular", 1], w["bao"].pk] == bao
    # The grid shows the latest.
    assert grid(call, client_of, book)[columns(book)["regular", 1], "An"][:2] == (8, new_an)


def test_clearing_a_cell_appends_an_empty_entry_and_clearing_an_empty_cell_writes_nothing(
    w, book, cell, save, stored, call, client_of, columns
):
    col = columns(book)["regular", 1]
    # An empty cell cleared: nothing to write, no entry to point at.
    assert saved(save(book["id"], [cell("an", None)])) == {(col, w["an"].pk): None}
    assert stored() == []
    entry = saved(save(book["id"], [cell("an", 7)]))[col, w["an"].pk]
    cleared = saved(save(book["id"], [cell("an", None, entry)]))[col, w["an"].pk]
    assert cleared > entry
    assert stored()[-1][2:] == (None, None)
    assert grid(call, client_of, book)[col, "An"] == (None, cleared, None)
    # Cleared again: unchanged.
    assert saved(save(book["id"], [cell("an", None, cleared)])) == {(col, w["an"].pk): cleared}
    assert len(stored()) == 2
    # And it can be filled again from the clearing.
    assert saved(save(book["id"], [cell("an", 9, cleared)]))[col, w["an"].pk] > cleared


def test_a_comment_only_subject_takes_pass_or_fail(w, open_book, save, stored, columns):
    pe = open_book(subject=w["pe"])
    col = columns(pe)["regular", 1]

    def put(result, expected=None, **extra):
        cell = {
            "column": col,
            "student": w["an"].pk,
            "value": None,
            "result": result,
            "expected": expected,
        }
        return save(pe["id"], [cell | extra])

    entry = saved(put("pass"))[col, w["an"].pk]
    assert saved(put("pass", entry)) == {(col, w["an"].pk): entry}  # unchanged
    assert saved(put("fail", entry))[col, w["an"].pk] > entry
    assert [e[3] for e in stored()] == ["pass", "fail"]
    assert put("pass", None, value=7).status_code == 400  # a value is the wrong form


# --- what is refused -------------------------------------------------------------------------


def errors(response):
    assert response.status_code == 400, response.content
    return {
        (c["column"], c["student"]): (c["code"], c["current"]) for c in response.json()["cells"]
    }


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (10.1, "out_of_range"),
        (-0.1, "out_of_range"),
        (100, "out_of_range"),
        ("11", "out_of_range"),
        (7.55, "too_many_decimals"),
        ("7.55", "too_many_decimals"),
        (0.05, "too_many_decimals"),
        ("abc", "wrong_form"),
        ("", "wrong_form"),
        ("NaN", "wrong_form"),
        ("Infinity", "wrong_form"),
        ("1e9999999", "wrong_form"),  # overflows the decimal context
        ("-1e9999999", "wrong_form"),
        (True, "wrong_form"),
        ([7], "wrong_form"),
    ],
)
def test_a_bad_value_is_an_error_on_its_cell_and_is_never_rounded(
    w, book, cell, save, stored, columns, value, code
):
    good = cell("bao", 8)
    response = save(book["id"], [cell("an", value), good])
    assert errors(response) == {(columns(book)["regular", 1], w["an"].pk): (code, None)}
    assert stored() == []  # the good cell is not saved either


def test_the_edges_of_the_scale_and_trailing_zeros_are_accepted(w, book, cell, save, stored):
    cells = [cell("an", 0), cell("bao", "10.0"), cell("eve", "7.50")]
    saved(save(book["id"], cells))
    assert [e[2] for e in stored()] == [Decimal("0"), Decimal("10"), Decimal("7.5")]


def test_a_result_on_a_scored_subject_both_forms_and_a_student_who_may_not_be_scored_are_refused(
    w, book, cell, save, stored, columns
):
    col = columns(book)["regular", 1]
    response = save(
        book["id"],
        [
            cell("an", None, result="pass"),  # the wrong form for a scored subject
            cell("bao", 7, result="fail"),  # both
            cell("binh", 7),  # in 7B
            cell("dung", 7),  # left 7A three days ago
            {"column": col, "student": 999999, "value": 7, "expected": None},  # nobody
            cell("eve", 7),  # fine
        ],
    )
    assert errors(response) == {
        (col, w["an"].pk): ("wrong_form", None),
        (col, w["bao"].pk): ("wrong_form", None),
        (col, w["binh"].pk): ("not_enrolled", None),
        (col, w["dung"].pk): ("not_enrolled", None),
        (col, 999999): ("not_enrolled", None),
    }
    assert stored() == []


def test_a_malformed_save_is_refused_whole(w, book, cell, save, stored, columns):
    assert save(book["id"], []).status_code == 400
    twice = save(book["id"], [cell("an", 7), cell("an", 8)])  # one cell twice
    assert (twice.status_code, twice.json()) == (400, {"request": ["duplicate_cell"]})
    unknown = {"column": 999999, "student": w["an"].pk, "value": 7, "expected": None}
    nowhere = save(book["id"], [cell("bao", 7), unknown])
    assert (nowhere.status_code, nowhere.json()) == (400, {"request": ["unknown_column"]})
    other = {"column": columns(book)["regular", 1], "student": w["an"].pk, "value": 7}
    assert save(book["id"], [other]).status_code == 400  # `expected` is required
    assert save(book["id"], [cell("an", 7, result="maybe")]).status_code == 400
    assert stored() == []


def test_a_student_who_left_is_kept_in_the_grid_but_cannot_be_scored(
    schools, w, book, cell, save, stored, call, client_of, columns
):
    a, _ = schools
    col = columns(book)["regular", 1]
    # Dung was in the class until three days ago: take him back for a day, score him, then he
    # leaves again; the score stays in the grid.
    with school_scope(a.pk):
        Enrollment.objects.filter(student=w["dung"]).update(valid_to=None, reason_ended=None)
    entry = saved(save(book["id"], [cell("dung", 6)]))[col, w["dung"].pk]
    with school_scope(a.pk):
        Enrollment.objects.filter(student=w["dung"]).update(
            valid_to=TODAY - DAY, reason_ended=Enrollment.ReasonEnded.CLASS_CHANGE
        )
    detail = call(client_of("t1@example.com"), "get", f"gradebooks/{book['id']}/").json()
    dung = next(s for s in detail["students"] if s["name"] == "Dung")
    assert dung["in_class"] is False
    assert [(c["column"], c["value"], c["entry"]) for c in dung["cells"]] == [(col, 6, entry)]
    refused = save(book["id"], [cell("dung", 9, entry)])
    assert errors(refused) == {(col, w["dung"].pk): ("not_enrolled", None)}
    assert len(stored()) == 1


# --- conflicts -------------------------------------------------------------------------------


def test_a_stale_expected_is_a_conflict_reporting_the_current_entry_and_nothing_is_saved(
    w, book, cell, save, stored, columns, client_of
):
    col = columns(book)["regular", 1]
    mine = saved(save(book["id"], [cell("an", 7)]))[col, w["an"].pk]
    # t3 co-teaches the subject and saves the same cell meanwhile.
    theirs = saved(save(book["id"], [cell("an", 9, mine)], client_of("t3@example.com")))[
        col, w["an"].pk
    ]
    # t1 still holds `mine`: their save of An (a different value) and of Bao (fine) conflicts.
    response = save(book["id"], [cell("an", 8, mine), cell("bao", 6)])
    ((_, (code, current)),) = errors(response).items()
    assert code == "conflict"
    assert (current["entry"], current["value"], current["result"]) == (theirs, 9, None)
    assert current["entered_by_name"] == "t3@example.com"
    assert current["entered_at"]
    assert len(stored()) == 2  # Bao's valid cell was not saved with it
    # An empty cell the client thinks is filled, and a filled one it thinks is empty, conflict too.
    assert errors(save(book["id"], [cell("bao", 6, 123456)]))[col, w["bao"].pk][0] == "conflict"
    assert errors(save(book["id"], [cell("an", 9)]))[col, w["an"].pk][0] == "conflict"
    # Even the same value: the client has not seen the other saver's entry.
    assert errors(save(book["id"], [cell("an", 9, mine)]))[col, w["an"].pk][0] == "conflict"
    # Once it holds the current entry, it saves.
    assert saved(save(book["id"], [cell("an", 8, theirs)]))[col, w["an"].pk] > theirs


def test_an_error_and_a_conflict_are_each_reported_on_their_cell(
    w, book, cell, save, stored, columns, client_of
):
    col = columns(book)["regular", 1]
    first = saved(save(book["id"], [cell("an", 7)]))[col, w["an"].pk]
    saved(save(book["id"], [cell("an", 9, first)], client_of("t3@example.com")))
    result = errors(save(book["id"], [cell("an", 5, first), cell("bao", 11), cell("eve", 4)]))
    assert {key: code for key, (code, _) in result.items()} == {
        (col, w["an"].pk): "conflict",
        (col, w["bao"].pk): "out_of_range",
    }
    assert len(stored()) == 2


# --- the order of the history and what the current entry is ----------------------------------


def test_the_history_lists_every_entry_of_a_cell_oldest_first_with_who_entered_it(
    w, book, cell, save, call, client_of, columns
):
    col = columns(book)["regular", 1]
    one = saved(save(book["id"], [cell("an", 7)]))[col, w["an"].pk]
    two = saved(save(book["id"], [cell("an", 8, one)], client_of("t3@example.com")))[
        col, w["an"].pk
    ]
    three = saved(save(book["id"], [cell("an", None, two)]))[col, w["an"].pk]
    saved(save(book["id"], [cell("bao", 5)]))
    history = call(
        client_of("alice@example.com"),
        "get",
        f"gradebooks/{book['id']}/history/?column={col}&student={w['an'].pk}",
    )
    assert history.status_code == 200
    assert [(h["id"], h["value"], h["entered_by_name"]) for h in history.json()] == [
        (one, 7, "t1@example.com"),
        (two, 8, "t3@example.com"),
        (three, None, "t1@example.com"),
    ]
    # A column of another gradebook is not found, and both parameters are required.
    base = f"gradebooks/{book['id']}/history/"
    assert (
        call(client_of("t1@example.com"), "get", f"{base}?column=999999&student=1").status_code
        == 404
    )
    assert call(client_of("t1@example.com"), "get", f"{base}?column={col}").status_code == 400


def test_the_current_entry_is_the_latest_by_time_then_id(
    schools, w, book, columns, call, client_of
):
    a, _ = schools
    col = columns(book)["regular", 1]
    with school_scope(a.pk):
        # Entered earlier, inserted first (the database refuses the other order,
        # `scoreentry_in_order`).
        ScoreEntry.objects.create(
            school=a,
            column_id=col,
            student=w["an"],
            value=Decimal("4"),
            entered_by=w["t1"],
            entered_at=timezone.now() - DAY,
        )
        later = ScoreEntry.objects.create(
            school=a, column_id=col, student=w["an"], value=Decimal("6"), entered_by=w["t1"]
        )
        tie = ScoreEntry.objects.create(
            school=a,
            column_id=col,
            student=w["bao"],
            value=Decimal("1"),
            entered_by=w["t1"],
            entered_at=later.entered_at,
        )
        ScoreEntry.objects.create(
            school=a,
            column_id=col,
            student=w["bao"],
            value=Decimal("2"),
            entered_by=w["t1"],
            entered_at=tie.entered_at,
        )
    cells = grid(call, client_of, book)
    assert cells[col, "An"][:2] == (6, later.pk)
    assert cells[col, "Bao"][0] == 2  # the same time: the later id


def test_a_new_entry_is_never_dated_before_one_already_saved(
    schools, w, book, cell, save, columns, call, client_of
):
    """Whatever the clocks say, the latest entry (by time, then id) is the cell's score: a save
    after an entry dated ahead of this server's clock is still the current one."""
    a, _ = schools
    col = columns(book)["regular", 1]
    with school_scope(a.pk):
        ahead = ScoreEntry.objects.create(
            school=a,
            column_id=col,
            student=w["an"],
            value=Decimal("5"),
            entered_by=w["t3"],
            entered_at=timezone.now() + timedelta(hours=1),
        )
    saved(save(book["id"], [cell("an", 8, ahead.pk)]))
    assert grid(call, client_of, book)[col, "An"][0] == 8


def test_entry_and_release_times_are_the_database_clock_never_the_servers(
    monkeypatch, schools, w, book, cell, save, columns, call, client_of
):
    """Entries and releases are dated by the database clock read after the gradebook lock: a
    server whose own clock is an hour behind changes nothing."""
    a, _ = schools
    col = columns(book)["regular", 1]
    t1 = client_of("t1@example.com")
    with school_scope(a.pk), connection.cursor() as cursor:
        cursor.execute("SELECT clock_timestamp()")
        (before,) = cursor.fetchone()
    monkeypatch.setattr(timezone, "now", lambda: before - 3600 * SECOND)
    saved(save(book["id"], [cell(name, 7) for name in ("an", "bao", "eve")], t1))
    assert call(t1, "post", f"gradebooks/{book['id']}/columns/{col}/release/").status_code == 200
    monkeypatch.undo()
    with school_scope(a.pk):
        stamps = [e.entered_at for e in ScoreEntry.objects.all()]
        released = GradebookColumn.objects.get(pk=col).released_at
    assert all(before <= at <= released for at in stamps)


def test_a_release_is_never_dated_before_an_entry_of_its_gradebook(
    schools, w, book, cell, save, columns, call, client_of
):
    a, _ = schools
    col = columns(book)["regular", 1]
    t1 = client_of("t1@example.com")
    entries = saved(save(book["id"], [cell(name, 7) for name in ("an", "bao", "eve")], t1))
    with school_scope(a.pk):  # another cell, dated ahead of every clock
        ahead = ScoreEntry.objects.create(
            school=a,
            column_id=columns(book)["mid_term", 1],
            student=w["an"],
            value=Decimal("5"),
            entered_by=w["t3"],
            entered_at=timezone.now() + timedelta(hours=1),
        )
    assert call(t1, "post", f"gradebooks/{book['id']}/columns/{col}/release/").status_code == 200
    with school_scope(a.pk):
        assert GradebookColumn.objects.get(pk=col).released_at >= ahead.entered_at
    detail = call(t1, "get", f"gradebooks/{book['id']}/").json()
    assert not any(c["changed_after_release"] for s in detail["students"] for c in s["cells"])
    assert len(entries) == 3


def test_a_save_reads_the_schools_day_in_the_database_not_the_servers(
    monkeypatch, w, book, cell, save, stored
):
    """The roster of a save uses the transaction's `(now() AT TIME ZONE ...)::date`, the value
    the trigger uses; a server whose calendar is off changes nothing."""
    from grades import views

    far = TODAY + 400 * DAY
    monkeypatch.setattr(views, "timezone", types.SimpleNamespace(localdate=lambda: far))
    saved(save(book["id"], [cell("an", 7), cell("eve", 8)]))
    assert len(stored()) == 2


def test_a_change_after_the_release_is_flagged_on_its_cell(
    w, book, cell, save, call, client_of, columns
):
    col = columns(book)["regular", 1]
    t1 = client_of("t1@example.com")
    entries = saved(save(book["id"], [cell(name, 7) for name in ("an", "bao", "eve")]))
    assert call(t1, "post", f"gradebooks/{book['id']}/columns/{col}/release/").status_code == 200
    flags = lambda: {  # noqa: E731
        s["name"]: s["cells"][0]["changed_after_release"]
        for s in call(t1, "get", f"gradebooks/{book['id']}/").json()["students"]
        if s["cells"]
    }
    assert flags() == {"An": False, "Bao": False, "Eve": False}
    saved(save(book["id"], [cell("an", 8, entries[col, w["an"].pk])]))
    assert flags() == {"An": True, "Bao": False, "Eve": False}


# --- who may save ----------------------------------------------------------------------------


def test_only_the_teacher_of_the_pair_saves(
    schools, w, book, cell, save, stored, client_of, board_member, guardian_of_an
):
    for who in (
        "t2@example.com",
        "alice@example.com",
        board_member,
        "admin-a@example.com",
        guardian_of_an,
    ):
        assert save(book["id"], [cell("an", 7)], client_of(who)).status_code == 403, who
    assert stored() == []
    assert save(book["id"], [cell("an", 7)], client_of("t3@example.com")).status_code == 200


# --- concurrency -----------------------------------------------------------------------------


def in_thread(function, results, key):
    def run():
        try:
            results[key] = function()
        finally:
            connections.close_all()

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_a_save_waits_for_a_save_in_flight_and_then_conflicts_with_it(
    schools, w, book, cell, save, stored, columns, app_conn, client_of, lock_wait
):
    """Another transaction holds the gradebook (as a save does) and saves the cell; the waiting
    save then sees that entry, not the cell as it was, and conflicts."""
    a, _ = schools
    col = columns(book)["regular", 1]
    app_conn.execute("BEGIN")
    app_conn.execute("SELECT set_config('app.school_id', %s, true)", [str(a.pk)])
    app_conn.execute("SELECT 1 FROM grades_gradebook WHERE id = %s FOR NO KEY UPDATE", [book["id"]])
    results = {}
    client = client_of("t1@example.com")  # signed in before the thread starts
    thread = in_thread(lambda: save(book["id"], [cell("an", 7)], client), results, "mine")
    lock_wait()
    assert thread.is_alive()  # waiting for the lock
    app_conn.execute(
        "INSERT INTO grades_scoreentry (school_id, column_id, student_id, value, entered_by_id,"
        " entered_at) VALUES (%s, %s, %s, 9, %s, now())",
        [a.pk, col, w["an"].pk, w["t3"].pk],
    )
    app_conn.execute("COMMIT")
    thread.join(10)
    ((code, current),) = errors(results["mine"]).values()
    assert code == "conflict" and current["value"] == 9
    assert [e[2] for e in stored()] == [Decimal("9")]


def test_two_saves_of_the_same_cell_at_once_keep_one_and_conflict_the_other(
    w, book, cell, save, stored, columns, client_of
):
    gate = threading.Barrier(2)
    results = {}

    def go(who, value):
        client = client_of(who)  # signed in before the thread starts

        def run():
            gate.wait()
            return save(book["id"], [cell("an", value)], client)

        return run

    threads = [
        in_thread(go("t1@example.com", 6), results, "t1"),
        in_thread(go("t3@example.com", 9), results, "t3"),
    ]
    for thread in threads:
        thread.join(20)
    codes = sorted(r.status_code for r in results.values())
    assert codes == [200, 400]
    loser = next(r for r in results.values() if r.status_code == 400)
    ((code, current),) = errors(loser).values()
    winner = next(r for r in results.values() if r.status_code == 200)
    assert code == "conflict"
    assert current["entry"] == next(iter(saved(winner).values()))
    assert len(stored()) == 1  # exactly one entry: no lost score, no doubled one
    assert stored()[0][2] == Decimal(str(current["value"]))


def test_a_save_the_database_refuses_midway_writes_nothing(
    monkeypatch, w, book, cell, save, stored, columns
):
    """If a student leaves the class between the save's check and its insert, the trigger refuses
    that entry and the request rolls back every entry it had written. Modelled with a roster that
    still lists Dung, who left three days ago."""
    from grades import views

    real = views.roster

    def stale(gradebook, today):
        students, in_class = real(gradebook, today)
        return students, in_class | {w["dung"].pk}

    monkeypatch.setattr(views, "roster", stale)
    response = save(book["id"], [cell("an", 7), cell("bao", 8), cell("dung", 6)])
    assert (response.status_code, response.json()) == (
        400,
        {"constraint": ["scoreentry_student_in_class"]},
    )
    assert stored() == []
