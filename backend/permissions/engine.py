"""One answer to "may this member do this action on this target, on this date?" (docs/roles.md).

`can(actor, action, target)` is the only check features call; `visible_students` and
`visible_classes` and `visible_pairs` are its queryset form (filtered in SQL, and tested to agree
with `can` for every role and action); `capabilities` summarises an actor for the frontend, which
hides controls with it while the server still checks every request.

Targets: `School`, `SubjectGroup`, `SchoolClass`, `TeachingPair(subject, school_class)`, `Student`.
A scope that cannot say anything about a target type refuses it (for example a score is a
subject x class fact, so a group leader's "own group" reaches `TeachingPair`s, never a `Student`,
and the engine cannot leak other subjects through a student)."""

from django.db.models import Q, QuerySet

from schools.models import Enrollment, SchoolClass, Student, SubjectGroup
from tenancy.models import School

from .actor import Actor, TeachingPair
from .matrix import ACTIONS, MATRIX, Access, Cell, Role, Scope

# A student who left (transfer out, drop-out, graduation) and their Guardians keep these two on the
# student, read only, until the leaving period's school year ends (docs/roles.md "After leaving
# the School"). A student still at the School, or a continuing one between years, has every
# student-scoped cell of the matrix.
POST_LEAVE_STUDENT_ACTIONS = frozenset({"student_profile.view", "scores.view"})

# Class-level reads. They have no matrix row: staff reach them through their class scopes
# (STAFF_CLASS_READS), a student and their Guardians through the classes the student has been in.
# Value: still allowed on the class left, for a student who left. `class_records.view` is the
# class-level content only (notices, discussions, class-level summaries); anything per student
# (scores, attendance, conduct) goes through its own action on a Student, pair or class.
CLASS_READS = {
    "class_activities.view": True,
    "classmates.view_basic": True,
    "class_teachers.view": True,
    "class_records.view": False,
}

# The class scope through which each staff role reads classes. The School admin has none (least
# data) and neither has the operator.
STAFF_CLASS_READS = {
    Role.PRINCIPAL_BOARD: Scope.SCHOOL,
    Role.GROUP_LEADER: Scope.GROUP_CLASSES,
    Role.HOMEROOM_TEACHER: Scope.HOMEROOM_CLASS,
    Role.SUBJECT_TEACHER: Scope.TEACHING_CLASSES,
}

Target = School | SubjectGroup | SchoolClass | TeachingPair | Student


def _school_id(target) -> int | None:
    if isinstance(target, School):
        return target.pk
    if isinstance(target, TeachingPair):
        ids = {target.subject.school_id, target.school_class.school_id}
        return ids.pop() if len(ids) == 1 else None
    return target.school_id


def _cells(actor: Actor, action: str, *, released: bool, read: bool):
    """The matrix cells that apply to this actor's roles and are strong enough for the action."""
    definition = ACTIONS[action]
    needs = Access.READ if read else definition.needs
    for role in actor.roles:
        cell = MATRIX[definition.row].cells[role]
        if cell.access < needs:
            continue
        if cell.released and not released:
            continue
        if cell.duty is not None and cell.duty not in actor.duties:
            continue
        yield cell


def _open_students(actor: Actor, ids: frozenset[int], action: str) -> frozenset[int]:
    """The ids still at the School on the date; for the post-leave reads also those who left and
    whose leaving period's school year has not ended."""
    access = actor.student_access
    after_leaving = action in POST_LEAVE_STUDENT_ACTIONS
    return frozenset(
        s for s in ids if access[s].at_school or (after_leaving and access[s].classes_left)
    )


def _scope_classes(actor: Actor, scope: Scope) -> frozenset[int] | None:
    """The classes a scope reaches as class targets; None for every class of the School. The one
    place both `can` and `visible_classes` read, so they cannot disagree."""
    match scope:
        case Scope.SCHOOL:
            return None
        case Scope.GROUP_CLASSES:
            return actor.group_classes
        case Scope.HOMEROOM_CLASS:
            return actor.homeroom_classes
        case Scope.TEACHING_CLASSES:
            return actor.teaching_classes
        case Scope.ENROLLED_CLASS:
            return actor.own_classes
    return frozenset()


def _student_class_reads(actor: Actor, action: str) -> frozenset[int]:
    """Classes a student reads (and their Guardians): every class they have been in while they are
    still at the School, the class left (not its records) after leaving until the year ends."""
    classes: set[int] = set()
    for access in actor.student_access.values():
        if access.at_school:
            classes |= access.classes_ever
        elif CLASS_READS[action]:
            classes |= access.classes_left
    return frozenset(classes)


def _class_reads(actor: Actor, action: str) -> frozenset[int] | None:
    """The classes a class read reaches for this actor; None for every class of the School."""
    classes = set(_student_class_reads(actor, action))
    for role, scope in STAFF_CLASS_READS.items():
        if role in actor.roles:
            reached = _scope_classes(actor, scope)
            if reached is None:
                return None
            classes |= reached
    return frozenset(classes)


def _in_classes(classes: frozenset[int], target, *, students: bool, pairs: bool, actor: Actor):
    if pairs and isinstance(target, TeachingPair):
        return target.school_class.pk in classes
    if students and isinstance(target, Student):
        return actor.class_of_student.get(target.pk) in classes
    return False


def _matches(actor: Actor, scope: Scope, action: str, target) -> bool:
    if isinstance(target, SchoolClass):
        classes = _scope_classes(actor, scope)
        return classes is None or target.pk in classes
    match scope:
        case Scope.SCHOOL:
            return True
        case Scope.GROUP_SUBJECTS:
            if isinstance(target, SubjectGroup):
                return target.pk in actor.led_groups
            return (
                isinstance(target, TeachingPair)
                and target.subject.subject_group_id in actor.led_groups
                and (target.subject.pk, target.school_class.pk) in actor.group_pairs
            )
        case Scope.GROUP_CLASSES:
            return _in_classes(actor.group_classes, target, students=True, pairs=False, actor=actor)
        case Scope.HOMEROOM_CLASS:
            return _in_classes(
                actor.homeroom_classes, target, students=True, pairs=True, actor=actor
            )
        case Scope.TEACHING_CLASSES:
            return _in_classes(
                actor.teaching_classes, target, students=True, pairs=True, actor=actor
            )
        case Scope.ENROLLED_CLASS:
            return _in_classes(actor.own_classes, target, students=False, pairs=True, actor=actor)
        case Scope.TEACHING_PAIR:
            return (
                isinstance(target, TeachingPair)
                and (target.subject.pk, target.school_class.pk) in actor.teaching_pairs
            )
        case Scope.TEACHING_SUBJECT:
            return isinstance(target, TeachingPair) and target.subject.pk in actor.teaching_subjects
        case Scope.SELF:
            return isinstance(target, Student) and target.pk in _open_students(
                actor, actor.own_student_ids, action
            )
        case Scope.LINKED:
            return isinstance(target, Student) and target.pk in _open_students(
                actor, actor.linked_student_ids, action
            )
    raise AssertionError(f"unhandled scope {scope}")


def can(
    actor: Actor, action: str, target: Target, *, released: bool = False, read: bool = False
) -> bool:
    """May `actor` do `action` on `target` (on `actor.on`)?

    `read=True` asks the weaker question "at least read it?": a 👁 cell then counts for a write
    action. It is for callers that gate a read (a GET); a write must never be gated with it
    (`Can(...)` in drf.py applies it to safe methods only). `released=True` says the thing was
    released to students and Guardians; the "once released" cells refuse without it."""
    if action in CLASS_READS:
        if not isinstance(target, SchoolClass) or target.school_id != actor.school_id:
            return False
        classes = _class_reads(actor, action)
        return classes is None or target.pk in classes
    if _school_id(target) != actor.school_id:
        return False
    return any(
        _matches(actor, cell.scope, action, target)
        for cell in _cells(actor, action, released=released, read=read)
    )


def _school_students(actor: Actor) -> QuerySet[Student]:
    return Student.objects.filter(school_id=actor.school_id)


def _enrolled_in(actor: Actor, classes: frozenset[int]):
    return (
        Enrollment.objects.in_force(actor.on)
        .filter(school_id=actor.school_id, school_class_id__in=classes)
        .values("student_id")
    )


def visible_students(
    actor: Actor,
    action: str = "student_profile.view",
    *,
    released: bool = False,
    read: bool = False,
) -> QuerySet[Student]:
    """The students `actor` may act on for `action` (default: see their profile), as a queryset.
    `read` has `can`'s meaning, so a write action lists only the students it may write to unless
    the caller asks for `read=True`."""
    students = _school_students(actor)
    if action in CLASS_READS:  # a class target only
        return students.none()
    ids: set[int] = set()
    class_sets: list[frozenset[int]] = []
    for cell in _cells(actor, action, released=released, read=read):
        match cell.scope:
            case Scope.SCHOOL:
                return students
            case Scope.GROUP_CLASSES | Scope.HOMEROOM_CLASS | Scope.TEACHING_CLASSES:
                class_sets.append(_scope_classes(actor, cell.scope))
            case Scope.SELF:
                ids |= _open_students(actor, actor.own_student_ids, action)
            case Scope.LINKED:
                ids |= _open_students(actor, actor.linked_student_ids, action)
    if not ids and not class_sets:
        return students.none()
    q = students.filter(pk__in=ids)
    for classes in class_sets:
        q = q | students.filter(pk__in=_enrolled_in(actor, classes))
    return q


def visible_classes(
    actor: Actor,
    action: str = "student_profile.view",
    *,
    released: bool = False,
    read: bool = False,
) -> QuerySet[SchoolClass]:
    """The classes `actor` may act on for `action`: exactly those `can(actor, action, klass)`
    accepts (a scope that cannot say anything about a class target adds none)."""
    classes = SchoolClass.objects.filter(school_id=actor.school_id)
    if action in CLASS_READS:
        ids = _class_reads(actor, action)
        return classes if ids is None else classes.filter(pk__in=ids)
    ids = set()
    for cell in _cells(actor, action, released=released, read=read):
        reached = _scope_classes(actor, cell.scope)
        if reached is None:
            return classes
        ids |= reached
    return classes.filter(pk__in=ids)


def visible_pairs(
    actor: Actor,
    action: str,
    *,
    released: bool = False,
    read: bool = False,
    prefix: str = "",
) -> Q:
    """A filter for rows that carry a subject x class (a gradebook, a period, a test): `Model.
    objects.filter(visible_pairs(actor, action))` keeps the rows whose pair `can(actor, action,
    TeachingPair(subject, school_class))` accepts. `prefix` reaches the columns through a relation
    ("gradebook__"); the rows need `school_id`, `subject_id` and `school_class_id`."""

    def column(name: str) -> str:
        return f"{prefix}{name}"

    def pair(subject: int, klass: int) -> Q:
        return Q(**{column("subject_id"): subject, column("school_class_id"): klass})

    nothing = Q(**{column("school_id__in"): []})
    if action in CLASS_READS:  # a class target only
        return nothing
    reach = nothing
    for cell in _cells(actor, action, released=released, read=read):
        match cell.scope:
            case Scope.SCHOOL:
                return Q(**{column("school_id"): actor.school_id})
            case Scope.GROUP_SUBJECTS:
                for subject, klass in actor.group_pairs:
                    reach |= pair(subject, klass)
            case Scope.TEACHING_PAIR:
                for subject, klass in actor.teaching_pairs:
                    reach |= pair(subject, klass)
            case Scope.TEACHING_SUBJECT:
                reach |= Q(**{column("subject_id__in"): actor.teaching_subjects})
            case Scope.HOMEROOM_CLASS | Scope.TEACHING_CLASSES | Scope.ENROLLED_CLASS:
                reach |= Q(**{column("school_class_id__in"): _scope_classes(actor, cell.scope)})
    return Q(**{column("school_id"): actor.school_id}) & reach


def _class_scope(kind: str, classes: frozenset[int] | None) -> dict:
    return {
        "kind": kind,
        "access": "read",
        "once_released": False,
        **({} if classes is None else {"school_classes": sorted(classes)}),
    }


def _describe(actor: Actor, cell: Cell, action: str) -> dict | None:
    """What a cell reaches for this actor, as ids; None when it reaches nothing."""
    scope = cell.scope
    ids: dict[str, object]
    match scope:
        case Scope.SCHOOL:
            ids = {}
        case Scope.GROUP_SUBJECTS:
            ids = {"subject_groups": sorted(actor.led_groups)}
        case Scope.GROUP_CLASSES:
            ids = {"school_classes": sorted(actor.group_classes)}
        case Scope.HOMEROOM_CLASS:
            ids = {"school_classes": sorted(actor.homeroom_classes)}
        case Scope.TEACHING_CLASSES:
            ids = {"school_classes": sorted(actor.teaching_classes)}
        case Scope.ENROLLED_CLASS:
            ids = {"school_classes": sorted(actor.own_classes)}
        case Scope.TEACHING_PAIR:
            ids = {
                "pairs": [
                    {"subject": s, "school_class": c} for s, c in sorted(actor.teaching_pairs)
                ]
            }
        case Scope.TEACHING_SUBJECT:
            ids = {"subjects": sorted(actor.teaching_subjects)}
        case Scope.SELF:
            ids = {"students": sorted(_open_students(actor, actor.own_student_ids, action))}
        case Scope.LINKED:
            ids = {"students": sorted(_open_students(actor, actor.linked_student_ids, action))}
    if scope is not Scope.SCHOOL and not any(ids.values()):
        return None
    return {
        "kind": scope.value,
        "access": "write" if cell.access is Access.WRITE else "read",
        "once_released": cell.released,
        **ids,
    }


def capabilities(actor: Actor) -> list[dict]:
    """Every action the actor has some reach for, with the scopes it applies to. A write action
    lists its read-only scopes too (`access: "read"`)."""
    found = []
    for action in ACTIONS:
        scopes = [
            described
            for cell in _cells(actor, action, released=True, read=True)
            if (described := _describe(actor, cell, action)) is not None
        ]
        if scopes:
            found.append({"action": action, "scopes": scopes})
    for action in CLASS_READS:
        scopes = []
        for role, scope in STAFF_CLASS_READS.items():
            if role not in actor.roles:
                continue
            reached = _scope_classes(actor, scope)
            if reached is None or reached:
                scopes.append(_class_scope(scope.value, reached))
        if mine := _student_class_reads(actor, action):
            scopes.append(_class_scope("enrolled_class", mine))
        if scopes:
            found.append({"action": action, "scopes": scopes})
    return found
