"""The matrix in docs/roles.md and permissions/matrix.py are the same table, and the engine
answers every cell of it."""

from pathlib import Path

import pytest

from accounts.models import RoleAssignment
from permissions.actor import Actor
from permissions.engine import can
from permissions.matrix import ACTIONS, COLUMNS, MATRIX, Access, Role, Scope

DOC = Path(__file__).resolve().parents[3] / "docs" / "roles.md"

# The plan's action list (docs/slices/slice-5.md), written out once more on purpose.
PLANNED_ACTIONS = """school.configure accounts.manage guardian_invite.issue student_profile.view
student_profile.view_sensitive attendance.take attendance.view leave_request.send
leave_request.approve scores.enter
gradebook.review gradebook.reopen scores.view conduct.rate lessons.author lessons.view
tests.author tests.publish_regular tests.approve_periodic tests.take tests.grade notices.send
report_card.sign_subject report_card.sign_class report_card.sign_principal
ministry_reports.export support_access.grant audit.read""".split()


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def doc_table() -> tuple[list[str], list[list[str]]]:
    """Header cells and body rows of the permission matrix, read from the markdown itself."""
    lines = DOC.read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("| Action |"))
    header = split_row(lines[start])
    rows = []
    for line in lines[start + 2 :]:  # skip the |---| line
        if not line.startswith("|"):
            break
        rows.append(split_row(line))
    return header, rows


DOC_HEADER, DOC_ROWS = doc_table()


def test_the_document_table_has_the_columns_of_the_matrix():
    assert DOC_HEADER == ["Action", *COLUMNS]


def test_the_document_and_matrix_py_have_the_same_rows_in_the_same_order():
    assert [r[0] for r in DOC_ROWS] == [row.label for row in MATRIX.values()]


@pytest.mark.parametrize("doc_row", DOC_ROWS, ids=lambda r: r[0][:40])
def test_every_cell_of_a_document_row_equals_matrix_py(doc_row):
    assert len(doc_row) == len(DOC_HEADER), f"ambiguous row (cell count): {doc_row[0]}"
    row = next(row for row in MATRIX.values() if row.label == doc_row[0])
    expected = [row.cells[role].doc_text for role in COLUMNS.values()]
    assert doc_row[1:] == expected


def test_cell_flags_follow_the_document_words():
    for key, row in MATRIX.items():
        for role, cell in row.cells.items():
            assert cell.released == ("once released" in cell.qualifier), (key, role)
            assert (cell.access is Access.NO) == (cell.scope is None), (key, role)
    assert {k for k, r in MATRIX.items() for c in r.cells.values() if c.duty} == {
        "gradebook_reopen",
        "report_card_sign_principal",
    }
    assert all(row.cells[Role.OPERATOR].access is Access.NO for row in MATRIX.values())


def test_actions_cover_the_planned_list_and_every_matrix_row():
    assert list(ACTIONS) == PLANNED_ACTIONS
    assert {d.row for d in ACTIONS.values()} == set(MATRIX)


# The scope the engine must enforce for each cell, keyed by the column and the document's own words
# (symbol and qualifier; an unqualified cell is just the symbol). Written out here, apart from
# matrix.py, and checked against the parsed document, so a scope changed in matrix.py without the
# document (or the document's words without the scope) fails.
S = Scope
DOC_SCOPES = {
    ("Group leader", "✔ own group"): S.GROUP_SUBJECTS,
    ("Group leader", "👁"): S.GROUP_SUBJECTS,
    ("Group leader", "👁 all"): S.SCHOOL,
    ("Group leader", "👁 group's"): S.GROUP_SUBJECTS,
    ("Guardian", "✔ linked"): S.LINKED,
    ("Guardian", "👁 linked"): S.LINKED,
    ("Guardian", "👁 linked, once released"): S.LINKED,
    ("Homeroom", "✔ own class"): S.HOMEROOM_CLASS,
    ("Homeroom", "✔ own class's Guardians"): S.HOMEROOM_CLASS,
    ("Homeroom", "👁 all"): S.SCHOOL,
    ("Homeroom", "👁 own class"): S.HOMEROOM_CLASS,
    ("Principal board", "✔"): S.SCHOOL,
    ("Principal board", "✔ named by School"): S.SCHOOL,
    ("Principal board", "✔ principal or delegate"): S.SCHOOL,
    ("Principal board", "✔ whole School"): S.SCHOOL,
    ("Principal board", "👁"): S.SCHOOL,
    ("Principal board", "👁 all"): S.SCHOOL,
    ("School admin", "✔"): S.SCHOOL,
    ("School admin", "✔ whole School"): S.SCHOOL,
    ("School admin", "👁"): S.SCHOOL,
    ("Student", "✔ own class, in its window"): S.ENROLLED_CLASS,
    ("Student", "👁 published to own class"): S.ENROLLED_CLASS,
    ("Student", "👁 self"): S.SELF,
    ("Student", "👁 self, once released"): S.SELF,
    ("Subject teacher", "✔ own classes"): S.TEACHING_CLASSES,
    ("Subject teacher", "✔ own periods"): S.TEACHING_PAIR,
    ("Subject teacher", "✔ own subject"): S.TEACHING_SUBJECT,
    ("Subject teacher", "✔ own subject × class"): S.TEACHING_PAIR,
    ("Subject teacher", "✔ own tests"): S.TEACHING_PAIR,
    ("Subject teacher", "👁 all"): S.SCHOOL,
    ("Subject teacher", "👁 own periods"): S.TEACHING_PAIR,
}


def test_every_cell_of_the_document_has_the_scope_the_table_pins():
    seen = set()
    for doc_row in DOC_ROWS:
        row = next(row for row in MATRIX.values() if row.label == doc_row[0])
        for column, text in zip(COLUMNS, doc_row[1:], strict=True):
            actual = row.cells[COLUMNS[column]].scope
            if text.startswith("✘"):
                assert actual is None, (doc_row[0], column)
                continue
            seen.add((column, text))
            assert DOC_SCOPES[(column, text)] is actual, (doc_row[0], column, text, actual)
    assert seen == set(DOC_SCOPES), "a pinned (column, text) is not in the document any more"


# One entry per scope: the targets a cell of that scope reaches in the `world` fixture. Written by
# hand, apart from the engine, so a mistake in either side shows.
SCHOOL_A = {
    "school_a", "group_math", "group_lit", "class_7a", "class_7b", "pair_math_7a",
    "pair_lit_7a", "pair_math_7b", "pair_lit_7b", "student_s1", "student_s2", "student_s3",
}  # fmt: skip
IN_SCOPE = {
    None: set(),
    Scope.SCHOOL: SCHOOL_A,
    # gl_math leads Math; Math is taught (in force) only in 7A
    Scope.GROUP_SUBJECTS: {"group_math", "pair_math_7a"},
    # hr_7a: S3 left 7A, S2 is in 7B
    Scope.HOMEROOM_CLASS: {"class_7a", "pair_math_7a", "pair_lit_7a", "student_s1"},
    # t_math teaches Math in 7A only
    Scope.TEACHING_PAIR: {"pair_math_7a"},
    Scope.TEACHING_SUBJECT: {"pair_math_7a", "pair_math_7b"},
    Scope.TEACHING_CLASSES: {"class_7a", "pair_math_7a", "pair_lit_7a", "student_s1"},
    Scope.SELF: {"student_s1"},
    Scope.ENROLLED_CLASS: {"class_7a", "pair_math_7a", "pair_lit_7a"},
    Scope.LINKED: {"student_s1"},
}

CELLS = [(key, role) for key in MATRIX for role in Role]


@pytest.mark.parametrize("row_key,role", CELLS, ids=[f"{k}-{r.value}" for k, r in CELLS])
def test_matrix_cell(world, row_key, role):
    """One cell of docs/roles.md: allowed exactly on the in-scope targets, at the strength the
    cell gives (✔ write, 👁 read only), refused on every other class, subject, group, student and
    School, and the "once released" cells need `released=True`."""
    cell = MATRIX[row_key].cells[role]
    actor = world.actors[role.value]
    targets = {**world.targets, **world.other_school_targets}
    for action in (a for a, d in ACTIONS.items() if d.row == row_key):
        for read in (False, True):
            for released in (False, True):
                needs = Access.READ if read else ACTIONS[action].needs
                granted = cell.access >= max(needs, Access.READ) and (released or not cell.released)
                allowed = {
                    name
                    for name, target in targets.items()
                    if can(actor, action, target, released=released, read=read)
                }
                expected = IN_SCOPE[cell.scope] if granted else set()
                assert allowed == expected, (action, role.value, read, released)


def test_a_member_with_no_role_may_do_nothing(world):
    nobody = world.actors["nobody"]
    targets = {**world.targets, **world.other_school_targets}.values()
    assert not any(
        can(nobody, action, t, released=True, read=True) for action in ACTIONS for t in targets
    )


def test_named_duties_are_fed_by_the_principal_board_row(world):
    """Reopening needs `can_reopen_gradebooks`; signing as principal needs `title = principal` or
    `signs_for_principal`."""
    from permissions.tests.conftest import assign, make_member

    def board_actor(**fields):
        membership = make_member(world.school, f"b{len(fields)}{fields}@example.com")
        assign(world.school, membership, "principal_board", **fields)
        return Actor(membership)

    school = world.school
    # Only one principal at a time (a constraint): the world's board member steps down to vice.
    RoleAssignment.objects.filter(membership=world.members["board"]).update(title="vice_principal")
    cases = {
        "vice, no flags": (dict(title="vice_principal"), False, False),
        "vice, signs for principal": (
            dict(title="vice_principal", signs_for_principal=True),
            False,
            True,
        ),
        "vice, can reopen": (dict(title="vice_principal", can_reopen_gradebooks=True), True, False),
        "principal, no flags": (dict(title="principal"), False, True),
        "no title, no flags": (dict(), False, False),
    }
    for name, (fields, reopens, signs) in cases.items():
        actor = board_actor(**fields)
        assert can(actor, "gradebook.reopen", school) is reopens, name
        assert can(actor, "report_card.sign_principal", school) is signs, name
