"""Attendance rules (triggers, constraints, grants, audit) and API, exercised as the app role."""

# `world` is slice 1's fixture, imported by name, so each test taking it "redefines" it.
# ruff: noqa: F811, F401

from datetime import timedelta

import pytest
from django.db import DataError, ProgrammingError

from audit.models import AuditEvent
from schools.models import Enrollment, GuardianLink
from schools.tests.factories import make_membership, make_student
from tenancy.rls import school_scope
from testing import A, enroll, make_account, member, sign_in
from timetable.models import AttendanceMark, TimetableEntry
from timetable.tests.test_timetable import (
    TODAY,
    entry,
    refused,
    teach,
    teacher,
    world,
)

pytestmark = pytest.mark.usefixtures("as_app_role")

DAY = timedelta(days=1)
WEEK = 7 * DAY
Status = AttendanceMark.Status


@pytest.fixture
def class_7a(schools, world):
    """7A: An and Bao since the year began, Dung since three days ago, Eve until eight days ago.
    A period of MATH by t1 (t1 and t2 teach it, t4 will not) held on today's weekday since two
    weeks ago. So today's class is An, Bao, Dung; last week's An, Bao; two weeks ago's An, Bao,
    Eve."""
    a, _ = schools
    with school_scope(a.pk):
        bao, dung, eve = (make_student(a, name) for name in ("Bao", "Dung", "Eve"))
        enroll(a, bao, world["7A"])
        Enrollment.objects.create(
            school=a,
            student=dung,
            school_year=world["year"],
            school_class=world["7A"],
            valid_from=TODAY - 3 * DAY,
            reason_started=Enrollment.ReasonStarted.TRANSFER_IN,
        )
        Enrollment.objects.create(
            school=a,
            student=eve,
            school_year=world["year"],
            school_class=world["7A"],
            valid_from=world["year"].starts_on,
            valid_to=TODAY - 8 * DAY,
            reason_started=Enrollment.ReasonStarted.NEW_YEAR,
            reason_ended=Enrollment.ReasonEnded.CLASS_CHANGE,
        )
        period = entry(world, a, weekday=TODAY.isoweekday(), valid_from=TODAY - 2 * WEEK)
    return {**world, "bao": bao, "dung": dung, "eve": eve, "period": period}


def mark(world, school, student, on, status=Status.PRESENT, **fields):
    return AttendanceMark.objects.create(
        school=school,
        entry=world["period"],
        on=on,
        student=student,
        status=status,
        recorded_by=world["t1"],
        **fields,
    )


def take(world, school, on, **statuses):
    """The whole sheet of the period on `on`, present except the students named in `statuses`."""
    with school_scope(school.pk):
        for key in ("an", "bao", "dung", "eve"):
            if Enrollment.objects.in_force(on).filter(student=world[key], school_class=world["7A"]):
                mark(world, school, world[key], on, statuses.get(key, Status.PRESENT))


def stored(school):
    """Every mark of the School as stored, by student."""
    with school_scope(school.pk):
        return {m["student_id"]: m for m in AttendanceMark.objects.values()}


def audited(school):
    with school_scope(school.pk):
        return list(AuditEvent.objects.filter(target_table="timetable_attendancemark"))


# --- the database rules ---------------------------------------------------------------------


def test_a_mark_needs_the_period_held_on_its_date(schools, class_7a):
    a, _ = schools
    world, year = class_7a, class_7a["year"]
    with school_scope(a.pk):
        mark(world, a, world["an"], TODAY)
        mark(world, a, world["an"], TODAY - WEEK)
    # Another weekday, a week before the entry began, past the year's end the entry is open into.
    after_year = year.ends_on + DAY
    while after_year.isoweekday() != TODAY.isoweekday():
        after_year += DAY
    for bad in (TODAY - DAY, TODAY - 3 * WEEK, after_year):
        refused("attendancemark_fits_entry", a, lambda bad=bad: mark(world, a, world["an"], bad))
    # Once the entry ended, later days are refused and earlier ones stay possible.
    with school_scope(a.pk):
        TimetableEntry.objects.filter(pk=world["period"].pk).update(valid_to=TODAY - 3 * DAY)
        mark(world, a, world["bao"], TODAY - WEEK)
    refused("attendancemark_fits_entry", a, lambda: mark(world, a, world["bao"], TODAY))


def test_a_student_must_be_enrolled_in_the_class_on_the_date(schools, class_7a):
    a, _ = schools
    world = class_7a
    # Binh is in 7B; Dung joined 7A three days ago; Eve left it eight days ago.
    for student, day in (
        (world["binh"], TODAY),
        (world["dung"], TODAY - WEEK),
        (world["eve"], TODAY - WEEK),
    ):
        refused(
            "attendancemark_student_enrolled",
            a,
            lambda student=student, day=day: mark(world, a, student, day),
        )
    with school_scope(a.pk):
        mark(world, a, world["dung"], TODAY)
        mark(world, a, world["eve"], TODAY - 2 * WEEK)


def test_a_student_has_one_mark_per_period_and_day_with_a_known_status_and_a_short_note(
    schools, class_7a
):
    a, _ = schools
    world = class_7a
    with school_scope(a.pk):
        mark(world, a, world["an"], TODAY)
    refused(
        "attendancemark_once_per_student_period_day", a, lambda: mark(world, a, world["an"], TODAY)
    )
    refused(
        "attendancemark_status_is_known",
        a,
        lambda: mark(world, a, world["bao"], TODAY, status="sick"),
    )
    with pytest.raises(DataError), school_scope(a.pk):
        mark(world, a, world["bao"], TODAY, note="x" * 201)


def test_the_app_role_corrects_a_mark_but_never_moves_or_deletes_it(schools, class_7a):
    a, _ = schools
    world = class_7a
    with school_scope(a.pk):
        saved = mark(world, a, world["an"], TODAY)
        AttendanceMark.objects.filter(pk=saved.pk).update(status=Status.LATE, note="traffic")
    for change in (
        lambda marks: marks.update(on=TODAY - WEEK),
        lambda marks: marks.update(student=world["bao"]),
        lambda marks: marks.delete(),
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
            change(AttendanceMark.objects.filter(pk=saved.pk))


def test_only_a_correction_after_the_day_is_audited(schools, class_7a):
    a, _ = schools
    world = class_7a
    with school_scope(a.pk):
        today = mark(world, a, world["an"], TODAY)
        past = mark(world, a, world["an"], TODAY - WEEK)
        AttendanceMark.objects.filter(pk=today.pk).update(status=Status.LATE)
    assert audited(a) == []  # neither taking nor correcting on the day is logged
    with school_scope(a.pk):
        AttendanceMark.objects.filter(pk=past.pk).update(status=Status.ABSENT_EXCUSED)
    (event,) = audited(a)
    assert (event.action, event.target_id) == ("update", past.pk)
    assert event.details["status"] == ["present", "absent_excused"]


# --- the API --------------------------------------------------------------------------------


def sheet_url(world, day=TODAY):
    return f"/api/setup/attendance/{world['period'].pk}/{day}/"


def put(client, world, marks, day=TODAY):
    return client.put(
        sheet_url(world, day), {"marks": marks}, content_type="application/json", HTTP_HOST=A
    )


def sheet(*students, **statuses):
    """A body for `put`: every student present unless `statuses` says otherwise (by name)."""
    return [
        {"student": s.pk, "status": statuses.get(s.full_name, "present"), "note": ""}
        for s in students
    ]


def test_the_sheet_lists_the_class_of_that_day_by_name_and_saves_whole(schools, class_7a):
    a, _ = schools
    world = class_7a
    t1 = sign_in(A, "t1@example.com")
    first = t1.get(sheet_url(world), HTTP_HOST=A)
    assert first.status_code == 200
    body = first.json()
    assert (body["class_name"], body["subject_name"], body["session"], body["number"]) == (
        "7A",
        "MATH",
        "morning",
        1,
    )
    assert body["can_take"] is True
    # Eve left before today, and Dung is in; Binh is in another class.
    assert [(s["name"], s["mark"]) for s in body["students"]] == [
        ("An", None),
        ("Bao", None),
        ("Dung", None),
    ]
    an, bao, dung = world["an"], world["bao"], world["dung"]
    saved = put(t1, world, [*sheet(an, dung), {**sheet(bao)[0], "status": "late", "note": "xe"}])
    assert saved.status_code == 200, saved.json()
    assert [(s["name"], s["mark"]) for s in saved.json()["students"]] == [
        ("An", {"status": "present", "note": ""}),
        ("Bao", {"status": "late", "note": "xe"}),
        ("Dung", {"status": "present", "note": ""}),
    ]
    assert len(stored(a)) == 3
    two_weeks_ago = t1.get(sheet_url(world, TODAY - 2 * WEEK), HTTP_HOST=A).json()
    assert [s["name"] for s in two_weeks_ago["students"]] == ["An", "Bao", "Eve"]


def test_the_sheet_holds_exactly_the_students_enrolled_that_day(schools, class_7a):
    a, _ = schools
    world = class_7a
    t1 = sign_in(A, "t1@example.com")
    an, bao, dung = world["an"], world["bao"], world["dung"]

    def refusal(marks):
        response = put(t1, world, marks)
        assert response.status_code == 400
        assert stored(a) == {}  # nothing of a refused sheet is kept
        return response.json()

    assert refusal(sheet(an, bao)) == {"students": {"missing": [dung.pk], "extra": []}}
    extra = [*sheet(an, bao, dung), *sheet(world["binh"], world["eve"])]
    assert refusal(extra) == {
        "students": {"missing": [], "extra": sorted([world["binh"].pk, world["eve"].pk])}
    }
    # A student listed twice is one too many.
    assert refusal([*sheet(an, bao, dung), *sheet(an)])["students"]["extra"] == [an.pk]
    assert put(t1, world, sheet(an, bao, dung)).status_code == 200


def test_a_future_day_or_a_day_without_the_period_is_refused(schools, class_7a):
    a, _ = schools
    world = class_7a
    t1 = sign_in(A, "t1@example.com")
    members = sheet(world["an"], world["bao"])
    next_week = put(t1, world, members, TODAY + WEEK)
    assert (next_week.status_code, next_week.json()) == (400, {"on": ["not_after_today"]})
    assert put(t1, world, members, TODAY - DAY).status_code == 404  # another weekday
    assert put(t1, world, members, TODAY - 3 * WEEK).status_code == 404  # before the entry began
    assert t1.get(sheet_url(world, "not a date"), HTTP_HOST=A).status_code == 400
    assert t1.get("/api/setup/attendance/0/2000-01-03/", HTTP_HOST=A).status_code == 404
    assert stored(a) == {}


def test_unchanged_marks_are_not_rewritten_and_same_day_edits_are_not_audited(schools, class_7a):
    a, _ = schools
    world = class_7a
    t1, t2 = sign_in(A, "t1@example.com"), sign_in(A, "t2@example.com")
    members = (world["an"], world["bao"], world["dung"])
    assert put(t1, world, sheet(*members)).status_code == 200
    before = stored(a)
    # The same sheet again leaves every row alone; a co-teacher's same-day correction moves one.
    assert put(t1, world, sheet(*members)).status_code == 200
    assert stored(a) == before
    assert put(t2, world, sheet(*members, Bao="absent_unexcused")).status_code == 200
    after = stored(a)
    assert {pk for pk in after if after[pk] != before[pk]} == {world["bao"].pk}
    assert (after[world["bao"].pk]["status"], after[world["bao"].pk]["recorded_by_id"]) == (
        "absent_unexcused",
        world["t2"].pk,
    )
    assert audited(a) == []


def test_a_correction_after_the_day_is_audited_for_the_marks_it_changes(schools, class_7a):
    a, _ = schools
    world = class_7a
    t1 = sign_in(A, "t1@example.com")
    two_weeks_ago = TODAY - 2 * WEEK
    members = (world["an"], world["bao"], world["eve"])
    assert put(t1, world, sheet(*members), two_weeks_ago).status_code == 200
    assert audited(a) == []  # taking a past day's sheet is not a correction
    corrected = put(t1, world, sheet(*members, Eve="absent_excused"), two_weeks_ago)
    assert corrected.status_code == 200
    (event,) = audited(a)  # one row changed, one event
    assert (event.target_id, event.actor_membership_id) == (
        stored(a)[world["eve"].pk]["id"],
        world["t1"].pk,
    )
    assert event.details["status"] == ["present", "absent_excused"]


def test_who_may_take_and_who_may_read_a_period(schools, admin_a, class_7a):
    a, _ = schools
    world = class_7a
    # t2 teaches MATH in 7A too (a co-teacher of the pair); t4 teaches MATH in 7B only.
    t4 = teacher(a, "t4@example.com")
    with school_scope(a.pk):
        teach(a, t4, world["math"], world["7B"])
    teacher(a, "t3@example.com")  # teaches nothing
    member(a, make_account("board@example.com", display_name="Board"), "principal_board")
    parent = make_account(None, "0912000002", "Guardian")
    with school_scope(a.pk):
        GuardianLink.objects.create(
            school=a,
            membership=make_membership(a, parent),
            student=world["an"],
            relation="mother",
            valid_from=TODAY - 30 * DAY,
        )
    body = sheet(world["an"], world["bao"], world["dung"])

    def clients(*identifiers):
        return [sign_in(A, identifier) for identifier in identifiers]

    # The subject teachers of the pair, the co-teacher included, take and read it.
    for client in clients("t1@example.com", "t2@example.com"):
        assert put(client, world, body).status_code == 200
        assert client.get(sheet_url(world), HTTP_HOST=A).json()["can_take"] is True
    # The homeroom teacher of 7A and the board read it, and take nothing.
    for client in clients("alice@example.com", "board@example.com"):
        response = client.get(sheet_url(world), HTTP_HOST=A)
        assert (response.status_code, response.json()["can_take"]) == (200, False)
        assert put(client, world, body).status_code == 403
    # A teacher of another class, one with no class, the School admin and a Guardian: refused.
    for client in clients("t4@example.com", "t3@example.com", "admin-a@example.com", "0912000002"):
        assert client.get(sheet_url(world), HTTP_HOST=A).status_code == 403
        assert put(client, world, body).status_code == 403


def overview_url(klass_id):
    return f"/api/setup/classes/{klass_id}/attendance/"


def overview(client, klass, first, last):
    return client.get(overview_url(klass.pk), {"from": str(first), "to": str(last)}, HTTP_HOST=A)


def test_the_homeroom_overview_lists_every_student_with_their_absences_by_day(schools, class_7a):
    a, _ = schools
    world = class_7a
    take(world, a, TODAY, bao=Status.LATE, dung=Status.ABSENT_EXCUSED)
    take(world, a, TODAY - 2 * WEEK, an=Status.ABSENT_UNEXCUSED, eve=Status.ABSENT_EXCUSED)
    homeroom = sign_in(A, "alice@example.com")
    response = overview(homeroom, world["7A"], TODAY - 2 * WEEK, TODAY)
    assert response.status_code == 200
    assert response.json()["class_name"] == "7A"
    rows = {
        s["name"]: [
            (m["on"], m["session"], m["number"], m["subject_name"], m["status"]) for m in s["marks"]
        ]
        for s in response.json()["students"]
    }
    # Everyone enrolled in the range is listed, Eve (left 8 days ago) and Dung (joined 3) too;
    # a present mark is not an absence.
    assert rows == {
        "An": [(str(TODAY - 2 * WEEK), "morning", 1, "MATH", "absent_unexcused")],
        "Bao": [(str(TODAY), "morning", 1, "MATH", "late")],
        "Dung": [(str(TODAY), "morning", 1, "MATH", "absent_excused")],
        "Eve": [(str(TODAY - 2 * WEEK), "morning", 1, "MATH", "absent_excused")],
    }
    # A range without marks still lists the class as it was then (Eve gone, Dung just in).
    quiet = overview(homeroom, world["7A"], TODAY - 4 * DAY, TODAY - 3 * DAY).json()
    assert [(s["name"], s["marks"]) for s in quiet["students"]] == [
        ("An", []),
        ("Bao", []),
        ("Dung", []),
    ]


def test_who_may_read_a_class_overview(schools, admin_a, class_7a):
    a, _ = schools
    world = class_7a
    member(a, make_account("board@example.com", display_name="Board"), "principal_board")
    parent = make_account(None, "0912000002", "Guardian")
    with school_scope(a.pk):
        GuardianLink.objects.create(
            school=a,
            membership=make_membership(a, parent),
            student=world["an"],
            relation="mother",
            valid_from=TODAY - 30 * DAY,
        )
    seven_a, seven_b = world["7A"], world["7B"]
    homeroom, board = sign_in(A, "alice@example.com"), sign_in(A, "board@example.com")
    assert overview(homeroom, seven_a, TODAY, TODAY).status_code == 200
    assert overview(homeroom, seven_b, TODAY, TODAY).status_code == 403  # not their class
    assert overview(board, seven_a, TODAY, TODAY).status_code == 200
    assert overview(board, seven_b, TODAY, TODAY).status_code == 200
    # A subject teacher sees a period's sheet, not the class; neither do the admin and a Guardian.
    for identifier in ("t1@example.com", "admin-a@example.com", "0912000002"):
        assert overview(sign_in(A, identifier), seven_a, TODAY, TODAY).status_code == 403
    missing = board.get(overview_url(0), {"from": str(TODAY), "to": str(TODAY)}, HTTP_HOST=A)
    assert missing.status_code == 404


def test_an_overview_spans_at_most_31_days(schools, class_7a):
    world = class_7a
    homeroom = sign_in(A, "alice@example.com")
    first = TODAY - 40 * DAY
    assert overview(homeroom, world["7A"], first, first + 30 * DAY).status_code == 200
    too_long = overview(homeroom, world["7A"], first, first + 31 * DAY)
    assert (too_long.status_code, too_long.json()) == (400, {"to": ["range_too_long"]})
    backwards = overview(homeroom, world["7A"], TODAY, TODAY - DAY)
    assert (backwards.status_code, backwards.json()) == (400, {"to": ["before_from"]})
    missing = homeroom.get(overview_url(world["7A"].pk), HTTP_HOST=A)
    assert (missing.status_code, missing.json()) == (400, {"from": ["required"]})


def test_my_periods_carry_their_attendance_counts(schools, class_7a):
    a, _ = schools
    world = class_7a
    t1 = sign_in(A, "t1@example.com")

    def mine(day=TODAY):
        (period,) = t1.get("/api/setup/timetable/mine/", {"on": str(day)}, HTTP_HOST=A).json()
        return period["attendance"]

    assert mine() is None  # not taken
    take(world, a, TODAY, an=Status.ABSENT_EXCUSED, bao=Status.ABSENT_UNEXCUSED, dung=Status.LATE)
    assert mine() == {"absent": 2, "late": 1}
    take(world, a, TODAY - WEEK)
    assert mine(TODAY - WEEK) == {"absent": 0, "late": 0}  # taken, everyone there
    assert mine(TODAY - 2 * WEEK) is None  # another day's marks do not count
