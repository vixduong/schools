"""A Guardian of two children in two classes, a Guardian of a third, a student with a sign-in, a
subject teacher who is also a Guardian, and a day of periods, on top of the gradebook world (`w`
in grades' conftest: School A, HK I, MATH and PE, 7A and 7B, t1 to t3). Everything runs as the app
role."""

# The gradebook fixtures are imported by name, so this conftest offers them too.
# ruff: noqa: F401, F811

from datetime import time, timedelta

import pytest
from django.utils import timezone

from accounts.models import Account
from grades.tests.conftest import (
    _as_app_role,
    book,
    call,
    client_of,
    columns,
    open_book,
    profile_versions,
    save,
    staff,
    w,
)
from schools.models import GuardianLink, Room, Student
from tenancy.rls import school_scope
from testing import A, owner_role
from timetable.models import AttendanceMark, BellPeriod, TimetableEntry

TODAY = timezone.localdate()
DAY = timedelta(days=1)


def link(school, membership, student):
    return GuardianLink.objects.create(
        school=school,
        membership=membership,
        student=student,
        relation=GuardianLink.Relation.MOTHER,
        valid_from=TODAY - 30 * DAY,
    )


@pytest.fixture
def p(schools, w):
    """`g` is the Guardian of An (7A) and Binh (7B); `other` of Bao (7A); `s_an` signs in as An;
    t1 ("Thầy Một", teaches MATH and PE in 7A) is also a Guardian of Binh; t2 ("Cô Hai", MATH in
    7B) is nobody's Guardian. Today's weekday: 7A has MATH by t1 in R1 (morning 1) and PE by t1
    (afternoon 1, no room), 7B has MATH by t2 (morning 1). An was marked late in today's MATH,
    with a note."""
    a = schools[0]
    g, other, s_an = (staff(a, f"{name}@example.com") for name in ("g", "other", "s_an"))
    # A teacher's name that is not their email, so a leaked email shows.
    with owner_role():
        for teacher, name in ((w["t1"], "Thầy Một"), (w["t2"], "Cô Hai")):
            Account.objects.filter(pk=teacher.account_id).update(display_name=name)
    with school_scope(a.pk):
        link(a, g, w["an"])
        link(a, g, w["binh"])
        link(a, other, w["bao"])
        link(a, w["t1"], w["binh"])
        Student.objects.filter(pk=w["an"].pk).update(membership=s_an)
        bell = {
            key: BellPeriod.objects.create(
                school=a,
                school_year=w["year"],
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
        room = Room.objects.create(school=a, name="R1")

        def entry(klass, slot, subject, teacher, room=None):
            return TimetableEntry.objects.create(
                school=a,
                school_year=w["year"],
                school_class=klass,
                weekday=TODAY.isoweekday(),
                bell_period=bell[slot],
                subject=subject,
                teacher=teacher,
                room=room,
                valid_from=TODAY - 14 * DAY,
            )

        math_7a = entry(w["7A"], ("morning", 1), w["math"], w["t1"], room)
        entry(w["7A"], ("afternoon", 1), w["pe"], w["t1"])
        entry(w["7B"], ("morning", 1), w["math"], w["t2"])
        AttendanceMark.objects.create(
            school=a,
            entry=math_7a,
            on=TODAY,
            student=w["an"],
            status=AttendanceMark.Status.LATE,
            note="xe hỏng giữa đường",
            recorded_by=w["t1"],
        )
    return {**w, "g": g, "other": other, "s_an": s_an, "bell": bell, "entry": entry}


@pytest.fixture
def portal():
    """`portal(client, "children/")`: a GET under /api/portal/."""
    return lambda client, path: client.get(f"/api/portal/{path}", HTTP_HOST=A)
