"""The portal API (slice 8): the member's own and linked children, a child's day and their
released scores. A child outside the member's reach is a 404, never a 403."""

from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from schools.models import Enrollment, SchoolYear, Term
from schools.tests.factories import make_student, make_year
from tenancy.rls import school_scope
from timetable.models import AttendanceMark, TimetableEntry

from .conftest import link

TODAY = timezone.localdate()
DAY = timedelta(days=1)
CHILD_ENDPOINTS = ("today/", "scores/")
CONTACT_KEYS = {"email", "phone", "note", "account", "membership"}


def ok(response):
    assert response.status_code == 200, response.content
    return response.json()


def released_7a(p, open_book, save, columns, call, client_of, values=None, **cells_extra):
    """t1 opens MATH 7A HK I, scores An, Bao and Eve in regular 1 and releases it; the book JSON
    and the column id."""
    book = open_book()
    col = columns(book)["regular", 1]
    values = values or {"an": 7, "bao": 8, "eve": 9}
    cells = [
        {"column": col, "student": p[name].pk, "value": value, "expected": None}
        for name, value in values.items()
    ]
    assert save(book["id"], cells).status_code == 200
    release = f"gradebooks/{book['id']}/columns/{col}/release/"
    assert call(client_of("t1@example.com"), "post", release).status_code == 200
    return book, col


def current_entry(call, client_of, book, student):
    detail = call(client_of("t1@example.com"), "get", f"gradebooks/{book['id']}/").json()
    row = next(s for s in detail["students"] if s["id"] == student.pk)
    return row["cells"][0]["entry"]


# --- children/ ---------------------------------------------------------------------------------


def test_children_are_the_members_own_and_linked_students_with_their_class_today(
    p, client_of, portal
):
    assert ok(portal(client_of("g@example.com"), "children/")) == [
        {"id": p["an"].pk, "name": "An", "class_name": "7A", "left": False},
        {"id": p["binh"].pk, "name": "Binh", "class_name": "7B", "left": False},
    ]
    assert ok(portal(client_of("s_an@example.com"), "children/")) == [
        {"id": p["an"].pk, "name": "An", "class_name": "7A", "left": False},
    ]


# --- who reaches a child -----------------------------------------------------------------------


def test_a_guardian_of_another_student_gets_404(p, client_of, portal):
    for path in CHILD_ENDPOINTS:
        assert (
            portal(client_of("other@example.com"), f"children/{p['bao'].pk}/{path}").status_code
            == 200
        )
        assert (
            portal(client_of("g@example.com"), f"children/{p['bao'].pk}/{path}").status_code == 404
        )
    assert portal(client_of("g@example.com"), "children/999999/today/").status_code == 404


def test_another_schools_student_is_a_404(schools, p, client_of, portal):
    with school_scope(schools[1].pk):
        stranger = make_student(schools[1], "Stranger")
    for path in CHILD_ENDPOINTS:
        assert (
            portal(client_of("g@example.com"), f"children/{stranger.pk}/{path}").status_code == 404
        )


def test_a_student_does_not_reach_a_classmate(p, client_of, portal):
    s_an = client_of("s_an@example.com")
    for path in CHILD_ENDPOINTS:
        assert portal(s_an, f"children/{p['an'].pk}/{path}").status_code == 200
        assert portal(s_an, f"children/{p['bao'].pk}/{path}").status_code == 404


def test_a_plain_subject_teacher_has_no_children_and_reaches_none(p, client_of, portal):
    t2 = client_of("t2@example.com")
    assert ok(portal(t2, "children/")) == []
    for path in CHILD_ENDPOINTS:  # Binh is in 7B, which t2 teaches
        assert (
            portal(client_of("g@example.com"), f"children/{p['binh'].pk}/{path}").status_code == 200
        )
        assert portal(t2, f"children/{p['binh'].pk}/{path}").status_code == 404


def test_a_teacher_who_is_also_a_guardian_sees_only_the_linked_child(p, client_of, portal):
    t1 = client_of("t1@example.com")
    assert [c["id"] for c in ok(portal(t1, "children/"))] == [p["binh"].pk]
    for path in CHILD_ENDPOINTS:  # An is in 7A, which t1 teaches
        assert portal(t1, f"children/{p['binh'].pk}/{path}").status_code == 200
        assert portal(t1, f"children/{p['an'].pk}/{path}").status_code == 404


# --- today/ ------------------------------------------------------------------------------------


def test_today_lists_the_classs_periods_with_the_childs_mark(p, client_of, portal):
    g = client_of("g@example.com")
    assert ok(portal(g, f"children/{p['an'].pk}/today/")) == {
        "on": TODAY.isoformat(),
        "periods": [
            {
                "session": "morning",
                "number": 1,
                "starts_at": "07:00:00",
                "ends_at": "07:45:00",
                "subject_name": "MATH",
                "teacher_name": "Thầy Một",
                "room_name": "R1",
                "status": "late",
            },
            {
                "session": "afternoon",
                "number": 1,
                "starts_at": "13:30:00",
                "ends_at": "14:15:00",
                "subject_name": "PE",
                "teacher_name": "Thầy Một",
                "room_name": None,
                "status": None,
            },
        ],
    }
    binh = ok(portal(g, f"children/{p['binh'].pk}/today/"))["periods"]
    assert [(x["subject_name"], x["teacher_name"], x["status"]) for x in binh] == [
        ("MATH", "Cô Hai", None)
    ]


def test_a_day_without_periods_is_an_empty_list_and_a_bad_date_a_400(p, client_of, portal):
    g = client_of("g@example.com")
    tomorrow = TODAY + DAY
    assert ok(portal(g, f"children/{p['an'].pk}/today/?on={tomorrow}")) == {
        "on": tomorrow.isoformat(),
        "periods": [],
    }
    assert portal(g, f"children/{p['an'].pk}/today/?on=nope").status_code == 400


# --- scores/ -----------------------------------------------------------------------------------


def test_an_unreleased_column_is_absent_until_it_is_released(
    p, client_of, portal, open_book, save, columns, call
):
    g = client_of("g@example.com")
    book = open_book()
    reg1, mid = columns(book)["regular", 1], columns(book)["mid_term", 1]
    cells = [
        {"column": reg1, "student": p[name].pk, "value": value, "expected": None}
        for name, value in (("an", 7), ("bao", 8), ("eve", 9))
    ] + [{"column": mid, "student": p["an"].pk, "value": 5, "expected": None}]
    assert save(book["id"], cells).status_code == 200
    scores = f"children/{p['an'].pk}/scores/"
    assert ok(portal(g, scores)) == {
        "term": p["hk1"].pk,
        "term_name": "HK I",
        "gradebooks": [],
    }
    release = f"gradebooks/{book['id']}/columns/{reg1}/release/"
    assert call(client_of("t1@example.com"), "post", release).status_code == 200
    assert ok(portal(g, scores))["gradebooks"] == [
        {
            "subject_name": "MATH",
            "class_name": "7A",
            "columns": [
                {
                    "kind": "regular",
                    "index": 1,
                    "value": 7.0,
                    "result": None,
                    "changed_after_release": False,
                }
            ],
        }
    ]


def test_a_change_after_the_release_shows_at_once_flagged(
    p, client_of, portal, open_book, save, columns, call
):
    book, col = released_7a(p, open_book, save, columns, call, client_of)
    entry = current_entry(call, client_of, book, p["an"])
    assert (
        save(
            book["id"], [{"column": col, "student": p["an"].pk, "value": 6, "expected": entry}]
        ).status_code
        == 200
    )
    (cell,) = ok(portal(client_of("g@example.com"), f"children/{p['an'].pk}/scores/"))[
        "gradebooks"
    ][0]["columns"]
    assert (cell["value"], cell["changed_after_release"]) == (6.0, True)


def test_a_cleared_entry_shows_blank_never_an_older_value(
    p, client_of, portal, open_book, save, columns, call
):
    book, col = released_7a(p, open_book, save, columns, call, client_of)
    entry = current_entry(call, client_of, book, p["an"])
    cleared = {"column": col, "student": p["an"].pk, "value": None, "expected": entry}
    assert save(book["id"], [cleared]).status_code == 200
    (cell,) = ok(portal(client_of("g@example.com"), f"children/{p['an'].pk}/scores/"))[
        "gradebooks"
    ][0]["columns"]
    assert (cell["value"], cell["result"], cell["changed_after_release"]) == (None, None, True)


def test_a_child_who_left_keeps_their_scores_but_has_no_day(
    schools, p, client_of, portal, open_book, save, columns, call
):
    released_7a(p, open_book, save, columns, call, client_of)
    a = schools[0]
    week_ago = TODAY - 7 * DAY
    with school_scope(a.pk):
        # t1 teaches 7A and is Bao's Guardian too; Bao was marked absent in MATH a week ago.
        link(a, p["t1"], p["bao"])
        AttendanceMark.objects.create(
            school=a,
            entry=TimetableEntry.objects.get(school_class=p["7A"], subject=p["math"]),
            on=week_ago,
            student=p["bao"],
            status=AttendanceMark.Status.ABSENT_EXCUSED,
            recorded_by=p["t1"],
        )
        Enrollment.objects.filter(student=p["bao"]).update(
            valid_to=TODAY - DAY, reason_ended=Enrollment.ReasonEnded.TRANSFER_OUT
        )
    other = client_of("other@example.com")
    assert ok(portal(other, "children/")) == [
        {"id": p["bao"].pk, "name": "Bao", "class_name": None, "left": True}
    ]
    (book,) = ok(portal(other, f"children/{p['bao'].pk}/scores/"))["gradebooks"]
    assert [c["value"] for c in book["columns"]] == [8.0]
    assert ok(portal(other, f"children/{p['bao'].pk}/today/"))["periods"] == []
    # A week ago Bao was still in 7A, which held two periods that day: the class's records are
    # closed to him now all the same.
    an_then = ok(portal(client_of("g@example.com"), f"children/{p['an'].pk}/today/?on={week_ago}"))
    assert len(an_then["periods"]) == 2
    assert ok(portal(other, f"children/{p['bao'].pk}/today/?on={week_ago}"))["periods"] == []
    # t1 reads 7A's records as its teacher, but not the mark of a child who left.
    t1_then = ok(
        portal(client_of("t1@example.com"), f"children/{p['bao'].pk}/today/?on={week_ago}")
    )
    assert [x["status"] for x in t1_then["periods"]] == [None, None]


def test_a_class_change_mid_term_shows_the_gradebooks_of_both_classes(
    schools, p, client_of, portal, open_book, save, columns, call
):
    a = schools[0]
    with school_scope(a.pk):  # Dung left 7A three days ago; he joins 7B two days ago
        Enrollment.objects.create(
            school=a,
            student=p["dung"],
            school_year=p["year"],
            school_class=p["7B"],
            valid_from=TODAY - 2 * DAY,
            reason_started=Enrollment.ReasonStarted.CLASS_CHANGE,
        )
        link(a, p["other"], p["dung"])
    released_7a(p, open_book, save, columns, call, client_of)
    t2 = client_of("t2@example.com")
    book_7b = open_book(klass=p["7B"], client=t2)
    col = columns(book_7b)["regular", 1]
    cells = [
        {"column": col, "student": p[name].pk, "value": value, "expected": None}
        for name, value in (("binh", 5), ("dung", 6))
    ]
    assert save(book_7b["id"], cells, t2).status_code == 200
    release = f"gradebooks/{book_7b['id']}/columns/{col}/release/"
    assert call(t2, "post", release).status_code == 200
    dung = ok(portal(client_of("other@example.com"), f"children/{p['dung'].pk}/scores/"))
    assert [(b["class_name"], [c["value"] for c in b["columns"]]) for b in dung["gradebooks"]] == [
        ("7A", [None]),
        ("7B", [6.0]),
    ]
    an = ok(portal(client_of("g@example.com"), f"children/{p['an'].pk}/scores/"))
    assert [b["class_name"] for b in an["gradebooks"]] == ["7A"]


def test_the_term_defaults_to_todays_and_another_years_term_is_a_400(schools, p, client_of, portal):
    a = schools[0]
    with school_scope(a.pk):
        last = SchoolYear.objects.create(
            school=a, name="last", starts_on=TODAY - 400 * DAY, ends_on=TODAY - 31 * DAY
        )
        old = Term.objects.create(
            school=a, school_year=last, name="old", starts_on=last.starts_on, ends_on=last.ends_on
        )
    g = client_of("g@example.com")
    scores = f"children/{p['an'].pk}/scores/"
    assert ok(portal(g, f"{scores}?term={p['hk2'].pk}"))["term_name"] == "HK II"
    with school_scope(schools[1].pk):
        b_year = make_year(schools[1])
        elsewhere = Term.objects.create(
            school=schools[1],
            school_year=b_year,
            name="HK I",
            starts_on=b_year.starts_on,
            ends_on=b_year.ends_on,
        )
    for bad in (old.pk, elsewhere.pk, 999999, "x", 2**63):
        response = portal(g, f"{scores}?term={bad}")
        assert response.status_code == 400, bad
        assert response.json() == {"term": ["unknown"]}


# --- least data and query count ----------------------------------------------------------------


def keys(value):
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in keys(v)}
    return set()


def test_no_response_carries_contact_details_or_the_marks_note(
    p, client_of, portal, open_book, save, columns, call
):
    released_7a(p, open_book, save, columns, call, client_of)
    g = client_of("g@example.com")
    for path in ("children/", *(f"children/{p['an'].pk}/{x}" for x in CHILD_ENDPOINTS)):
        response = portal(g, path)
        assert response.status_code == 200, path
        assert not keys(response.json()) & CONTACT_KEYS, path
        content = response.content.decode()
        assert "xe hỏng" not in content and "@example.com" not in content, path


def count(client, portal, path):
    with CaptureQueriesContext(connection) as queries:
        assert portal(client, path).status_code == 200
    return len(queries)


def test_the_query_count_does_not_grow_with_children_periods_or_gradebooks(
    schools, p, client_of, portal, open_book, save, columns, call
):
    a = schools[0]
    g = client_of("g@example.com")
    today, scores = f"children/{p['an'].pk}/today/", f"children/{p['an'].pk}/scores/"
    released_7a(p, open_book, save, columns, call, client_of)
    before = [count(g, portal, path) for path in ("children/", today, scores)]
    with school_scope(a.pk):
        link(a, p["g"], p["bao"])  # a third child
        p["entry"](p["7A"], ("morning", 2), p["math"], p["t1"])  # a third period
    pe = open_book(subject=p["pe"])  # a second released gradebook
    col = columns(pe)["regular", 1]
    cells = [
        {"column": col, "student": p[name].pk, "value": None, "result": "pass", "expected": None}
        for name in ("an", "bao", "eve")
    ]
    assert save(pe["id"], cells).status_code == 200
    assert (
        call(
            client_of("t1@example.com"), "post", f"gradebooks/{pe['id']}/columns/{col}/release/"
        ).status_code
        == 200
    )
    assert len(ok(portal(g, "children/"))) == 3
    assert len(ok(portal(g, today))["periods"]) == 3
    assert len(ok(portal(g, scores))["gradebooks"]) == 2
    assert [count(g, portal, path) for path in ("children/", today, scores)] == before
