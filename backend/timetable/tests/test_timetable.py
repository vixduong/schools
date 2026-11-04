"""Timetable rules (clash constraints, triggers) and API, exercised as the app role."""

from datetime import time, timedelta

import pytest
from django.db import IntegrityError, ProgrammingError
from django.utils import timezone

from accounts.models import Membership, RoleAssignment
from audit.models import AuditEvent
from schools.models import GuardianLink, Room, SchoolYear
from schools.tests.factories import make_membership, make_subject
from tenancy.rls import school_scope
from testing import A, make_account, member, sign_in
from timetable.models import BellPeriod, TimetableEntry

pytestmark = pytest.mark.usefixtures("as_app_role")

TODAY = timezone.localdate()
DAY = timedelta(days=1)
TOMORROW = TODAY + DAY  # a replacement starts after today


def teach(
    school, membership, subject, klass, *, valid_from=TODAY - 30 * DAY, valid_to=None, **extra
):
    return RoleAssignment.objects.create(
        school=school,
        membership=membership,
        role=RoleAssignment.Role.SUBJECT_TEACHER,
        school_year=klass.school_year,
        subject=subject,
        school_class=klass,
        valid_from=valid_from,
        valid_to=valid_to,
        **extra,
    )


def teacher(school, email):
    """A Membership (to teach what the test grants) and the email to sign in with."""
    account = make_account(email, display_name=email)
    with school_scope(school.pk):
        return make_membership(school, account)


@pytest.fixture
def world(schools, setup, admin):
    """School A: 7A and 7B; MATH and LIT; rooms R1 and R2; bell periods morning 1 and 2 and
    afternoon 1; t1 teaches MATH in both classes and LIT in 7A, t2 MATH in both."""
    a, _ = schools
    t1, t2 = teacher(a, "t1@example.com"), teacher(a, "t2@example.com")
    with school_scope(a.pk):
        math, lit = make_subject(a, "MATH"), make_subject(a, "LIT")
        teach(a, t1, math, setup["7A"])
        teach(a, t1, math, setup["7B"])
        teach(a, t1, lit, setup["7A"])
        teach(a, t2, math, setup["7A"])
        teach(a, t2, math, setup["7B"])
        periods = {
            key: BellPeriod.objects.create(
                school=a,
                school_year=setup["year"],
                session=key[0],
                number=key[1],
                starts_at=time(*start),
                ends_at=time(*end),
            )
            for key, start, end in (
                (("morning", 1), (7, 0), (7, 45)),
                (("morning", 2), (7, 50), (8, 35)),
                (("afternoon", 1), (13, 30), (14, 15)),
            )
        }
        rooms = [Room.objects.create(school=a, name=name) for name in ("R1", "R2")]
    return {**setup, "t1": t1, "t2": t2, "math": math, "lit": lit, "bell": periods, "rooms": rooms}


def entry(world, school, **fields):
    """A TimetableEntry in 7A on Monday, first period, MATH by t1, open from today."""
    defaults = {
        "school": school,
        "school_year": world["year"],
        "school_class": world["7A"],
        "weekday": 1,
        "bell_period": world["bell"]["morning", 1],
        "subject": world["math"],
        "teacher": world["t1"],
        "valid_from": TODAY,
    }
    return TimetableEntry.objects.create(**{**defaults, **fields})


def refused(constraint, school, make):
    with pytest.raises(IntegrityError, match=constraint), school_scope(school.pk):
        make()


# --- the database rules ---------------------------------------------------------------------


def test_a_class_a_teacher_and_a_room_each_have_one_entry_per_slot_at_a_time(schools, world):
    a, _ = schools
    r1, r2 = world["rooms"]
    with school_scope(a.pk):
        entry(world, a, room=r1)
    # The same slot from the same day: the class, the teacher and the room each clash.
    refused("timetableentry_class_clash", a, lambda: entry(world, a, teacher=world["t2"]))
    refused(
        "timetableentry_teacher_clash",
        a,
        lambda: entry(world, a, school_class=world["7B"], room=r2),
    )
    refused(
        "timetableentry_room_clash",
        a,
        lambda: entry(world, a, school_class=world["7B"], teacher=world["t2"], room=r1),
    )
    # Another weekday or period, no room, or a period that starts after the first ends: no clash.
    with school_scope(a.pk):
        entry(world, a, weekday=2, room=r1)
        entry(world, a, bell_period=world["bell"]["morning", 2], room=r1)
        entry(world, a, school_class=world["7B"], teacher=world["t2"], room=None)
        entry(world, a, school_class=world["7B"], teacher=world["t1"], room=None, weekday=3)
        TimetableEntry.objects.filter(weekday=2).update(valid_to=TODAY + 4 * DAY)
        entry(world, a, weekday=2, valid_from=TODAY + 5 * DAY, room=r1)


def test_a_room_left_empty_never_clashes(schools, world):
    a, _ = schools
    with school_scope(a.pk):
        entry(world, a, room=None)
        entry(world, a, school_class=world["7B"], teacher=world["t2"], room=None)


def test_an_entry_lies_inside_its_school_year(schools, world):
    a, _ = schools
    year = world["year"]
    for bad in (
        {"valid_from": year.starts_on - DAY},
        {"valid_from": year.ends_on + DAY},
        {"valid_from": TODAY, "valid_to": year.ends_on + DAY},
    ):
        refused("timetableentry_inside_school_year", a, lambda bad=bad: entry(world, a, **bad))
    with school_scope(a.pk):
        saved = entry(world, a, valid_from=year.ends_on)  # an open one only has to start inside it
    # Ending an entry past the year is the same refusal (the app role may update valid_to).
    with pytest.raises(IntegrityError, match="timetableentry_inside_school_year"):
        with school_scope(a.pk):
            TimetableEntry.objects.filter(pk=saved.pk).update(valid_to=year.ends_on + DAY)


def test_a_school_year_cannot_shrink_past_its_timetable(admin, schools, world):
    a, _ = schools
    year = world["year"]
    with school_scope(a.pk):
        entry(world, a, valid_from=TODAY + 10 * DAY)
        entry(world, a, weekday=2, valid_to=TODAY + 20 * DAY)

    def move(**dates):
        return admin.patch(
            f"/api/setup/school-years/{year.pk}/",
            {key: str(day) for key, day in dates.items()},
            content_type="application/json",
            HTTP_HOST=A,
        )

    # An end before the open entry starts, and an end before the other entry ends. (The start
    # cannot move past an enrollment's, which begins with the year.)
    for ends_on in (TODAY + 5 * DAY, TODAY + 15 * DAY):
        response = move(ends_on=ends_on)
        assert (response.status_code, response.json()) == (
            400,
            {"constraint": ["school_year_keeps_its_timetable"]},
        )
    assert move(ends_on=TODAY + 30 * DAY).status_code == 200


def test_an_entry_ends_on_or_after_it_starts_and_on_a_weekday(schools, world):
    a, _ = schools
    refused(
        "timetableentry_valid_to_after_valid_from",
        a,
        lambda: entry(world, a, valid_to=TODAY - DAY),
    )
    refused("timetableentry_weekday_in_1_to_7", a, lambda: entry(world, a, weekday=8))
    refused("timetableentry_weekday_in_1_to_7", a, lambda: entry(world, a, weekday=0))


def test_the_teacher_must_hold_the_subject_teacher_role_for_that_class_on_the_first_day(
    schools, world
):
    a, _ = schools
    lit, t2 = world["lit"], world["t2"]
    # t2 teaches no LIT; t1 teaches no LIT in 7B.
    refused("timetableentry_teacher_teaches", a, lambda: entry(world, a, teacher=t2, subject=lit))
    refused(
        "timetableentry_teacher_teaches",
        a,
        lambda: entry(world, a, school_class=world["7B"], subject=lit),
    )
    with school_scope(a.pk):
        assignment = teach(a, t2, lit, world["7A"], valid_from=TODAY + 2 * DAY)
    # The role starts two days from now: an entry from today is refused, one from then is not.
    refused("timetableentry_teacher_teaches", a, lambda: entry(world, a, teacher=t2, subject=lit))
    with school_scope(a.pk):
        entry(world, a, teacher=t2, subject=lit, valid_from=assignment.valid_from)


def test_a_pending_or_ended_role_or_an_inactive_membership_does_not_let_a_teacher_teach(
    schools, world
):
    a, _ = schools
    lit, t2 = world["lit"], world["t2"]
    with school_scope(a.pk):
        pending = teach(
            a,
            t2,
            lit,
            world["7A"],
            status=RoleAssignment.Status.PENDING_CONFIRMATION,
            requested_by=world["t1"],
        )
    refused("timetableentry_teacher_teaches", a, lambda: entry(world, a, teacher=t2, subject=lit))
    with school_scope(a.pk):
        RoleAssignment.objects.filter(pk=pending.pk).update(
            status=RoleAssignment.Status.ACTIVE, requested_by=None
        )
        entry(world, a, teacher=t2, subject=lit)  # active: the entry is accepted
    # The assignment ended before the entry starts.
    with school_scope(a.pk):
        RoleAssignment.objects.filter(pk=pending.pk).update(valid_to=TODAY - 2 * DAY)
    refused(
        "timetableentry_teacher_teaches",
        a,
        lambda: entry(world, a, teacher=t2, subject=lit, weekday=2, valid_from=TODAY - DAY),
    )
    # An inactive Membership teaches nothing, whatever its Role Assignments say.
    with school_scope(a.pk):
        Membership.objects.filter(pk=world["t1"].pk).update(status=Membership.Status.INACTIVE)
    refused("timetableentry_teacher_teaches", a, lambda: entry(world, a, weekday=3))


def test_a_later_end_of_the_role_assignment_leaves_the_entry_alone(schools, world):
    a, _ = schools
    with school_scope(a.pk):
        saved = entry(world, a)
        RoleAssignment.objects.filter(
            membership=world["t1"], subject=world["math"], school_class=world["7A"]
        ).update(valid_to=TODAY)
        saved.valid_to = TODAY + 9 * DAY  # ending an entry does not ask the role again
        saved.save(update_fields=["valid_to"])


def test_a_bell_period_and_a_class_of_one_school_year_serve_one_entry(schools, world):
    a, _ = schools
    year = world["year"]
    with school_scope(a.pk):
        later = SchoolYear.objects.create(
            school=a,
            name="later",
            starts_on=year.ends_on + DAY,
            ends_on=year.ends_on + 300 * DAY,
        )
        elsewhere = BellPeriod.objects.create(
            school=a,
            school_year=later,
            session="morning",
            number=1,
            starts_at=time(7),
            ends_at=time(8),
        )
    refused(
        "timetableentry_bell_period_in_school_year",
        a,
        lambda: entry(world, a, bell_period=elsewhere),
    )
    # The class belongs to the other school year than the entry's.
    refused(
        "timetableentry_class_in_school_year",
        a,
        lambda: entry(
            world, a, school_year=later, bell_period=elsewhere, valid_from=later.starts_on
        ),
    )


def test_a_bell_period_has_unique_numbers_ordered_times_no_overlap_and_a_known_session(
    schools, world
):
    a, _ = schools
    slot = {"school": a, "school_year": world["year"], "starts_at": time(9), "ends_at": time(10)}
    refused(
        "bellperiod_slot_key",
        a,
        lambda: BellPeriod.objects.create(**slot, session="morning", number=1),
    )
    refused(
        "bellperiod_ends_after_start",
        a,
        lambda: BellPeriod.objects.create(
            **{**slot, "ends_at": time(9)}, session="morning", number=3
        ),
    )
    # Breaks are gaps: a period may start when another ends, never inside it.
    refused(
        "bellperiod_no_overlap",
        a,
        lambda: BellPeriod.objects.create(
            **{**slot, "starts_at": time(7, 40), "ends_at": time(8)}, session="morning", number=4
        ),
    )
    with school_scope(a.pk):  # morning 2 ends at 08:35
        BellPeriod.objects.create(
            **{**slot, "starts_at": time(8, 35), "ends_at": time(9)}, session="morning", number=4
        )
    for number in (0, 6):
        refused(
            "bellperiod_number_in_1_to_5",
            a,
            lambda number=number: BellPeriod.objects.create(
                **slot, session="morning", number=number
            ),
        )
    refused(
        "bellperiod_session_is_known",
        a,
        lambda: BellPeriod.objects.create(**slot, session="night", number=1),
    )


def test_the_app_role_cannot_move_an_entry_only_end_it(schools, world):
    a, _ = schools
    with school_scope(a.pk):
        saved = entry(world, a)
    with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
        TimetableEntry.objects.filter(pk=saved.pk).update(valid_from=TODAY + DAY)


# --- the API --------------------------------------------------------------------------------


def url(klass):
    return f"/api/setup/classes/{klass.pk}/timetable/"


def get(client, path, **query):
    return client.get(path, query, HTTP_HOST=A)


def save(client, klass, valid_from, slots):
    return client.post(
        url(klass),
        {"valid_from": str(valid_from), "entries": slots},
        content_type="application/json",
        HTTP_HOST=A,
    )


def slot(world, weekday, period, subject, teacher, room=None):
    return {
        "weekday": weekday,
        "bell_period": world["bell"][period].pk,
        "subject": subject.pk,
        "teacher": teacher.pk,
        "room": room.pk if room else None,
    }


def week_7a(world):
    return [
        slot(world, 1, ("morning", 1), world["math"], world["t1"], world["rooms"][0]),
        slot(world, 1, ("morning", 2), world["lit"], world["t1"], world["rooms"][0]),
        slot(world, 2, ("afternoon", 1), world["math"], world["t1"]),
    ]


def shown(response):
    return sorted((e["weekday"], e["bell_period"]) for e in response.json())


def test_the_admin_saves_a_week_for_two_classes(admin, world):
    first = save(admin, world["7A"], TOMORROW, week_7a(world))
    assert first.status_code == 201, first.json()
    second = save(
        admin,
        world["7B"],
        TOMORROW,
        [slot(world, 1, ("morning", 2), world["math"], world["t2"], world["rooms"][1])],
    )
    assert second.status_code == 201, second.json()
    in_7a = get(admin, url(world["7A"]), on=str(TOMORROW))
    assert in_7a.status_code == 200
    assert [(e["weekday"], e["bell_period"]) for e in in_7a.json()] == [
        (1, world["bell"]["morning", 1].pk),
        (1, world["bell"]["morning", 2].pk),
        (2, world["bell"]["afternoon", 1].pk),
    ]
    assert len(get(admin, url(world["7B"]), on=str(TOMORROW)).json()) == 1


def test_a_new_week_replaces_the_old_from_a_day_and_the_old_one_stays_readable(
    admin, schools, world
):
    a, _ = schools
    save(admin, world["7A"], TOMORROW, week_7a(world))
    start = TODAY + 7 * DAY
    replaced = save(admin, world["7A"], start, week_7a(world)[:1])
    assert replaced.status_code == 201, replaced.json()
    assert len(get(admin, url(world["7A"]), on=str(start - DAY)).json()) == 3
    assert len(get(admin, url(world["7A"]), on=str(start)).json()) == 1
    assert len(get(admin, url(world["7A"]), on=str(TOMORROW)).json()) == 3  # the old week

    # Saving the same day again corrects a draft: the rows not yet in force are deleted and
    # recreated, the in-force ones are not touched twice.
    save(admin, world["7A"], start, week_7a(world)[:2])
    with school_scope(a.pk):
        rows = TimetableEntry.objects.filter(school_class=world["7A"])
        assert rows.count() == 5
        assert rows.filter(valid_to=start - DAY).count() == 3
        assert rows.filter(valid_from=start).count() == 2
    # An earlier day removes the not-yet-started week and ends the in-force one the day before.
    save(admin, world["7A"], TODAY + 3 * DAY, week_7a(world)[:1])
    with school_scope(a.pk):
        rows = TimetableEntry.objects.filter(school_class=world["7A"])
        assert rows.count() == 4
        assert rows.filter(valid_to=TODAY + 2 * DAY).count() == 3
        assert rows.filter(valid_from=TODAY + 3 * DAY, valid_to=None).count() == 1


def test_a_week_starts_after_today_inside_the_class_year(admin, world):
    year = world["year"]
    # Today's periods are never rewritten (attendance refers to them).
    for day in (TODAY - DAY, TODAY):
        assert save(admin, world["7A"], day, []).json() == {"valid_from": ["not_after_today"]}
    assert save(admin, world["7A"], TOMORROW, []).status_code == 201
    assert save(admin, world["7A"], year.ends_on + DAY, []).json() == {
        "valid_from": ["outside_school_year"]
    }
    assert save(admin, world["7A"], "next week", []).status_code == 400


def test_a_clash_is_refused_naming_the_other_entry_and_nothing_is_saved(admin, schools, world):
    a, _ = schools
    r1, r2 = world["rooms"]
    save(
        admin,
        world["7B"],
        TOMORROW,
        [slot(world, 1, ("morning", 1), world["math"], world["t2"], r1)],
    )
    mine = [slot(world, 1, ("morning", 1), world["math"], world["t1"], r2)]
    assert save(admin, world["7A"], TOMORROW, mine).status_code == 201

    # t1 is now in 7A, and the next class asks for t1 at the same time.
    teacher_clash = save(
        admin,
        world["7B"],
        TOMORROW + DAY,
        [slot(world, 1, ("morning", 1), world["math"], world["t1"], r1)],
    )
    assert teacher_clash.status_code == 400
    assert teacher_clash.json() == {
        "constraint": ["timetableentry_teacher_clash"],
        "clash": {
            "weekday": 1,
            "bell_period": world["bell"]["morning", 1].pk,
            "class": world["7A"].pk,
            "subject": world["math"].pk,
            "teacher": world["t1"].pk,
            "room": r2.pk,
        },
    }
    # A room clash names the other class's entry; the refused save left 7B's week as it was.
    room_clash = save(
        admin,
        world["7A"],
        TOMORROW + DAY,
        [slot(world, 1, ("morning", 1), world["math"], world["t1"], r1)],
    )
    assert room_clash.json()["constraint"] == ["timetableentry_room_clash"]
    assert room_clash.json()["clash"]["class"] == world["7B"].pk
    assert room_clash.json()["clash"]["teacher"] == world["t2"].pk
    with school_scope(a.pk):
        assert TimetableEntry.objects.filter(school_class=world["7A"]).count() == 1
        assert TimetableEntry.objects.filter(valid_to__isnull=False).count() == 0


def test_a_class_cannot_have_two_entries_in_one_slot_of_the_week(admin, world):
    twice = [
        slot(world, 1, ("morning", 1), world["math"], world["t1"]),
        slot(world, 1, ("morning", 1), world["lit"], world["t1"]),
    ]
    refused_body = save(admin, world["7A"], TOMORROW, twice).json()
    assert refused_body["constraint"] in (
        ["timetableentry_class_clash"],
        ["timetableentry_teacher_clash"],
    )
    assert refused_body["clash"]["subject"] == world["math"].pk


def test_a_teacher_who_does_not_teach_it_is_refused(admin, world):
    wrong = [slot(world, 1, ("morning", 1), world["lit"], world["t2"])]
    assert save(admin, world["7A"], TOMORROW, wrong).json() == {
        "constraint": ["timetableentry_teacher_teaches"]
    }


def test_a_bell_period_of_another_year_or_school_is_refused(admin, schools, world):
    _, b = schools
    with school_scope(b.pk):
        other = SchoolYear.objects.create(
            school=b, name="b", starts_on=TODAY - DAY, ends_on=TODAY + 99 * DAY
        )
        foreign = BellPeriod.objects.create(
            school=b,
            school_year=other,
            session="morning",
            number=1,
            starts_at=time(7),
            ends_at=time(8),
        )
    body = [
        {**slot(world, 1, ("morning", 1), world["math"], world["t1"]), "bell_period": foreign.pk}
    ]
    assert save(admin, world["7A"], TOMORROW, body).status_code == 400


def test_a_class_that_does_not_exist_is_not_found(admin, world):
    path = f"/api/setup/classes/{world['7A'].pk + 10_000}/timetable/"
    assert get(admin, path).status_code == 404
    post = admin.post(path, {}, content_type="application/json", HTTP_HOST=A)
    assert post.status_code == 404


def test_who_may_read_and_write_a_class_timetable(admin, schools, world):
    a, _ = schools
    save(admin, world["7A"], TOMORROW, week_7a(world)[:1])
    member(a, make_account("board@example.com", display_name="Board"), "principal_board")
    parent = make_account(None, "0912000002", "Guardian")
    with school_scope(a.pk):
        GuardianLink.objects.create(
            school=a,
            membership=make_membership(a, parent),
            student=world["chi"],
            relation="mother",
            valid_from=TODAY - 30 * DAY,
        )
    board, t1, t2 = (sign_in(A, f"{who}@example.com") for who in ("board", "t1", "t2"))
    homeroom = sign_in(A, "alice@example.com")
    # The principal board reads every class and writes none.
    assert get(board, url(world["7A"])).status_code == 200
    assert save(board, world["7A"], TOMORROW, []).status_code == 403
    # A subject teacher reads the classes they teach, and only those; writes none.
    assert get(t1, url(world["7A"])).status_code == 200
    assert save(t1, world["7A"], TOMORROW, []).status_code == 403
    assert get(t2, url(world["7B"])).status_code == 200
    # The homeroom teacher reads their class (alice: 7A) and no other.
    assert get(homeroom, url(world["7A"])).status_code == 200
    assert get(homeroom, url(world["7B"])).status_code == 403
    # A Guardian of a child in another class, and a teacher who teaches neither class, are refused.
    assert get(sign_in(A, "0912000002"), url(world["7A"])).status_code == 403
    teacher(a, "t3@example.com")
    assert get(sign_in(A, "t3@example.com"), url(world["7A"])).status_code == 403


def test_my_periods_are_the_signed_in_teachers_on_the_weekday_in_order(admin, world):
    save(admin, world["7A"], TOMORROW, week_7a(world))
    save(
        admin, world["7B"], TOMORROW, [slot(world, 1, ("afternoon", 1), world["math"], world["t1"])]
    )
    monday = TOMORROW + timedelta(
        days=(8 - TOMORROW.isoweekday()) % 7
    )  # the next Monday (or tomorrow)
    teacher_client = sign_in(A, "t1@example.com")

    mine = get(teacher_client, "/api/setup/timetable/mine/", on=str(monday))
    assert mine.status_code == 200
    assert [
        (
            p["session"],
            p["number"],
            p["starts_at"],
            p["class_name"],
            p["subject_name"],
            p["room_name"],
        )
        for p in mine.json()
    ] == [
        ("morning", 1, "07:00:00", "7A", "MATH", "R1"),
        ("morning", 2, "07:50:00", "7A", "LIT", "R1"),
        ("afternoon", 1, "13:30:00", "7B", "MATH", None),
    ]
    assert (
        get(teacher_client, "/api/setup/timetable/mine/", on=str(monday + DAY)).json()[0]["number"]
        == 1
    )
    assert get(teacher_client, "/api/setup/timetable/mine/", on=str(monday + 2 * DAY)).json() == []
    assert get(teacher_client, "/api/setup/timetable/mine/", on="not a date").status_code == 400
    # Not a teacher: empty, not refused.
    assert get(admin, "/api/setup/timetable/mine/", on=str(monday)).json() == []


def test_an_open_entry_is_not_in_force_after_its_school_year(admin, schools, world):
    a, _ = schools
    year = world["year"]
    after = year.ends_on + DAY
    with school_scope(a.pk):
        entry(world, a, weekday=after.isoweekday(), valid_from=year.ends_on - 30 * DAY)
    teacher_client = sign_in(A, "t1@example.com")
    inside = year.ends_on - 6 * DAY  # the same weekday, the week before
    assert len(get(admin, url(world["7A"]), on=str(inside)).json()) == 1
    assert len(get(teacher_client, "/api/setup/timetable/mine/", on=str(inside)).json()) == 1
    assert get(admin, url(world["7A"]), on=str(after)).json() == []
    assert get(teacher_client, "/api/setup/timetable/mine/", on=str(after)).json() == []


def test_a_replacement_leaves_audit_events_for_the_rows_it_deletes(admin, schools, world):
    a, _ = schools
    start = TOMORROW + 7 * DAY
    save(admin, world["7A"], start, week_7a(world))
    save(admin, world["7A"], start, week_7a(world)[:1])  # deletes the three not yet in force
    with school_scope(a.pk):
        logged = AuditEvent.objects.filter(target_table="timetable_timetableentry")
        assert logged.filter(action="insert").count() == 4
        deleted = logged.filter(action="delete")
        assert deleted.count() == 3
        assert deleted.first().details["valid_from"] == str(start)


def test_an_ended_entry_is_not_among_my_periods(admin, world):
    save(admin, world["7A"], TOMORROW, week_7a(world)[:1])
    save(admin, world["7A"], TODAY + 7 * DAY, [])
    teacher_client = sign_in(A, "t1@example.com")
    day = TODAY + 7 * DAY
    while day.isoweekday() != 1:
        day += DAY
    assert get(teacher_client, "/api/setup/timetable/mine/", on=str(day)).json() == []


def test_bell_periods_are_set_up_by_the_admin_and_read_by_the_board(admin, schools, world):
    a, _ = schools
    path = "/api/setup/bell-periods/"
    made = admin.post(
        path,
        {
            "school_year": world["year"].pk,
            "session": "afternoon",
            "number": 2,
            "starts_at": "14:20",
            "ends_at": "15:05",
        },
        content_type="application/json",
        HTTP_HOST=A,
    )
    assert made.status_code == 201, made.json()
    assert "school" not in made.json()
    # The year, session and number stay; the times change.
    edit = admin.patch(
        f"{path}{made.json()['id']}/",
        {"starts_at": "14:25", "number": 3},
        content_type="application/json",
        HTTP_HOST=A,
    )
    assert edit.json() == {"number": ["immutable"]}
    edit = admin.patch(
        f"{path}{made.json()['id']}/",
        {"starts_at": "14:25"},
        content_type="application/json",
        HTTP_HOST=A,
    )
    assert edit.status_code == 200 and edit.json()["starts_at"] == "14:25:00"
    duplicate = admin.post(
        path,
        {
            "school_year": world["year"].pk,
            "session": "afternoon",
            "number": 2,
            "starts_at": "15:00",
            "ends_at": "15:30",
        },
        content_type="application/json",
        HTTP_HOST=A,
    )
    assert duplicate.status_code == 400
    backwards = admin.post(
        path,
        {
            "school_year": world["year"].pk,
            "session": "morning",
            "number": 4,
            "starts_at": "09:00",
            "ends_at": "08:00",
        },
        content_type="application/json",
        HTTP_HOST=A,
    )
    assert backwards.json() == {"constraint": ["bellperiod_ends_after_start"]}
    assert len(get(admin, path, school_year=world["year"].pk).json()) == 4
    assert get(admin, path, school_year=world["year"].pk + 999).json() == []

    member(a, make_account("board@example.com"), RoleAssignment.Role.PRINCIPAL_BOARD)
    board_client = sign_in(A, "board@example.com")
    assert get(board_client, path).status_code == 200
    assert (
        board_client.post(path, {}, content_type="application/json", HTTP_HOST=A).status_code == 403
    )
    assert get(sign_in(A, "t1@example.com"), path).status_code == 403
