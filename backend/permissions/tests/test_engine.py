"""Dates, post-transfer reads, queryset helpers, capabilities and query counts of the engine."""

from datetime import timedelta

from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import Membership, RoleAssignment
from permissions.actor import Actor
from permissions.engine import can, capabilities, visible_classes, visible_students
from schools.models import Enrollment, GuardianLink, Student
from schools.tests.factories import make_student

from .conftest import enroll, link, make_member

DAY = timedelta(days=1)
CLASS_READS = ("class_activities.view", "classmates.view_basic", "class_teachers.view")


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


class TestAfterATransferOut:
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
            assert all(can(actor, action, c7a) for action in CLASS_READS), member
            assert not can(actor, "class_records.view", c7a), member
            assert not can(actor, "class_activities.view", world.targets["class_7b"]), member

    def test_the_cell_that_reaches_a_student_in_the_class_does_not_include_them(self, world):
        s3 = world.targets["student_s3"]
        assert not can(world.actors["homeroom_teacher"], "student_profile.view", s3)

    def test_a_student_still_in_the_class_keeps_the_class_records(self, world):
        for role in ("student", "guardian"):
            actor = world.actors[role]
            c7a = world.targets["class_7a"]
            assert all(can(actor, action, c7a) for action in (*CLASS_READS, "class_records.view"))
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
            assert not any(can(actor, action, c7a) for action in CLASS_READS)

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
        # The class left stays readable for the rest of the year, its records stay closed.
        assert can(actor, "class_activities.view", world.targets["class_7a"])
        assert not can(actor, "class_records.view", world.targets["class_7a"])

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
        "group_leader": {s1},
        "homeroom_teacher": {s1},
        "subject_teacher": {s1},
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
        "group_leader": {c7a},
        "homeroom_teacher": {c7a},
        "subject_teacher": {c7a},
        "student": {c7a},
        "guardian": {c7a},
        "operator": set(),
    }
    for role, classes in expected.items():
        assert ids(visible_classes(world.actors[role])) == classes, role


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
