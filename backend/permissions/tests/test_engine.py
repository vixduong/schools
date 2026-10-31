"""Dates, post-transfer reads, queryset helpers, capabilities and query counts of the engine."""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import Membership, RoleAssignment
from permissions.actor import Actor
from permissions.engine import (
    CLASS_READS,
    can,
    capabilities,
    visible_classes,
    visible_pairs,
    visible_students,
)
from permissions.matrix import ACTIONS
from schools.models import Enrollment, GuardianLink, SchoolYear, Student
from schools.tests.factories import make_class, make_student

from .conftest import Assignment, assign, enroll, link, make_member

DAY = timedelta(days=1)
LEFT_CLASS_READS = ("class_activities.view", "classmates.view_basic", "class_teachers.view")


def at(world, member, on):
    return Actor(world.members[member], on)


def ended(role_assignment, valid_to):
    RoleAssignment.objects.filter(pk=role_assignment.pk).update(valid_to=valid_to)


def test_a_role_that_ended_yesterday_grants_nothing_today(world):
    hr = world.members["hr_7a"]
    ended(hr.roleassignment_set.get(), world.today - DAY)
    klass = world.targets["class_7a"]
    assert can(Actor(hr), "report_card.sign_class", klass) is False
    assert can(Actor(hr, world.today - DAY), "report_card.sign_class", klass) is True


def test_a_role_scheduled_to_end_keeps_access_until_its_day(world):
    hr = world.members["hr_7a"]
    ended(hr.roleassignment_set.get(), world.today + 3 * DAY)
    klass = world.targets["class_7a"]
    for offset, expected in ((0, True), (3, True), (4, False)):
        assert can(Actor(hr, world.today + offset * DAY), "report_card.sign_class", klass) is (
            expected
        ), offset


def test_a_role_that_has_not_started_grants_nothing(world):
    hr = world.members["hr_7a"]
    RoleAssignment.objects.filter(membership=hr).update(valid_from=world.today + DAY)
    assert can(Actor(hr), "report_card.sign_class", world.targets["class_7a"]) is False


def test_an_inactive_membership_or_a_pending_confirmation_grants_nothing(world):
    klass = world.targets["class_7a"]
    hr = world.members["hr_7a"]
    RoleAssignment.objects.filter(membership=hr).update(
        status="pending_confirmation", requested_by=world.members["admin"]
    )
    assert can(Actor(hr), "report_card.sign_class", klass) is False
    RoleAssignment.objects.filter(membership=hr).update(status="active", requested_by=None)
    assert can(Actor(hr), "report_card.sign_class", klass) is True
    Membership.objects.filter(pk=hr.pk).update(status="inactive")
    hr.refresh_from_db()
    assert can(Actor(hr), "report_card.sign_class", klass) is False


def test_a_guardian_link_that_ended_yesterday_grants_nothing(world):
    guardian = world.members["guardian_s1"]
    s1 = world.targets["student_s1"]
    GuardianLink.objects.filter(membership=guardian).update(valid_to=world.today - DAY)
    assert can(Actor(guardian), "student_profile.view", s1) is False
    assert can(Actor(guardian, world.today - DAY), "student_profile.view", s1) is True


def test_a_student_with_no_enrollment_in_force_has_no_access(world):
    student = world.members["student_s1"]
    Enrollment.objects.filter(student__membership=student).update(
        valid_to=world.today - DAY, reason_ended="class_change"
    )
    s1 = world.targets["student_s1"]
    assert can(Actor(student), "student_profile.view", s1) is False
    assert can(Actor(student), "class_activities.view", world.targets["class_7a"]) is False


def test_the_student_may_not_read_scores_before_release(world):
    s1 = world.targets["student_s1"]
    student = world.actors["student"]
    assert can(student, "scores.view", s1) is False
    assert can(student, "scores.view", s1, released=True) is True


class TestAfterLeaving:
    """S3 left 7A five days ago; the school year runs on."""

    def test_the_student_and_guardian_keep_two_reads_on_the_student(self, world):
        s3 = world.targets["student_s3"]
        for member in ("student_s3", "guardian_s3"):
            actor = Actor(world.members[member])
            assert can(actor, "student_profile.view", s3)
            assert can(actor, "scores.view", s3, released=True)
            # Nothing else on the student, and nothing that writes.
            for action in ("attendance.view", "conduct.rate", "tests.take", "leave_request.send"):
                assert not can(actor, action, s3, read=True, released=True), (member, action)

    def test_they_keep_three_class_reads_but_never_the_class_records(self, world):
        c7a = world.targets["class_7a"]
        for member in ("student_s3", "guardian_s3"):
            actor = Actor(world.members[member])
            assert all(can(actor, action, c7a) for action in LEFT_CLASS_READS), member
            assert not can(actor, "class_records.view", c7a), member
            assert not can(actor, "class_activities.view", world.targets["class_7b"]), member

    def test_the_sensitive_cell_of_the_homeroom_teacher_does_not_include_them(self, world):
        s3 = world.targets["student_s3"]
        assert can(world.actors["homeroom_teacher"], "student_profile.view", s3)
        assert not can(world.actors["homeroom_teacher"], "student_profile.view_sensitive", s3)

    def test_a_student_still_in_the_class_keeps_the_class_records(self, world):
        for role in ("student", "guardian"):
            actor = world.actors[role]
            c7a = world.targets["class_7a"]
            assert all(
                can(actor, action, c7a) for action in (*LEFT_CLASS_READS, "class_records.view")
            )
            assert not can(actor, "class_records.view", world.targets["class_7b"])

    def test_it_all_closes_after_the_school_year_ends(self, world):
        s3, c7a = world.targets["student_s3"], world.targets["class_7a"]
        last_day, after = world.year.ends_on, world.year.ends_on + DAY
        for member in ("student_s3", "guardian_s3"):
            assert can(at(world, member, last_day), "student_profile.view", s3)
            assert can(at(world, member, last_day), "class_teachers.view", c7a)
            actor = at(world, member, after)
            assert not can(actor, "student_profile.view", s3)
            assert not can(actor, "scores.view", s3, released=True)
            assert not any(can(actor, action, c7a) for action in LEFT_CLASS_READS)

    def test_a_guardian_of_another_student_in_the_class_keeps_the_class_records(self, world):
        """Access is per student: S1's link keeps the class records open for their Guardian
        while S3's own data closes with the year."""
        guardian = world.members["guardian_s3"]
        link(world.school, guardian, world.targets["student_s1"])
        c7a = world.targets["class_7a"]
        assert can(Actor(guardian), "class_records.view", c7a)
        assert can(Actor(guardian), "student_profile.view", world.targets["student_s1"])
        after = Actor(guardian, world.year.ends_on + DAY)
        assert not can(after, "student_profile.view", world.targets["student_s3"])

    def test_a_new_enrollment_in_another_class_keeps_the_student_in(self, world):
        s3, c7b = world.targets["student_s3"], world.targets["class_7b"]
        enroll(world.school, s3, c7b, valid_from=world.today)
        actor = Actor(world.members["student_s3"])
        assert can(actor, "class_records.view", c7b)
        assert can(actor, "attendance.view", s3)
        # Back at the School: every class they have been in is readable, records included.
        assert can(actor, "class_activities.view", world.targets["class_7a"])
        assert can(actor, "class_records.view", world.targets["class_7a"])

    @pytest.mark.parametrize("reason", ["transfer_out", "dropped_out", "graduated"])
    def test_every_leaver_keeps_the_same_reads_until_the_year_ends(self, world, reason):
        s3, c7a = world.targets["student_s3"], world.targets["class_7a"]
        Enrollment.objects.filter(student=s3).update(reason_ended=reason)
        for member in ("student_s3", "guardian_s3"):
            actor = Actor(world.members[member])
            assert can(actor, "student_profile.view", s3)
            assert can(actor, "scores.view", s3, released=True)
            assert all(can(actor, action, c7a) for action in LEFT_CLASS_READS)
            assert not can(actor, "class_records.view", c7a)
            after = at(world, member, world.year.ends_on + DAY)
            assert not can(after, "student_profile.view", s3)

    def test_a_class_change_is_not_a_transfer_out(self, world):
        s2 = world.targets["student_s2"]
        enrollment = Enrollment.objects.get(student=s2)
        Enrollment.objects.filter(pk=enrollment.pk).update(
            valid_to=world.today - 2 * DAY, reason_ended="class_change"
        )
        s2.membership = make_member(world.school, "s2@example.com")
        s2.save()
        assert not can(Actor(s2.membership), "student_profile.view", s2)


def test_a_scheduled_leave_keeps_access_until_its_day(world):
    """A transfer out dated in 10 days: the class records stay until then, the two reads and the
    class reads after, the closed year ends it all."""
    s2 = world.targets["student_s2"]
    member = make_member(world.school, "s2@example.com")
    Student.objects.filter(pk=s2.pk).update(membership=member)
    leave = world.today + 10 * DAY
    Enrollment.objects.filter(student=s2).update(valid_to=leave, reason_ended="transfer_out")
    c7b = world.targets["class_7b"]
    for offset, records, profile, attendance in (
        (0, True, True, True),
        (10, True, True, True),
        (11, False, True, False),
    ):
        actor = Actor(member, world.today + offset * DAY)
        assert can(actor, "class_records.view", c7b) is records, offset
        assert can(actor, "student_profile.view", s2) is profile, offset
        assert can(actor, "attendance.view", s2) is attendance, offset
    assert not can(Actor(member, world.year.ends_on + DAY), "student_profile.view", s2)


def ids(queryset):
    return set(queryset.values_list("pk", flat=True))


def test_visible_students_follow_the_cells(world):
    s1, s2, s3 = (world.targets[f"student_{n}"].pk for n in ("s1", "s2", "s3"))
    expected = {
        "school_admin": set(),
        "principal_board": {s1, s2, s3},
        "group_leader": {s1, s2, s3},
        "homeroom_teacher": {s1, s2, s3},
        "subject_teacher": {s1, s2, s3},
        "student": {s1},
        "guardian": {s1},
        "operator": set(),
    }
    for role, students in expected.items():
        assert ids(visible_students(world.actors[role])) == students, role
    # Post-transfer, S3 sees themself and the Guardian sees S3 for the two reads.
    assert ids(visible_students(Actor(world.members["student_s3"]))) == {s3}
    assert ids(visible_students(Actor(world.members["guardian_s3"]))) == {s3}
    assert ids(visible_students(Actor(world.members["guardian_s3"]), "attendance.view")) == set()


def test_visible_students_only_include_the_requested_school(world):
    assert world.other_school_targets["student_b"].pk not in ids(
        visible_students(world.actors["principal_board"])
    )


def test_visible_classes_follow_the_cells(world):
    c7a, c7b = world.targets["class_7a"].pk, world.targets["class_7b"].pk
    expected = {
        "school_admin": set(),
        "principal_board": {c7a, c7b},
        "group_leader": {c7a, c7b},
        "homeroom_teacher": {c7a, c7b},
        "subject_teacher": {c7a, c7b},
        "student": set(),  # a student's cell is on the student, not on a class
        "guardian": set(),
        "operator": set(),
    }
    for role, classes in expected.items():
        assert ids(visible_classes(world.actors[role])) == classes, role
    # The class reads: staff through their class scopes, the student through their classes.
    reads = {
        "school_admin": set(),
        "principal_board": {c7a, c7b},
        "group_leader": {c7a},
        "homeroom_teacher": {c7a},
        "subject_teacher": {c7a},
        "student": {c7a},
        "guardian": {c7a},
        "operator": set(),
    }
    for role, classes in reads.items():
        for action in CLASS_READS:
            assert ids(visible_classes(world.actors[role], action)) == classes, (role, action)


def test_visible_students_agree_with_can(world):
    students = [world.targets[f"student_{n}"] for n in ("s1", "s2", "s3")]
    for role, actor in world.actors.items():
        seen = ids(visible_students(actor))
        assert seen == {s.pk for s in students if can(actor, "student_profile.view", s)}, role


def test_visible_students_is_one_query(world):
    actor = world.actors["homeroom_teacher"]
    list(visible_students(actor))  # facts load once
    with CaptureQueriesContext(connection) as queries:
        list(visible_students(actor))
    assert len(queries) == 1


def test_capabilities_list_actions_with_scopes(world):
    caps = {c["action"]: c["scopes"] for c in capabilities(world.actors["subject_teacher"])}
    math, c7a = world.targets["pair_math_7a"].subject.pk, world.targets["class_7a"].pk
    assert caps["scores.enter"] == [
        {
            "kind": "teaching_pair",
            "access": "write",
            "once_released": False,
            "pairs": [{"subject": math, "school_class": c7a}],
        }
    ]
    assert "school.configure" not in caps and "scores.view" in caps
    admin = {c["action"]: c["scopes"] for c in capabilities(world.actors["school_admin"])}
    assert admin["school.configure"] == [
        {"kind": "school", "access": "write", "once_released": False}
    ]
    assert admin["audit.read"][0]["access"] == "read"
    student = {c["action"]: c["scopes"] for c in capabilities(world.actors["student"])}
    assert student["scores.view"][0]["once_released"] is True
    assert student["class_records.view"][0]["school_classes"] == [c7a]
    left = {c["action"]: c["scopes"] for c in capabilities(Actor(world.members["student_s3"]))}
    assert "class_records.view" not in left and "class_activities.view" in left
    assert not capabilities(world.actors["nobody"])


def test_a_can_loop_over_50_targets_runs_a_bounded_number_of_queries(world):
    students = make_students(world, 50)

    def queries_for(actor_role, targets):
        actor = Actor(world.actors[actor_role].membership)  # a fresh actor: nothing loaded
        with CaptureQueriesContext(connection) as queries:
            for target in targets:
                can(actor, "student_profile.view", target, read=True)
                can(actor, "scores.view", target, released=True)
        return len(queries)

    for role in ("homeroom_teacher", "subject_teacher", "group_leader", "student", "guardian"):
        few, many = queries_for(role, students[:2]), queries_for(role, students)
        assert many == few <= 8, (role, few, many)


def make_students(world, count):
    created = [make_student(world.school, f"Extra {i}") for i in range(count)]
    for student in created:
        enroll(world.school, student, world.targets["class_7a"], valid_from=world.today - 5 * DAY)
    return created


def test_request_actors_are_built_once_per_request(world):
    class Request:
        membership = world.members["hr_7a"]

    request = Request()
    assert Actor.of(request) is Actor.of(request)
    assert Actor.of(request) is not Actor.of(request, world.today - DAY)


def end_year_for_s1(world):
    """S1's enrollment ends with the school year (what `school-years/{id}/close/` does)."""
    Enrollment.objects.filter(student=world.targets["student_s1"]).update(
        valid_to=world.year.ends_on, reason_ended="year_end"
    )


class TestBetweenSchoolYears:
    """A continuing student (last enrollment ended `year_end`) keeps access through the break."""

    def test_the_student_and_guardian_stay_until_the_next_enrollment_starts(self, world):
        end_year_for_s1(world)
        s1, c7a, c7b = (world.targets[n] for n in ("student_s1", "class_7a", "class_7b"))
        summer = world.year.ends_on + 40 * DAY
        for member in ("student_s1", "guardian_s1"):
            actor = at(world, member, summer)
            assert can(actor, "student_profile.view", s1)
            assert can(actor, "attendance.view", s1)
            assert can(actor, "scores.view", s1, released=True)
            assert all(can(actor, a, c7a) for a in (*LEFT_CLASS_READS, "class_records.view"))
            assert not can(actor, "class_records.view", c7b)

    def test_the_next_enrollment_takes_over_and_keeps_the_old_class_readable(self, world):
        end_year_for_s1(world)
        next_year = SchoolYear.objects.create(
            school=world.school,
            name="next",
            starts_on=world.year.ends_on + 20 * DAY,
            ends_on=world.year.ends_on + 300 * DAY,
        )
        c8a = make_class(world.school, next_year, "8A")
        enroll(world.school, world.targets["student_s1"], c8a, valid_from=next_year.starts_on)
        actor = at(world, "student_s1", next_year.starts_on + 5 * DAY)
        assert can(actor, "class_records.view", c8a)
        assert can(actor, "class_records.view", world.targets["class_7a"])
        assert actor.student_access[world.targets["student_s1"].pk].enrolled_class == c8a.pk

    def test_a_class_change_with_no_next_class_grants_nothing(self, world):
        Enrollment.objects.filter(student=world.targets["student_s1"]).update(
            valid_to=world.today - DAY, reason_ended="class_change"
        )
        assert not can(world.actors["student"], "student_profile.view", world.targets["student_s1"])

    def test_a_leaver_is_not_a_continuing_student(self, world):
        s1 = world.targets["student_s1"]
        Enrollment.objects.filter(student=s1).update(
            valid_to=world.year.ends_on, reason_ended="graduated"
        )
        on = world.year.ends_on + DAY
        assert not can(at(world, "student_s1", on), "student_profile.view", s1)
        assert can(at(world, "student_s1", world.year.ends_on), "student_profile.view", s1)


def test_a_student_at_the_school_reads_every_class_they_have_been_in(world):
    s1, c7a, c7b = (world.targets[n] for n in ("student_s1", "class_7a", "class_7b"))
    Enrollment.objects.filter(student=s1).update(
        valid_to=world.today - 5 * DAY, reason_ended="class_change"
    )
    enroll(world.school, s1, c7b, valid_from=world.today - 4 * DAY)
    for role in ("student", "guardian"):
        actor = Actor(world.members[f"{role}_s1"])
        for klass in (c7a, c7b):
            assert all(can(actor, a, klass) for a in (*LEFT_CLASS_READS, "class_records.view"))
        assert can(actor, "scores.view", s1, released=True)
        # Read only, and only the class-level reads: no per-student data of the classmates.
        assert not can(actor, "tests.take", c7a) and not can(actor, "lessons.view", c7a)
        assert not can(actor, "scores.view", world.targets["student_s2"], released=True)
    assert ids(visible_classes(Actor(world.members["student_s1"]), "class_records.view")) == {
        c7a.pk,
        c7b.pk,
    }


def test_teachers_read_every_class_but_write_only_in_their_own_scope(world):
    s1, s2, s3 = (world.targets[f"student_s{n}"] for n in (1, 2, 3))
    for role in ("group_leader", "homeroom_teacher", "subject_teacher"):
        actor = world.actors[role]
        for student in (s1, s2, s3):
            assert can(actor, "student_profile.view", student), role
            assert can(actor, "scores.view", student), role
        for pair in ("pair_math_7b", "pair_lit_7b"):
            assert can(actor, "scores.view", world.targets[pair]), role
        assert not can(actor, "student_profile.view", world.other_school_targets["student_b"])
    # Writes stay where they were.
    t_math, hr = world.actors["subject_teacher"], world.actors["homeroom_teacher"]
    assert can(t_math, "scores.enter", world.targets["pair_math_7a"])
    assert not can(t_math, "scores.enter", world.targets["pair_math_7b"])
    assert not can(hr, "conduct.rate", world.targets["class_7b"])
    assert can(hr, "conduct.rate", world.targets["class_7a"])


def test_sensitive_details_are_for_the_homeroom_teacher_of_the_class_the_board_and_the_admin(world):
    s1, s2, s3 = (world.targets[f"student_s{n}"] for n in (1, 2, 3))
    view = "student_profile.view_sensitive"
    seen = {
        role: {name for name, s in (("s1", s1), ("s2", s2), ("s3", s3)) if can(a, view, s)}
        for role, a in world.actors.items()
        if role != "nobody"
    }
    assert seen == {
        "school_admin": {"s1", "s2", "s3"},
        "principal_board": {"s1", "s2", "s3"},
        "homeroom_teacher": {"s1"},  # S3 left the class, S2 is in 7B
        "group_leader": set(),
        "subject_teacher": set(),
        "student": set(),
        "guardian": set(),
        "operator": set(),
    }


def test_staff_reach_the_class_reads_through_their_class_scopes(world):
    c7a, c7b = world.targets["class_7a"], world.targets["class_7b"]
    expected = {
        "school_admin": set(),
        "principal_board": {"7a", "7b"},
        "group_leader": {"7a"},
        "homeroom_teacher": {"7a"},
        "subject_teacher": {"7a"},
        "operator": set(),
    }
    for role, classes in expected.items():
        for action in CLASS_READS:
            got = {n for n, c in (("7a", c7a), ("7b", c7b)) if can(world.actors[role], action, c)}
            assert got == classes, (role, action)
    other = world.other_school_targets["class_b"]
    assert not any(can(world.actors["principal_board"], a, other) for a in CLASS_READS)
    # Per-student data never comes through the class-level reads.
    assert not can(
        world.actors["principal_board"], "class_records.view", world.targets["student_s1"]
    )


def agreement_actors(world):
    """Every role's actor, the leavers, and a student and Guardian between school years."""
    end_year_for_s1(world)
    assign(
        world.school,
        make_member(world.school, "math7b@example.com"),
        Assignment.SUBJECT_TEACHER,
        subject=world.targets["pair_math_7a"].subject,
        school_class=world.targets["class_7b"],
    )
    actors = {role: Actor(a.membership) for role, a in world.actors.items()}
    for member in ("student_s3", "guardian_s3"):
        actors[member] = Actor(world.members[member])
    summer = world.year.ends_on + 10 * DAY
    for member in ("student_s1", "guardian_s1"):
        actors[f"{member}_in_summer"] = Actor(world.members[member], summer)
    return actors


def test_visible_students_classes_and_pairs_agree_with_can_for_every_role_and_action(world):
    """The queryset helpers are `can` in SQL form: for every role, action, read and released flag
    they select exactly what `can` accepts."""
    actors = agreement_actors(world)
    students = [world.targets[f"student_s{n}"] for n in (1, 2, 3)]
    classes = [world.targets["class_7a"], world.targets["class_7b"]]
    pairs = {
        key: world.targets[key]
        for key in ("pair_math_7a", "pair_lit_7a", "pair_math_7b", "pair_lit_7b")
    }
    teaching_rows = RoleAssignment.objects.filter(role=Assignment.SUBJECT_TEACHER)
    assert {(r.subject_id, r.school_class_id) for r in teaching_rows} == {
        (p.subject.pk, p.school_class.pk) for p in pairs.values()
    }
    for name, actor in actors.items():
        for action in (*ACTIONS, *CLASS_READS):
            for read in (False, True):
                for released in (False, True):
                    kw = {"read": read, "released": released}
                    where = (name, action, kw)
                    assert ids(visible_students(actor, action, **kw)) == {
                        s.pk for s in students if can(actor, action, s, **kw)
                    }, where
                    assert ids(visible_classes(actor, action, **kw)) == {
                        c.pk for c in classes if can(actor, action, c, **kw)
                    }, where
                    selected = {
                        (r.subject_id, r.school_class_id)
                        for r in teaching_rows.filter(visible_pairs(actor, action, **kw))
                    }
                    assert selected == {
                        (p.subject.pk, p.school_class.pk)
                        for p in pairs.values()
                        if can(actor, action, p, **kw)
                    }, where


def test_a_write_action_lists_only_what_it_may_write_unless_read_is_asked_for(world):
    board = world.actors["principal_board"]
    # Approving leave is a ✔ of the board: all its students; conduct is a 👁.
    assert ids(visible_students(board, "leave_request.approve")) == ids(visible_students(board))
    # The principal board only reads conduct: no student is writable, all are readable.
    assert not visible_students(board, "conduct.rate").exists()
    assert visible_students(board, "conduct.rate", read=True).count() == 3
    assert not visible_classes(board, "conduct.rate").exists()
    assert visible_classes(board, "conduct.rate", read=True).count() == 2
