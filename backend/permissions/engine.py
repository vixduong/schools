"""One answer to "may this member do this action on this target, on this date?" (docs/roles.md).

`can(actor, action, target)` is the only check features call; `visible_students` and
`visible_classes` are its queryset form (filtered in SQL); `capabilities` summarises an actor for
the frontend, which hides controls with it while the server still checks every request.

Targets: `School`, `SubjectGroup`, `SchoolClass`, `TeachingPair(subject, school_class)`, `Student`.
A scope that cannot say anything about a target type refuses it (for example a score is a
subject x class fact, so a group leader's "own group" reaches `TeachingPair`s, never a `Student`,
and the engine cannot leak other subjects through a student)."""

from django.db.models import QuerySet

from schools.models import Enrollment, SchoolClass, Student, SubjectGroup
from tenancy.models import School

from .actor import Actor, TeachingPair
from .matrix import ACTIONS, MATRIX, Access, Cell, Scope

# After a transfer out the student and their Guardians keep these two on the student, read only,
# until the school year ends (docs/roles.md "After a transfer out").
POST_TRANSFER_STUDENT_ACTIONS = frozenset({"student_profile.view", "scores.view"})

# Reads on a class that come from being (or having been) in it, for a student and their
# Guardians. Value: still allowed on the class left by a transfer out. Staff reach the class
# through their own matrix rows.
CLASS_READS = {
    "class_activities.view": True,
    "classmates.view_basic": True,
    "class_teachers.view": True,
    "class_records.view": False,
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
    """The ids with a class in force on the date; for the post-transfer reads also those whose
    transfer out has not yet outlived its school year."""
    open_ = {s for s in ids if s in actor.enrolled_class_of}
    if action in POST_TRANSFER_STUDENT_ACTIONS:
        open_ |= {s for s in ids if s in actor.left_classes_of}
    return frozenset(open_)


def _in_classes(classes: frozenset[int], target, *, students: bool, pairs: bool, actor: Actor):
    if isinstance(target, SchoolClass):
        return target.pk in classes
    if pairs and isinstance(target, TeachingPair):
        return target.school_class.pk in classes
    if students and isinstance(target, Student):
        return actor.class_of_student.get(target.pk) in classes
    return False


def _matches(actor: Actor, scope: Scope, action: str, target) -> bool:
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


def _can_read_class(actor: Actor, action: str, klass: SchoolClass) -> bool:
    if klass.pk in actor.enrolled_class_of.values():
        return True
    return CLASS_READS[action] and any(klass.pk in c for c in actor.left_classes_of.values())


def can(
    actor: Actor, action: str, target: Target, *, released: bool = False, read: bool = False
) -> bool:
    """May `actor` do `action` on `target` (on `actor.on`)?

    `read=True` asks the weaker question "at least read it?": a 👁 cell then counts for a write
    action. `released=True` says the thing was released to students and Guardians; the "once
    released" cells refuse without it."""
    if action in CLASS_READS:
        return (
            isinstance(target, SchoolClass)
            and target.school_id == actor.school_id
            and _can_read_class(actor, action, target)
        )
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
    actor: Actor, action: str = "student_profile.view", *, released: bool = False, read: bool = True
) -> QuerySet[Student]:
    """The students `actor` may act on for `action` (default: see their profile)."""
    ids: set[int] = set()
    class_sets: list[frozenset[int]] = []
    for cell in _cells(actor, action, released=released, read=read):
        match cell.scope:
            case Scope.SCHOOL:
                return _school_students(actor)
            case Scope.GROUP_CLASSES:
                class_sets.append(actor.group_classes)
            case Scope.HOMEROOM_CLASS:
                class_sets.append(actor.homeroom_classes)
            case Scope.TEACHING_CLASSES:
                class_sets.append(actor.teaching_classes)
            case Scope.SELF:
                ids |= _open_students(actor, actor.own_student_ids, action)
            case Scope.LINKED:
                ids |= _open_students(actor, actor.linked_student_ids, action)
    students = _school_students(actor)
    if not ids and not class_sets:
        return students.none()
    q = students.filter(pk__in=ids)
    for classes in class_sets:
        q = q | students.filter(pk__in=_enrolled_in(actor, classes))
    return q


def visible_classes(
    actor: Actor, action: str = "student_profile.view", *, released: bool = False, read: bool = True
) -> QuerySet[SchoolClass]:
    """The classes whose content `actor` may act on for `action`."""
    classes = SchoolClass.objects.filter(school_id=actor.school_id)
    ids: set[int] = set()
    for cell in _cells(actor, action, released=released, read=read):
        match cell.scope:
            case Scope.SCHOOL:
                return classes
            case Scope.GROUP_CLASSES | Scope.GROUP_SUBJECTS:
                ids |= actor.group_classes
            case Scope.HOMEROOM_CLASS:
                ids |= actor.homeroom_classes
            case Scope.TEACHING_CLASSES | Scope.TEACHING_PAIR:
                ids |= actor.teaching_classes
            case Scope.ENROLLED_CLASS:
                ids |= actor.own_classes
            case Scope.SELF | Scope.LINKED:
                mine = (
                    actor.own_student_ids if cell.scope is Scope.SELF else actor.linked_student_ids
                )
                for student in _open_students(actor, mine, action):
                    ids |= set(actor.left_classes_of.get(student, ()))
                    if student in actor.enrolled_class_of:
                        ids.add(actor.enrolled_class_of[student])
    return classes.filter(pk__in=ids)


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
    for action, after_transfer in CLASS_READS.items():
        classes = set(actor.enrolled_class_of.values())
        if after_transfer:
            classes |= {c for left in actor.left_classes_of.values() for c in left}
        if classes:
            found.append(
                {
                    "action": action,
                    "scopes": [
                        {
                            "kind": "enrolled_class",
                            "access": "read",
                            "once_released": False,
                            "school_classes": sorted(classes),
                        }
                    ],
                }
            )
    return found
