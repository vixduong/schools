"""RoleAssignment rules held by the database, exercised as the app role."""

from datetime import date, timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import Membership, RoleAssignment
from schools.models import SchoolYear
from schools.tests.factories import make_class, make_group, make_subject, make_year
from tenancy.rls import school_scope

from .conftest import make_account

pytestmark = pytest.mark.usefixtures("as_app_role")

Role = RoleAssignment.Role
D = date
START = D(2025, 9, 1)


@pytest.fixture
def setup(schools):
    """A Membership in School A with a year, a class, a subject and a group to scope to."""
    a, _ = schools
    account = make_account("t@example.com")
    with school_scope(a.pk):
        year = make_year(a)
        group = make_group(a)
        return {
            "school": a,
            "membership": Membership.objects.create(school=a, account=account),
            "year": year,
            "group": group,
            "klass": make_class(a, year),
            "subject": make_subject(a, group=group),
        }


def assign(s, role, valid_from=START, valid_to=None, **scope):
    return RoleAssignment.objects.create(
        school=s["school"],
        membership=s["membership"],
        role=role,
        school_year=s["year"],
        valid_from=valid_from,
        valid_to=valid_to,
        **{k: s[v] for k, v in scope.items()},
    )


# role -> (scope that is accepted, scopes that are refused)
SCOPES = {
    Role.SCHOOL_ADMIN: ({}, [{"school_class": "klass"}, {"subject_group": "group"}]),
    Role.PRINCIPAL_BOARD: ({}, [{"subject": "subject"}]),
    Role.GROUP_LEADER: (
        {"subject_group": "group"},
        [{}, {"school_class": "klass"}, {"subject_group": "group", "school_class": "klass"}],
    ),
    Role.HOMEROOM_TEACHER: (
        {"school_class": "klass"},
        [{}, {"subject_group": "group"}, {"school_class": "klass", "subject": "subject"}],
    ),
    Role.SUBJECT_TEACHER: (
        {"subject": "subject", "school_class": "klass"},
        [
            {},
            {"subject": "subject"},
            {"school_class": "klass"},
            {"subject": "subject", "school_class": "klass", "subject_group": "group"},
        ],
    ),
}


@pytest.mark.parametrize("role", list(SCOPES))
def test_each_role_accepts_only_its_scope(setup, role):
    good, bad = SCOPES[role]
    for refused in bad:
        with pytest.raises(IntegrityError, match="roleassignment_scope_matches_role"):
            with school_scope(setup["school"].pk):
                assign(setup, role, **refused)
    with school_scope(setup["school"].pk):
        assign(setup, role, **good)


@pytest.mark.parametrize("role", [Role.STUDENT, Role.GUARDIAN])
@pytest.mark.parametrize("scope", [{}, {"school_class": "klass"}])
def test_student_and_guardian_cannot_be_created_before_the_student_scope_exists(setup, role, scope):
    with pytest.raises(IntegrityError, match="roleassignment_scope_matches_role"):
        with school_scope(setup["school"].pk):
            assign(setup, role, **scope)


def test_period_must_not_end_before_it_starts(setup):
    with pytest.raises(IntegrityError, match="roleassignment_valid_to_after_valid_from"):
        with school_scope(setup["school"].pk):
            assign(setup, Role.SCHOOL_ADMIN, D(2025, 9, 2), D(2025, 9, 1))


def test_overlapping_periods_of_one_role_and_scope_are_refused(setup):
    with school_scope(setup["school"].pk):
        assign(setup, Role.HOMEROOM_TEACHER, D(2025, 9, 1), D(2025, 12, 31), school_class="klass")
    for start, end in [
        (D(2025, 12, 31), None),
        (D(2025, 10, 1), D(2025, 10, 2)),
        (D(2025, 1, 1), None),
    ]:
        with pytest.raises(IntegrityError, match="roleassignment_no_overlapping_periods"):
            with school_scope(setup["school"].pk):
                assign(setup, Role.HOMEROOM_TEACHER, start, end, school_class="klass")


def test_overlap_is_refused_for_school_wide_roles_with_no_scope(setup):
    with school_scope(setup["school"].pk):
        assign(setup, Role.SCHOOL_ADMIN)
    with pytest.raises(IntegrityError, match="roleassignment_no_overlapping_periods"):
        with school_scope(setup["school"].pk):
            assign(setup, Role.SCHOOL_ADMIN, D(2026, 1, 1))


def test_overlap_is_fine_for_another_scope_another_role_or_another_membership(setup):
    s = setup
    other_account = make_account("o@example.com")  # not inside a School scope: it swaps roles
    with school_scope(s["school"].pk):
        other_class = make_class(s["school"], s["year"], name="7B")
        other = Membership.objects.create(school=s["school"], account=other_account)
        assign(s, Role.HOMEROOM_TEACHER, school_class="klass")
        s["klass"] = other_class
        assign(s, Role.HOMEROOM_TEACHER, school_class="klass")  # another class
        assign(s, Role.SUBJECT_TEACHER, subject="subject", school_class="klass")  # another role
        s["membership"] = other
        assign(s, Role.HOMEROOM_TEACHER, school_class="klass")  # another person


def test_a_role_can_end_and_resume_later_in_the_same_year(setup):
    s = setup
    with school_scope(s["school"].pk):
        first = assign(s, Role.HOMEROOM_TEACHER, D(2025, 9, 1), school_class="klass")
        first.valid_to = D(2025, 11, 30)  # ended ...
        first.save()
        assign(s, Role.HOMEROOM_TEACHER, D(2026, 1, 5), school_class="klass")  # ... and resumed
        assert RoleAssignment.objects.filter(role=Role.HOMEROOM_TEACHER).count() == 2
    with pytest.raises(IntegrityError, match="roleassignment_no_overlapping_periods"):
        with school_scope(s["school"].pk):
            first.valid_to = D(2026, 2, 1)  # stretching it back over the resumed period
            first.save()


def test_cross_school_scope_references_are_refused(schools, setup):
    _, b = schools
    with school_scope(b.pk):
        klass_b = make_class(b)
        group_b = make_group(b)
        subject_b = make_subject(b)
    s = setup
    cases = [
        ("school_year", klass_b.school_year_id, Role.SCHOOL_ADMIN, {}),
        ("school_class", klass_b.pk, Role.HOMEROOM_TEACHER, {}),
        ("subject_group", group_b.pk, Role.GROUP_LEADER, {}),
        ("subject", subject_b.pk, Role.SUBJECT_TEACHER, {"school_class": "klass"}),
    ]
    for field, foreign_id, role, scope in cases:
        with pytest.raises(IntegrityError, match=f"accounts_roleassignment_{field}_id_same_school"):
            with school_scope(s["school"].pk):
                assignment = RoleAssignment(
                    school=s["school"],
                    membership=s["membership"],
                    role=role,
                    school_year=s["year"],
                    valid_from=D(2025, 9, 1),
                )
                for name, key in scope.items():
                    setattr(assignment, name, s[key])
                setattr(assignment, f"{field}_id", foreign_id)
                assignment.save()


def test_in_force_needs_the_period_and_the_school_year(setup):
    s = setup
    today = timezone.localdate()
    with school_scope(s["school"].pk):
        year = s["year"]  # today lies inside it
        later = SchoolYear.objects.create(
            school=s["school"],
            name="later",
            starts_on=year.ends_on + timedelta(days=1),
            ends_on=year.ends_on + timedelta(days=300),
        )
        s["year"] = later
        outside_year = assign(s, Role.SCHOOL_ADMIN, later.starts_on)
        s["year"] = year
        ended = assign(
            s, Role.PRINCIPAL_BOARD, today - timedelta(days=5), today - timedelta(days=1)
        )
        current = assign(s, Role.SCHOOL_ADMIN, today - timedelta(days=5), year.ends_on)
        assert set(RoleAssignment.objects.in_force()) == {current}
        assert set(RoleAssignment.objects.in_force(on=today - timedelta(days=2))) == {
            current,
            ended,
        }
        assert set(RoleAssignment.objects.in_force(on=later.starts_on)) == {outside_year}
        assert ended not in RoleAssignment.objects.in_force()
