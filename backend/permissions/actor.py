"""The facts about one member on one date, loaded lazily and once per Actor (and an Actor is
cached on the request), so `can()` in a loop costs a bounded number of queries."""

from dataclasses import dataclass
from functools import cached_property

from django.db.models import Q
from django.utils import timezone

from accounts.models import Membership, RoleAssignment
from schools.models import Enrollment, GuardianLink, SchoolClass, Student, Subject

from .matrix import Duty, Role

Assignment = RoleAssignment.Role


@dataclass(frozen=True)
class TeachingPair:
    """The target 'subject x class' (a gradebook, a period, a test's audience)."""

    subject: Subject
    school_class: SchoolClass


class Actor:
    """A Membership on a date (default today)."""

    def __init__(self, membership: Membership, on=None):
        self.membership = membership
        self.on = on or timezone.localdate()

    @classmethod
    def of(cls, request, on=None) -> "Actor":
        """The request's actor for `on`, built once per request (needs `request.membership`)."""
        on = on or timezone.localdate()
        cache = request.__dict__.setdefault("_actors", {})
        if on not in cache:
            cache[on] = cls(request.membership, on)
        return cache[on]

    @property
    def school_id(self) -> int:
        return self.membership.school_id

    @property
    def _is_active(self) -> bool:
        return self.membership.status == Membership.Status.ACTIVE

    # Role Assignments in force: active, confirmed, covering the date, active Membership.
    @cached_property
    def assignments(self) -> list[RoleAssignment]:
        if not self._is_active:
            return []
        return list(
            RoleAssignment.objects.in_force(self.on).filter(
                school_id=self.school_id, membership=self.membership
            )
        )

    def _ids(self, role: str, column: str) -> frozenset[int]:
        return frozenset(
            getattr(a, column) for a in self.assignments if a.role == role and getattr(a, column)
        )

    @cached_property
    def homeroom_classes(self) -> frozenset[int]:
        return self._ids(Assignment.HOMEROOM_TEACHER, "school_class_id")

    @cached_property
    def teaching_pairs(self) -> frozenset[tuple[int, int]]:
        return frozenset(
            (a.subject_id, a.school_class_id)
            for a in self.assignments
            if a.role == Assignment.SUBJECT_TEACHER
        )

    @cached_property
    def teaching_subjects(self) -> frozenset[int]:
        return frozenset(subject for subject, _ in self.teaching_pairs)

    @cached_property
    def teaching_classes(self) -> frozenset[int]:
        return frozenset(klass for _, klass in self.teaching_pairs)

    @cached_property
    def led_groups(self) -> frozenset[int]:
        return self._ids(Assignment.GROUP_LEADER, "subject_group_id")

    @cached_property
    def group_pairs(self) -> frozenset[tuple[int, int]]:
        """(subject, class) teaching rows in force for subjects of the groups this person leads."""
        if not self.led_groups:
            return frozenset()
        rows = RoleAssignment.objects.in_force(self.on).filter(
            school_id=self.school_id,
            role=Assignment.SUBJECT_TEACHER,
            subject__subject_group_id__in=self.led_groups,
        )
        return frozenset(rows.values_list("subject_id", "school_class_id").distinct())

    @cached_property
    def group_classes(self) -> frozenset[int]:
        return frozenset(klass for _, klass in self.group_pairs)

    @cached_property
    def duties(self) -> frozenset[Duty]:
        """Named duties of the principal-board rows in force."""
        duties = set()
        for a in self.assignments:
            if a.role != Assignment.PRINCIPAL_BOARD:
                continue
            if a.can_reopen_gradebooks:
                duties.add(Duty.REOPEN_GRADEBOOKS)
            if a.title == RoleAssignment.Title.PRINCIPAL or a.signs_for_principal:
                duties.add(Duty.SIGN_FOR_PRINCIPAL)
        return frozenset(duties)

    # The student side: the student this Membership signs in as, and the students it is a
    # Guardian of, each with their Enrollment periods as of the date.
    @cached_property
    def own_student_ids(self) -> frozenset[int]:
        if not self._is_active:
            return frozenset()
        students = Student.objects.filter(school_id=self.school_id, membership=self.membership)
        return frozenset(students.values_list("pk", flat=True))

    @cached_property
    def linked_student_ids(self) -> frozenset[int]:
        if not self._is_active:
            return frozenset()
        links = GuardianLink.objects.filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=self.on),
            school_id=self.school_id,
            membership=self.membership,
            valid_from__lte=self.on,
        )
        return frozenset(links.values_list("student_id", flat=True))

    @cached_property
    def _student_classes(self) -> tuple[dict[int, int], dict[int, set[int]]]:
        """(student -> class in force, student -> classes left by a transfer out whose school year
        has not ended). Two queries for every student of this actor."""
        ids = self.own_student_ids | self.linked_student_ids
        if not ids:
            return {}, {}
        current = dict(
            Enrollment.objects.in_force(self.on)
            .filter(school_id=self.school_id, student_id__in=ids)
            .values_list("student_id", "school_class_id")
        )
        left: dict[int, set[int]] = {}
        transferred = Enrollment.objects.filter(
            school_id=self.school_id,
            student_id__in=ids,
            reason_ended=Enrollment.ReasonEnded.TRANSFER_OUT,
            valid_to__lt=self.on,
            school_year__ends_on__gte=self.on,
        )
        for student, klass in transferred.values_list("student_id", "school_class_id"):
            left.setdefault(student, set()).add(klass)
        return current, left

    @property
    def enrolled_class_of(self) -> dict[int, int]:
        """Own and linked students' class in force on the date."""
        return self._student_classes[0]

    @property
    def left_classes_of(self) -> dict[int, set[int]]:
        """Own and linked students' classes left by a transfer out, readable until year end."""
        return self._student_classes[1]

    @cached_property
    def own_classes(self) -> frozenset[int]:
        """Classes the person's own student is enrolled in (a student's class content)."""
        return frozenset(
            klass for s, klass in self.enrolled_class_of.items() if s in self.own_student_ids
        )

    # Students of the classes this person works in (one query, only when there are such classes).
    @cached_property
    def class_of_student(self) -> dict[int, int]:
        classes = self.homeroom_classes | self.teaching_classes | self.group_classes
        if not classes:
            return {}
        rows = Enrollment.objects.in_force(self.on).filter(
            school_id=self.school_id, school_class_id__in=classes
        )
        return dict(rows.values_list("student_id", "school_class_id"))

    @cached_property
    def roles(self) -> frozenset[Role]:
        """Matrix columns this person occupies."""
        found = {Role(a.role) for a in self.assignments}
        if self.own_student_ids:
            found.add(Role.STUDENT)
        if self.linked_student_ids:
            found.add(Role.GUARDIAN)
        return frozenset(found)
