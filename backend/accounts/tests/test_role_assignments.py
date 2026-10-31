"""RoleAssignment rules held by the database, exercised as the app role."""

from datetime import date, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import Membership, RoleAssignment
from schools.models import SchoolYear
from schools.tests.factories import make_class, make_group, make_subject, make_year
from tenancy.rls import school_scope

from .conftest import make_account

pytestmark = pytest.mark.usefixtures("as_app_role")

Role = RoleAssignment.Role
CLASS_ROLES = (Role.HOMEROOM_TEACHER, Role.SUBJECT_TEACHER)
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
        school_year=s["year"] if "school_class" in scope else None,
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
        ("school_year", klass_b.school_year_id, Role.HOMEROOM_TEACHER, {"school_class": "klass"}),
        ("school_class", klass_b.pk, Role.HOMEROOM_TEACHER, {}),
        ("subject_group", group_b.pk, Role.GROUP_LEADER, {}),
        ("subject", subject_b.pk, Role.SUBJECT_TEACHER, {"school_class": "klass"}),
    ]
    for field, foreign_id, role, scope in cases:
        # A foreign year or class also breaks "the class's year": either constraint refuses it.
        refusal = f"accounts_roleassignment_{field}_id_same_school"
        if field in ("school_year", "school_class"):
            refusal += "|school_class_in_school_year"
        with pytest.raises(IntegrityError, match=refusal):
            with school_scope(s["school"].pk):
                assignment = RoleAssignment(
                    school=s["school"],
                    membership=s["membership"],
                    role=role,
                    school_year=s["year"] if role in CLASS_ROLES else None,
                    valid_from=D(2025, 9, 1),
                )
                for name, key in scope.items():
                    setattr(assignment, name, s[key])
                setattr(assignment, f"{field}_id", foreign_id)
                assignment.save()


def test_in_force_needs_the_period_and_an_active_membership_not_the_school_year(setup):
    s = setup
    today = timezone.localdate()
    with school_scope(s["school"].pk):
        year = s["year"]  # today lies inside it
        ended = assign(
            s, Role.PRINCIPAL_BOARD, today - timedelta(days=5), today - timedelta(days=1)
        )
        current = assign(s, Role.SCHOOL_ADMIN, today - timedelta(days=5))
        pending = assign(s, Role.HOMEROOM_TEACHER, today, school_class="klass")
        pending.status = RoleAssignment.Status.PENDING_CONFIRMATION
        pending.requested_by = s["membership"]
        pending.save()
        assert set(RoleAssignment.objects.in_force()) == {current}
        assert set(RoleAssignment.objects.in_force(on=today - timedelta(days=2))) == {
            current,
            ended,
        }
        # Far outside every school year, the open-ended role is still in force.
        assert current in RoleAssignment.objects.in_force(on=year.ends_on + timedelta(days=900))
        Membership.objects.update(status=Membership.Status.INACTIVE)
        assert not RoleAssignment.objects.in_force().exists()


def test_a_school_wide_role_stays_in_force_between_two_school_years(setup):
    s = setup
    gap = s["year"].starts_on - timedelta(days=30)  # the "summer" before the only year
    with school_scope(s["school"].pk):
        admin = assign(s, Role.SCHOOL_ADMIN, gap - timedelta(days=100))
        assert not SchoolYear.objects.filter(starts_on__lte=gap, ends_on__gte=gap).exists()
        assert admin in RoleAssignment.objects.in_force(on=gap)


def test_an_open_ended_class_role_does_not_block_the_same_role_in_a_later_year(setup):
    s = setup
    with school_scope(s["school"].pk):
        next_year = SchoolYear.objects.create(
            school=s["school"],
            name="next",
            starts_on=s["year"].ends_on + timedelta(days=1),
            ends_on=s["year"].ends_on + timedelta(days=300),
        )
        assign(s, Role.HOMEROOM_TEACHER, D(2025, 9, 1), school_class="klass")  # valid_to NULL
        next_class = make_class(s["school"], next_year, name="8A")
        later = RoleAssignment.objects.create(
            school=s["school"],
            membership=s["membership"],
            role=Role.HOMEROOM_TEACHER,
            school_year=next_year,
            school_class=next_class,
            valid_from=next_year.starts_on,
        )
        assert later.pk


@pytest.mark.parametrize("role", [Role.HOMEROOM_TEACHER, Role.SUBJECT_TEACHER])
def test_a_class_role_with_a_class_of_another_year_is_refused(setup, role):
    s = setup
    scope = {"school_class": "klass"} | (
        {"subject": "subject"} if role == Role.SUBJECT_TEACHER else {}
    )
    with school_scope(s["school"].pk):
        other_year = SchoolYear.objects.create(
            school=s["school"],
            name="other",
            starts_on=s["year"].ends_on + timedelta(days=1),
            ends_on=s["year"].ends_on + timedelta(days=300),
        )
        s["klass"] = make_class(s["school"], other_year, name="8A")  # a class of the other year
    with pytest.raises(IntegrityError, match="school_class_in_school_year"):
        with school_scope(s["school"].pk):
            assign(s, role, **scope)  # `assign` pairs it with s["year"]


def test_school_year_belongs_to_class_roles_only(setup):
    s = setup
    for role, scope in [
        (Role.SCHOOL_ADMIN, {}),
        (Role.PRINCIPAL_BOARD, {}),
        (Role.GROUP_LEADER, {"subject_group": s["group"]}),
    ]:
        with pytest.raises(IntegrityError, match="roleassignment_scope_matches_role"):
            with school_scope(s["school"].pk):
                RoleAssignment.objects.create(
                    school=s["school"],
                    membership=s["membership"],
                    role=role,
                    school_year=s["year"],
                    valid_from=START,
                    **scope,
                )
    with pytest.raises(IntegrityError, match="roleassignment_scope_matches_role"):
        with school_scope(s["school"].pk):
            RoleAssignment.objects.create(  # a class role without its year
                school=s["school"],
                membership=s["membership"],
                role=Role.HOMEROOM_TEACHER,
                school_class=s["klass"],
                valid_from=START,
            )


@pytest.mark.parametrize("role", list(SCOPES))
def test_no_current_role_may_set_the_grade_scope(setup, role):
    s = setup
    good, _ = SCOPES[role]
    with pytest.raises(IntegrityError, match="roleassignment_scope_matches_role"):
        with school_scope(s["school"].pk):
            assignment = assign(s, role, **good)
            assignment.grade = s["klass"].grade
            assignment.save()


def test_a_self_granted_role_needs_a_third_person_to_confirm(setup):
    s = setup
    other = make_account("c@example.com")
    with school_scope(s["school"].pk):
        confirmer = Membership.objects.create(school=s["school"], account=other)
        row = assign(s, Role.PRINCIPAL_BOARD)
        row.status = RoleAssignment.Status.PENDING_CONFIRMATION
        row.requested_by = s["membership"]
        row.save()
        with pytest.raises(IntegrityError, match="roleassignment_confirmer_is_a_third_person"):
            with transaction.atomic():
                row.confirmed_by = s["membership"]  # the requester confirming themselves
                row.save()
        row.confirmed_by = None
        with pytest.raises(IntegrityError, match="roleassignment_self_grant_needs_confirmation"):
            with transaction.atomic():
                row.status = RoleAssignment.Status.ACTIVE  # active without a confirmer
                row.save()
        row.status = RoleAssignment.Status.ACTIVE
        row.confirmed_by = confirmer
        row.save()
