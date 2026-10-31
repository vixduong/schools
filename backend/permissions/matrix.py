"""The permission matrix of docs/roles.md as data: one Row per matrix row, one Cell per role.

`tests/test_matrix.py` parses the table in the document and fails if it differs from this module,
so the two cannot drift. Each cell keeps the document's own words (`qualifier`) next to the
`Scope` the engine enforces.

Unqualified cells mean "within the role's own scope" (the document's legend): the School for the
School admin and the principal board, the group for a group leader, and so on."""

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Access(IntEnum):
    NO = 0  # ✘
    READ = 1  # 👁
    WRITE = 2  # ✔


SYMBOLS = {Access.NO: "✘", Access.READ: "👁", Access.WRITE: "✔"}


class Role(StrEnum):
    """Matrix columns. Staff roles are RoleAssignment roles; the student's and the Guardian's
    rights come from Student.membership + Enrollment and from GuardianLink; the operator holds
    nothing inside a School."""

    OPERATOR = "operator"
    SCHOOL_ADMIN = "school_admin"
    PRINCIPAL_BOARD = "principal_board"
    GROUP_LEADER = "group_leader"
    HOMEROOM_TEACHER = "homeroom_teacher"
    SUBJECT_TEACHER = "subject_teacher"
    STUDENT = "student"
    GUARDIAN = "guardian"


# The column titles of the document's table, in order.
COLUMNS = {
    "Operator": Role.OPERATOR,
    "School admin": Role.SCHOOL_ADMIN,
    "Principal board": Role.PRINCIPAL_BOARD,
    "Group leader": Role.GROUP_LEADER,
    "Homeroom": Role.HOMEROOM_TEACHER,
    "Subject teacher": Role.SUBJECT_TEACHER,
    "Student": Role.STUDENT,
    "Guardian": Role.GUARDIAN,
}


class Scope(StrEnum):
    """Which targets a cell reaches (see engine.py for how each one matches)."""

    SCHOOL = "school"  # everything in the School
    GROUP_SUBJECTS = "group_subjects"  # the led group, and its subjects taught in a class
    GROUP_CLASSES = "group_classes"  # classes where a subject of the led group is taught
    HOMEROOM_CLASS = "homeroom_class"  # the homeroom class, all subjects, its students
    TEACHING_PAIR = "teaching_pair"  # the subject x class pairs the person teaches
    TEACHING_SUBJECT = "teaching_subject"  # any class of a subject the person teaches
    TEACHING_CLASSES = "teaching_classes"  # classes the person teaches, and their students
    SELF = "self"  # the student themself
    ENROLLED_CLASS = "enrolled_class"  # the class a student is enrolled in (its content)
    LINKED = "linked"  # students the Guardian is linked to


class Duty(StrEnum):
    """A named duty of a principal-board member (RoleAssignment flags)."""

    REOPEN_GRADEBOOKS = "reopen_gradebooks"  # can_reopen_gradebooks
    SIGN_FOR_PRINCIPAL = "sign_for_principal"  # title = principal, or signs_for_principal


@dataclass(frozen=True)
class Cell:
    access: Access
    scope: Scope | None = None
    qualifier: str = ""  # the document's words after the symbol
    released: bool = False  # the caller must say the thing was released ("once released")
    duty: Duty | None = None

    @property
    def doc_text(self) -> str:
        return f"{SYMBOLS[self.access]} {self.qualifier}".strip()


@dataclass(frozen=True)
class Row:
    label: str  # the document's first column
    cells: dict[Role, Cell]


NO = Cell(Access.NO)


def W(scope: Scope, qualifier: str = "", **kw) -> Cell:
    return Cell(Access.WRITE, scope, qualifier, **kw)


def R(scope: Scope, qualifier: str = "", **kw) -> Cell:
    return Cell(Access.READ, scope, qualifier, **kw)


def row(label: str, **cells: Cell) -> Row:
    """Roles left out are ✘; the operator is always ✘."""
    return Row(label, {role: cells.get(role.value, NO) for role in Role})


S = Scope
MATRIX: dict[str, Row] = {
    "school_configure": row(
        "Configure School, years, classes, subjects",
        school_admin=W(S.SCHOOL),
        principal_board=R(S.SCHOOL),
    ),
    "accounts_manage": row(
        "Create accounts, import from Excel, assign roles",
        school_admin=W(S.SCHOOL),
        principal_board=R(S.SCHOOL),
    ),
    "guardian_invite": row(
        "Issue Guardian invite codes",
        school_admin=W(S.SCHOOL),
        homeroom_teacher=W(S.HOMEROOM_CLASS, "own class"),
    ),
    # Teachers read every class's profiles and scores (docs/roles.md); they write only in their
    # own scope, which is why the write rows below keep the narrow scopes.
    "student_profile": row(
        "See student profiles",
        principal_board=R(S.SCHOOL, "all"),
        group_leader=R(S.SCHOOL, "all"),
        homeroom_teacher=R(S.SCHOOL, "all"),
        subject_teacher=R(S.SCHOOL, "all"),
        student=R(S.SELF, "self"),
        guardian=R(S.LINKED, "linked"),
    ),
    "student_profile_sensitive": row(
        "See students' sensitive details (national and Ministry IDs, Guardian contact details)",
        school_admin=R(S.SCHOOL),
        principal_board=R(S.SCHOOL, "all"),
        homeroom_teacher=R(S.HOMEROOM_CLASS, "own class"),
    ),
    "attendance_take": row(
        "Take attendance per period",
        subject_teacher=W(S.TEACHING_PAIR, "own periods"),
    ),
    "attendance_view": row(
        "See attendance",
        principal_board=R(S.SCHOOL, "all"),
        homeroom_teacher=R(S.HOMEROOM_CLASS, "own class"),
        subject_teacher=R(S.TEACHING_PAIR, "own periods"),
        student=R(S.SELF, "self"),
        guardian=R(S.LINKED, "linked"),
    ),
    "leave_request_send": row(
        "Send a leave request",
        guardian=W(S.LINKED, "linked"),
    ),
    "leave_request_approve": row(
        "Approve a leave request",
        principal_board=W(S.SCHOOL),
        homeroom_teacher=W(S.HOMEROOM_CLASS, "own class"),
    ),
    "scores_enter": row(
        "Enter scores, submit gradebook",
        subject_teacher=W(S.TEACHING_PAIR, "own subject × class"),
    ),
    "gradebook_review": row(
        "Approve or return a gradebook",
        principal_board=W(S.SCHOOL),
        group_leader=W(S.GROUP_SUBJECTS, "own group"),
    ),
    "gradebook_reopen": row(
        "Reopen a locked gradebook (reason required, logged)",
        principal_board=W(S.SCHOOL, "named by School", duty=Duty.REOPEN_GRADEBOOKS),
    ),
    "scores_view": row(
        "See scores",
        principal_board=R(S.SCHOOL, "all"),
        group_leader=R(S.SCHOOL, "all"),
        homeroom_teacher=R(S.SCHOOL, "all"),
        subject_teacher=R(S.SCHOOL, "all"),
        student=R(S.SELF, "self, once released", released=True),
        guardian=R(S.LINKED, "linked, once released", released=True),
    ),
    "conduct_rate": row(
        "Rate conduct (end of term)",
        principal_board=R(S.SCHOOL),
        homeroom_teacher=W(S.HOMEROOM_CLASS, "own class"),
        student=R(S.SELF, "self"),
        guardian=R(S.LINKED, "linked"),
    ),
    "lessons": row(
        "Author and publish lessons",
        principal_board=R(S.SCHOOL),
        group_leader=R(S.GROUP_SUBJECTS, "group's"),
        subject_teacher=W(S.TEACHING_SUBJECT, "own subject"),
        student=R(S.ENROLLED_CLASS, "published to own class"),
    ),
    "tests_author": row(
        "Author a test; publish a regular test (incl. 15 and 30-minute quizzes)",
        principal_board=R(S.SCHOOL),
        group_leader=R(S.GROUP_SUBJECTS),
        subject_teacher=W(S.TEACHING_PAIR, "own subject × class"),
    ),
    "tests_approve_periodic": row(
        "Approve a periodic test (mid-term, end of term) before publishing",
        principal_board=W(S.SCHOOL),
        group_leader=W(S.GROUP_SUBJECTS, "own group"),
    ),
    "tests_take": row(
        "Take a published test",
        student=W(S.ENROLLED_CLASS, "own class, in its window"),
    ),
    "tests_grade": row(
        "Grade, release results, push to a gradebook column",
        subject_teacher=W(S.TEACHING_PAIR, "own tests"),
    ),
    "notices_send": row(
        "Send notices",
        school_admin=W(S.SCHOOL, "whole School"),
        principal_board=W(S.SCHOOL, "whole School"),
        group_leader=W(S.GROUP_SUBJECTS, "own group"),
        homeroom_teacher=W(S.HOMEROOM_CLASS, "own class's Guardians"),
        subject_teacher=W(S.TEACHING_CLASSES, "own classes"),
    ),
    "report_card_sign_subject": row(
        "Sign the digital report card: own subject's results",
        subject_teacher=W(S.TEACHING_PAIR, "own subject × class"),
    ),
    "report_card_sign_class": row(
        "Sign the digital report card: the class",
        homeroom_teacher=W(S.HOMEROOM_CLASS, "own class"),
    ),
    "report_card_sign_principal": row(
        "Sign as principal and apply the School's organisational signature",
        principal_board=W(S.SCHOOL, "principal or delegate", duty=Duty.SIGN_FOR_PRINCIPAL),
    ),
    "ministry_reports_export": row(
        "Export Ministry reports (Excel)",
        school_admin=W(S.SCHOOL),
        principal_board=W(S.SCHOOL),
    ),
    "support_access_grant": row(
        "Grant time-limited support access to the operator",
        school_admin=W(S.SCHOOL),
        principal_board=W(S.SCHOOL),
    ),
    "audit_read": row(
        "Read the audit log",
        school_admin=R(S.SCHOOL),
        principal_board=R(S.SCHOOL),
    ),
}


@dataclass(frozen=True)
class ActionDef:
    row: str  # key in MATRIX
    needs: Access  # the cell must give at least this


def _write(row_key: str) -> ActionDef:
    return ActionDef(row_key, Access.WRITE)


def _read(row_key: str) -> ActionDef:
    return ActionDef(row_key, Access.READ)


# Slug -> matrix row. A write action needs a ✔ cell (a 👁 cell reads only: pass `read=True` to
# `can` to ask "may this person at least read it?"); a view/read action is satisfied by 👁 too.
ACTIONS: dict[str, ActionDef] = {
    "school.configure": _write("school_configure"),
    "accounts.manage": _write("accounts_manage"),
    "guardian_invite.issue": _write("guardian_invite"),
    "student_profile.view": _read("student_profile"),
    "student_profile.view_sensitive": _read("student_profile_sensitive"),
    "attendance.take": _write("attendance_take"),
    "attendance.view": _read("attendance_view"),
    "leave_request.send": _write("leave_request_send"),
    "leave_request.approve": _write("leave_request_approve"),
    "scores.enter": _write("scores_enter"),
    "gradebook.review": _write("gradebook_review"),
    "gradebook.reopen": _write("gradebook_reopen"),
    "scores.view": _read("scores_view"),
    "conduct.rate": _write("conduct_rate"),
    "lessons.author": _write("lessons"),
    "lessons.view": _read("lessons"),
    "tests.author": _write("tests_author"),
    "tests.publish_regular": _write("tests_author"),
    "tests.approve_periodic": _write("tests_approve_periodic"),
    "tests.take": _write("tests_take"),
    "tests.grade": _write("tests_grade"),
    "notices.send": _write("notices_send"),
    "report_card.sign_subject": _write("report_card_sign_subject"),
    "report_card.sign_class": _write("report_card_sign_class"),
    "report_card.sign_principal": _write("report_card_sign_principal"),
    "ministry_reports.export": _write("ministry_reports_export"),
    "support_access.grant": _write("support_access_grant"),
    "audit.read": _read("audit_read"),
}
