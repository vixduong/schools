"""A School with one member per role, a transferred-out student and their Guardian, a second
class, a second subject group, and a second School. Built as the owner inside the test's own
transaction (`db`), scoped to a School with `set_school` like the middleware does."""

from dataclasses import dataclass
from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import Account, Membership, RoleAssignment
from permissions.actor import Actor, TeachingPair
from schools.models import Enrollment, GuardianLink
from schools.tests.factories import make_class, make_group, make_student, make_subject, make_year
from tenancy.models import School
from tenancy.rls import set_school

Assignment = RoleAssignment.Role


def make_member(school, email, display_name=None):
    account = Account.objects.create(email=email, display_name=display_name or email)
    return Membership.objects.create(school=school, account=account)


def assign(school, membership, role, *, valid_from=None, valid_to=None, **scope):
    klass = scope.get("school_class")
    return RoleAssignment.objects.create(
        school=school,
        membership=membership,
        role=role,
        school_year=klass.school_year if klass else None,
        valid_from=valid_from or timezone.localdate() - timedelta(days=30),
        valid_to=valid_to,
        **scope,
    )


def enroll(school, student, klass, *, valid_from, valid_to=None, reason_ended=None):
    return Enrollment.objects.create(
        school=school,
        student=student,
        school_year=klass.school_year,
        school_class=klass,
        valid_from=valid_from,
        valid_to=valid_to,
        reason_started=Enrollment.ReasonStarted.NEW_YEAR,
        reason_ended=reason_ended,
    )


def link(school, guardian, student, **fields):
    return GuardianLink.objects.create(
        school=school,
        membership=guardian,
        student=student,
        relation=GuardianLink.Relation.MOTHER,
        valid_from=fields.pop("valid_from", timezone.localdate() - timedelta(days=30)),
        **fields,
    )


@dataclass
class World:
    school: School
    other_school: School
    today: object
    members: dict  # name -> Membership
    actors: dict  # matrix role value (and "nobody") -> Actor
    targets: dict  # name -> target
    other_school_targets: dict
    year: object


@pytest.fixture
def world(db):
    today = timezone.localdate()
    a = School.objects.create(name="A", subdomain="a")
    b = School.objects.create(name="B", subdomain="b")

    set_school(b.pk)
    year_b = make_year(b)
    class_b = make_class(b, year_b)
    subject_b = make_subject(b, group=make_group(b))
    student_b = make_student(b)
    enroll(b, student_b, class_b, valid_from=today - timedelta(days=20))
    other = {
        "school_b": b,
        "group_b": subject_b.subject_group,
        "class_b": class_b,
        "pair_b": TeachingPair(subject_b, class_b),
        "student_b": student_b,
    }

    set_school(a.pk)
    year = make_year(a)
    c7a, c7b = make_class(a, year, "7A"), make_class(a, year, "7B")
    math_group, lit_group = make_group(a, "Math"), make_group(a, "Literature")
    math, lit = make_subject(a, "MATH", math_group), make_subject(a, "LIT", lit_group)
    other["pair_mixed"] = TeachingPair(math, class_b)

    members = {
        name: make_member(a, f"{name}@example.com")
        for name in (
            "admin",
            "board",
            "gl_math",
            "hr_7a",
            "t_math",
            "t_lit",
            "student_s1",
            "guardian_s1",
            "student_s3",
            "guardian_s3",
            "nobody",
        )
    }
    assign(a, members["admin"], Assignment.SCHOOL_ADMIN)
    assign(
        a,
        members["board"],
        Assignment.PRINCIPAL_BOARD,
        title=RoleAssignment.Title.PRINCIPAL,
        can_reopen_gradebooks=True,
    )
    assign(a, members["gl_math"], Assignment.GROUP_LEADER, subject_group=math_group)
    assign(a, members["hr_7a"], Assignment.HOMEROOM_TEACHER, school_class=c7a)
    assign(a, members["t_math"], Assignment.SUBJECT_TEACHER, subject=math, school_class=c7a)
    assign(a, members["t_lit"], Assignment.SUBJECT_TEACHER, subject=lit, school_class=c7a)
    assign(a, members["t_lit"], Assignment.SUBJECT_TEACHER, subject=lit, school_class=c7b)

    s1, s2, s3 = (make_student(a, name) for name in ("S1", "S2", "S3"))
    enroll(a, s1, c7a, valid_from=today - timedelta(days=20))
    enroll(a, s2, c7b, valid_from=today - timedelta(days=20))
    enroll(  # transferred out five days ago from 7A
        a,
        s3,
        c7a,
        valid_from=today - timedelta(days=25),
        valid_to=today - timedelta(days=5),
        reason_ended=Enrollment.ReasonEnded.TRANSFER_OUT,
    )
    for student, member in ((s1, "student_s1"), (s3, "student_s3")):
        student.membership = members[member]
        student.save()
    link(a, members["guardian_s1"], s1)
    link(a, members["guardian_s3"], s3)

    roles = {
        "school_admin": "admin",
        "principal_board": "board",
        "group_leader": "gl_math",
        "homeroom_teacher": "hr_7a",
        "subject_teacher": "t_math",
        "student": "student_s1",
        "guardian": "guardian_s1",
        "operator": "nobody",  # the operator holds nothing inside a School
        "nobody": "nobody",
    }
    return World(
        school=a,
        other_school=b,
        today=today,
        members=members,
        actors={role: Actor(members[member]) for role, member in roles.items()},
        targets={
            "school_a": a,
            "group_math": math_group,
            "group_lit": lit_group,
            "class_7a": c7a,
            "class_7b": c7b,
            "pair_math_7a": TeachingPair(math, c7a),
            "pair_lit_7a": TeachingPair(lit, c7a),
            "pair_math_7b": TeachingPair(math, c7b),
            "pair_lit_7b": TeachingPair(lit, c7b),
            "student_s1": s1,
            "student_s2": s2,
            "student_s3": s3,
        },
        other_school_targets=other,
        year=year,
    )
