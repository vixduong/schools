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
LEAVE_REASONS = (
    Enrollment.ReasonEnded.TRANSFER_OUT,
    Enrollment.ReasonEnded.DROPPED_OUT,
    Enrollment.ReasonEnded.GRADUATED,
)


@dataclass(frozen=True)
class StudentAccess:
    """Where one own or linked student stands at the School on the date (docs/roles.md "While the
    student is at the School", "After leaving the School")."""

    enrolled_class: int | None  # the class in force
    at_school: bool  # in force, or a continuing student between school years
    classes_ever: frozenset[int]  # every class they started in, on or before the date
    classes_left: frozenset[int]  # classes left by a leave whose school year has not ended
    # (only when not at_school: those students keep the post-leave reads)


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
    def student_access(self) -> dict[int, "StudentAccess"]:
        """Own and linked students -> where they stand at the School on the date. Two queries for
        every student of this actor."""
        ids = self.own_student_ids | self.linked_student_ids
        if not ids:
            return {}
        in_force = dict(
            Enrollment.objects.in_force(self.on)
            .filter(school_id=self.school_id, student_id__in=ids)
            .values_list("student_id", "school_class_id")
        )
        # Every period that has started, oldest first: the last one says how the student stands.
        started: dict[int, list[tuple]] = {student: [] for student in ids}
        rows = (
            Enrollment.objects.filter(
                school_id=self.school_id, student_id__in=ids, valid_from__lte=self.on
            )
            .order_by("valid_from", "id")
            .values_list("student_id", "school_class_id", "reason_ended", "school_year__ends_on")
        )
        for student, klass, reason, year_ends_on in rows:
            started[student].append((klass, reason, year_ends_on))
        return {student: self._access(in_force.get(student), started[student]) for student in ids}

    def _access(self, in_force_class, started) -> "StudentAccess":
        ever = frozenset(klass for klass, _, _ in started)
        if in_force_class is not None:
            return StudentAccess(in_force_class, True, ever, frozenset())
        # Nothing in force: a continuing student between years (the last period ended with the
        # year, or is still open after its year) stays; one who left keeps the post-leave reads
        # until the school year of the leaving period ends; anything else (a class change with no
        # next class) has no access.
        if started and started[-1][1] in (None, Enrollment.ReasonEnded.YEAR_END):
            return StudentAccess(None, True, ever, frozenset())
        left = frozenset(
            klass
            for klass, reason, year_ends_on in started
            if reason in LEAVE_REASONS and year_ends_on >= self.on
        )
        return StudentAccess(None, False, ever, left)

    @cached_property
    def own_classes(self) -> frozenset[int]:
        """Classes the person's own student is enrolled in (a student's class content)."""
        return frozenset(
            access.enrolled_class
            for student, access in self.student_access.items()
            if student in self.own_student_ids and access.enrolled_class is not None
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
