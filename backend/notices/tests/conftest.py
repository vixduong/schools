"""A School with every kind of person a notice can reach (or must not reach): staff, Guardians,
students, and the ones whose Role Assignment, GuardianLink, Enrollment or Membership no longer
counts. Built in one School scope as the owner; the app role comes with `as_app_role`."""

from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import Membership, RoleAssignment
from schools.models import Enrollment, GuardianLink, Student
from schools.tests.factories import make_class, make_group, make_student, make_subject, make_year
from tenancy.rls import school_scope
from testing import make_account

Role = RoleAssignment.Role
TODAY = timezone.localdate()
DAY = timedelta(days=1)

STAFF = ("admin", "board", "gl_math", "gl_lit", "hr_7a", "t_math", "t_lit")
EXTRA_TEACHERS = ("t_pending", "t_ended", "t_inactive")
GUARDIANS = ("g_an", "g_an_ended", "g_binh", "g_chi", "g_dao", "g_eve", "g_inactive")
STUDENT_ACCOUNTS = ("s_an", "s_binh", "s_dao")
NAMES = (*STAFF, *EXTRA_TEACHERS, *GUARDIANS, *STUDENT_ACCOUNTS, "nobody")


def assign(school, membership, role, **scope):
    klass = scope.get("school_class")
    return RoleAssignment.objects.create(
        school=school,
        membership=membership,
        role=role,
        school_year=klass.school_year if klass else None,
        valid_from=TODAY - 30 * DAY,
        **scope,
    )


def link(school, guardian, student, **fields):
    return GuardianLink.objects.create(
        school=school,
        membership=guardian,
        student=student,
        relation=GuardianLink.Relation.MOTHER,
        valid_from=TODAY - 30 * DAY,
        **fields,
    )


def enroll(school, student, klass, **fields):
    return Enrollment.objects.create(
        school=school,
        student=student,
        school_year=klass.school_year,
        school_class=klass,
        valid_from=TODAY - 20 * DAY,
        reason_started=Enrollment.ReasonStarted.NEW_YEAR,
        **fields,
    )


@pytest.fixture
def world(schools):
    """School A (see the names above). `m[name]` is a Membership; `hr_7a` is also a Guardian of
    Chi (a sender is never a recipient of their own notice)."""
    a = schools[0]
    accounts = {
        name: make_account(f"{name}@example.com", display_name=name.replace("_", " ").title())
        for name in NAMES
    }
    with school_scope(a.pk):
        m = {n: Membership.objects.create(school=a, account=accounts[n]) for n in NAMES}
        Membership.objects.filter(pk__in=[m["t_inactive"].pk, m["g_inactive"].pk]).update(
            status=Membership.Status.INACTIVE
        )
        year = make_year(a)
        k7a, k7b = make_class(a, year, "7A"), make_class(a, year, "7B")
        math_group, lit_group = make_group(a, "Math"), make_group(a, "Literature")
        math, lit = make_subject(a, "MATH", math_group), make_subject(a, "LIT", lit_group)
        assign(a, m["admin"], Role.SCHOOL_ADMIN)
        assign(a, m["board"], Role.PRINCIPAL_BOARD)
        assign(a, m["gl_math"], Role.GROUP_LEADER, subject_group=math_group)
        assign(a, m["gl_lit"], Role.GROUP_LEADER, subject_group=lit_group)
        assign(a, m["hr_7a"], Role.HOMEROOM_TEACHER, school_class=k7a)
        assign(a, m["t_math"], Role.SUBJECT_TEACHER, subject=math, school_class=k7a)
        assign(a, m["t_lit"], Role.SUBJECT_TEACHER, subject=lit, school_class=k7b)
        assign(a, m["t_inactive"], Role.SUBJECT_TEACHER, subject=math, school_class=k7a)
        assign(  # a role that ended yesterday
            a, m["t_ended"], Role.SUBJECT_TEACHER, subject=math, school_class=k7a
        )
        RoleAssignment.objects.filter(membership=m["t_ended"]).update(valid_to=TODAY - DAY)
        RoleAssignment.objects.create(  # waits for a second person's confirmation
            school=a,
            membership=m["t_pending"],
            role=Role.SUBJECT_TEACHER,
            subject=math,
            school_class=k7a,
            school_year=year,
            valid_from=TODAY - 30 * DAY,
            status=RoleAssignment.Status.PENDING_CONFIRMATION,
            requested_by=m["admin"],
        )
        students = {n: make_student(a, n.title()) for n in ("an", "binh", "chi", "dao", "eve")}
        enroll(a, students["an"], k7a)
        enroll(a, students["binh"], k7b)
        enroll(a, students["chi"], k7a)
        enroll(  # left 7A yesterday
            a,
            students["dao"],
            k7a,
            valid_to=TODAY - DAY,
            reason_ended=Enrollment.ReasonEnded.TRANSFER_OUT,
        )
        # `eve` has no Enrollment at all (between school years).
        for name, student in (("s_an", "an"), ("s_binh", "binh"), ("s_dao", "dao")):
            Student.objects.filter(pk=students[student].pk).update(membership=m[name])
        link(a, m["g_an"], students["an"])
        link(a, m["g_an_ended"], students["an"], valid_to=TODAY - DAY)
        link(a, m["g_inactive"], students["an"])
        link(a, m["g_binh"], students["binh"])
        link(a, m["g_chi"], students["chi"])
        link(a, m["hr_7a"], students["chi"])
        link(a, m["g_dao"], students["dao"])
        link(a, m["g_eve"], students["eve"])
    return {
        "school": a,
        "m": m,
        "7A": k7a,
        "7B": k7b,
        "math_group": math_group,
        "lit_group": lit_group,
        "students": students,
    }
