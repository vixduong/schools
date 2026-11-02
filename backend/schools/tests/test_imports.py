"""Slice 6b: Excel import of staff, students and Guardians."""

import io
import zipfile
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import load_workbook

from accounts.models import Invitation, RoleAssignment
from schools import imports
from schools.models import Enrollment, GuardianLink, ImportBatch, Student
from tenancy.rls import school_scope

from .conftest import A, B, activate, enroll, make_account, member, post, sign_in
from .factories import make_student, make_subject

pytestmark = pytest.mark.usefixtures("as_app_role")


def xlsx(kind, rows, name=None):
    """The real template with `rows` appended to its data sheet."""
    workbook = load_workbook(io.BytesIO(imports.template(kind)))
    for row in rows:
        workbook.worksheets[0].append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return SimpleUploadedFile(name or f"{kind}.xlsx", buffer.getvalue())


def upload(client, kind, file, year=None, host=A):
    body = {"kind": kind, "file": file} | ({"school_year": year.pk} if year else {})
    return client.post("/api/setup/imports/", body, HTTP_HOST=host)


def commit(client, batch_id):
    return post(client, A, f"setup/imports/{batch_id}/commit/")


@pytest.fixture
def roster(setup, schools):
    """Setup plus Dung (ministry ID HS1) in 7B."""
    a = schools[0]
    with school_scope(a.pk):
        dung = make_student(a, "Dung", ministry_student_id="HS1", national_id="079212000001")
        enroll(a, dung, setup["7B"])
    return setup | {"dung": dung}


def count(model, school, **filters):
    with school_scope(school.pk):
        return model.objects.filter(**filters).count()


def test_template_has_headers_a_guide_and_text_id_columns(admin):
    response = admin.get("/api/setup/imports/templates/students.xlsx", HTTP_HOST=A)
    assert response.status_code == 200
    assert response["Content-Type"] == imports.XLSX
    workbook = load_workbook(io.BytesIO(response.content))
    data, guide = workbook.worksheets
    assert [c.value for c in data[1]] == [c.header for c in imports.COLUMNS["students"]]
    assert data.protection.sheet and data["A1"].protection.locked
    assert data.column_dimensions["B"].number_format == "@"  # national ID keeps leading zeros
    assert guide.max_row == 1 + len(imports.COLUMNS["students"])
    assert admin.get("/api/setup/imports/templates/x.xlsx", HTTP_HOST=A).status_code == 404


def test_students_preview_reports_every_bad_cell_and_writes_nothing(admin, roster, schools):
    year = roster["year"]
    file = xlsx(
        "students",
        [
            ["HS2", "079212000002", "Em", "01/02/2013", "Nữ", "7A", None],
            [None, "79212000003", "Giang", "31/02/2013", "X", "9Z", None],  # lost its leading 0
            [None, None, "Ha", "01/02/2013", "Nam", "7A", None],
        ],
    )
    response = upload(admin, "students", file, year)
    assert response.status_code == 201, response.json()
    body = response.json()
    codes = {(e["row"], e["column"], e["code"]) for e in body["errors"]}
    assert codes == {
        (3, "Số định danh cá nhân", "invalid_national_id"),
        (3, "Ngày sinh", "invalid_date"),
        (3, "Giới tính", "invalid_choice"),
        (4, "Mã học sinh", "student_id_required"),
    }
    assert body["counts"] == {"rows": 3, "errors": 2, "created": 1}
    assert count(Student, schools[0], full_name="Em") == 0  # preview wrote nothing
    assert commit(admin, body["id"]).json() == {"errors": ["has_errors"]}


def test_students_commit_creates_updates_and_moves(admin, roster, schools):
    year = roster["year"]
    rows = [
        ["HS2", "079212000002", "Em", "01/02/2013", "Nữ", "7A", None],
        ["HS1", None, "Dung Nguyen", "02/03/2013", "Nam", "7A", None],  # moves from 7B
        ["HS9", "079212000002", "Em again", "01/02/2013", "Nữ", "7A", None],  # matches Em
        ["HS3", None, "Unknown class", "01/02/2013", "Nam", "9Z", None],
    ]
    batch = upload(admin, "students", xlsx("students", rows), year).json()
    assert batch["errors"] == [{"row": 5, "column": "Lớp", "code": "unknown_class"}]
    batch = upload(admin, "students", xlsx("students", rows[:3]), year).json()
    assert batch["errors"] == [] and batch["counts"]["created"] == 1
    response = commit(admin, batch["id"])
    assert response.status_code == 200, response.json()
    assert [r["enrollment"] for r in response.json()["results"]] == [
        "started",
        "moved",
        "unchanged",
    ]
    today = timezone.localdate()
    with school_scope(schools[0].pk):
        em = Student.objects.get(ministry_student_id="HS2")
        assert em.full_name == "Em again"  # the later row updated the name, not the IDs
        assert Enrollment.objects.get(student=em).valid_from == year.starts_on
        dung = Student.objects.get(pk=roster["dung"].pk)
        assert (dung.full_name, str(dung.date_of_birth)) == ("Dung Nguyen", "2013-03-02")
        old, new = Enrollment.objects.filter(student=dung).order_by("valid_from")
        assert (old.valid_to, old.reason_ended) == (today - timedelta(days=1), "class_change")
        assert (new.school_class_id, new.valid_from) == (roster["7A"].pk, today)
    assert commit(admin, batch["id"]).json() == {"status": ["already_committed"]}


def test_a_row_failing_at_commit_rolls_the_whole_batch_back(admin, roster, schools):
    file = xlsx(
        "students",
        [
            ["HS2", None, "Em", "01/02/2013", "Nữ", "7A", None],
            ["HS1", None, "Dung", "02/03/2013", "Nam", "7A", None],
        ],
    )
    batch = upload(admin, "students", file, roster["year"]).json()
    assert batch["errors"] == []
    today = timezone.localdate().isoformat()
    leave = {"reason": "dropped_out", "on": today}
    assert post(admin, A, f"setup/students/{roster['dung'].pk}/leave/", leave).status_code == 200
    response = commit(admin, batch["id"])
    assert response.status_code == 400
    assert response.json()["errors"] == [{"row": 3, "column": None, "code": "student_not_studying"}]
    assert count(Student, schools[0], ministry_student_id="HS2") == 0
    with school_scope(schools[0].pk):
        assert ImportBatch.objects.get(pk=batch["id"]).status == "previewed"


def test_a_preview_older_than_a_day_needs_a_new_upload(admin, roster, schools):
    file = xlsx("students", [["HS2", None, "Em", "01/02/2013", "Nữ", "7A", None]])
    batch = upload(admin, "students", file, roster["year"]).json()
    with school_scope(schools[0].pk):
        ImportBatch.objects.filter(pk=batch["id"]).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
    assert commit(admin, batch["id"]).json() == {"status": ["preview_expired"]}


def test_guardians_get_invitations_that_activate_into_links(admin, roster, schools):
    rows = [
        ["HS1", None, "Dung", "Trần Thị Bình", "Mẹ", "091 234 5679"],
        [None, "079212000001", "Someone else", "Lê Văn", "Bố", None],
        ["NOPE", None, None, "X", "Bố", None],
    ]
    batch = upload(admin, "guardians", xlsx("guardians", rows)).json()
    assert {(e["row"], e["column"], e["code"]) for e in batch["errors"]} == {
        (3, "Họ và tên học sinh", "student_name_mismatch"),
        (4, "Mã học sinh", "student_not_found"),
    }
    batch = upload(admin, "guardians", xlsx("guardians", rows[:1])).json()
    results = commit(admin, batch["id"]).json()["results"]
    assert results[0]["result"] == "invited" and results[0]["code"]
    with school_scope(schools[0].pk):
        stored = ImportBatch.objects.get(pk=batch["id"]).results
        invitation = Invitation.objects.get()
    assert "code" not in stored[0]  # the plain code is shown once, never kept
    assert (invitation.identifier, invitation.relation) == ("0912345679", "mother")
    _, response = activate(A, results[0]["code"], "0912345679")
    assert response.status_code == 200, response.json()
    assert count(GuardianLink, schools[0], student=roster["dung"]) == 1
    # Imported again: the phone is linked now, so the row is skipped.
    again = upload(admin, "guardians", xlsx("guardians", rows[:1])).json()
    assert again["results"] == [{"row": 2, "result": "skipped", "reason": "already_linked"}]


def test_a_pending_guardian_invitation_is_not_issued_twice(admin, roster):
    rows = [["HS1", None, None, "Bình", "Mẹ", None]]
    commit(admin, upload(admin, "guardians", xlsx("guardians", rows)).json()["id"])
    again = upload(admin, "guardians", xlsx("guardians", rows)).json()
    assert again["results"] == [{"row": 2, "result": "skipped", "reason": "pending_invitation"}]


def test_staff_rows_of_one_person_are_one_invitation(admin, roster, schools):
    with school_scope(schools[0].pk):
        make_subject(schools[0], "TOAN")
    rows = [
        ["Cường", "Cuong@Example.com", "Giáo viên bộ môn", "7A", "TOAN", None, None],
        ["Cường", "cuong@example.com", "Giáo viên chủ nhiệm", "7B", None, None, None],
        ["Dao", "dao@example.com", "Giáo viên bộ môn", "7A", "NOPE", None, None],
        ["Dao", "dao@example.com", "Giáo viên chủ nhiệm", None, None, None, None],
        ["Em", "em@example.com", "Quản trị trường", "7A", None, None, None],
    ]
    batch = upload(admin, "staff", xlsx("staff", rows), roster["year"]).json()
    assert {(e["row"], e["column"], e["code"]) for e in batch["errors"]} == {
        (4, "Mã môn", "unknown_subject"),
        (5, "Lớp", "required"),
        (6, "Lớp", "not_for_role"),
    }
    batch = upload(admin, "staff", xlsx("staff", rows[:2]), roster["year"]).json()
    results = commit(admin, batch["id"]).json()["results"]
    assert results[0]["invitation"] == results[1]["invitation"]
    _, response = activate(A, results[0]["code"], "cuong@example.com")
    assert response.status_code == 200, response.json()
    with school_scope(schools[0].pk):
        roles = RoleAssignment.objects.filter(membership__account__email="cuong@example.com")
        assert sorted(roles.values_list("role", "school_class_id")) == [
            ("homeroom_teacher", roster["7B"].pk),
            ("subject_teacher", roster["7A"].pk),
        ]


@pytest.mark.parametrize(
    ("name", "content", "code"),
    [
        ("roster.xlsm", None, "not_xlsx"),
        ("roster.xlsx", b"not a zip", "not_xlsx"),
    ],
)
def test_files_that_are_not_xlsx_are_refused(admin, name, content, code):
    file = SimpleUploadedFile(name, content or xlsx("guardians", []).read())
    assert upload(admin, "guardians", file).json() == {"file": [code]}


def test_a_renamed_macro_workbook_and_a_wrong_template_are_refused(admin):
    buffer = io.BytesIO(xlsx("guardians", []).read())
    with zipfile.ZipFile(buffer, "a") as archive:
        archive.writestr("xl/vbaProject.bin", b"macro")
    file = SimpleUploadedFile("roster.xlsx", buffer.getvalue())
    assert upload(admin, "guardians", file).json() == {"file": ["not_xlsx"]}
    assert upload(admin, "guardians", xlsx("staff", [])).json() == {"file": ["wrong_template"]}


def test_more_than_3000_rows_are_refused(admin):
    rows = [["HS1", None, None, "X", "Mẹ", None]] * (imports.MAX_ROWS + 1)
    assert upload(admin, "guardians", xlsx("guardians", rows)).json() == {"file": ["too_many_rows"]}


def test_staff_and_students_need_a_school_year(admin):
    response = upload(admin, "students", xlsx("students", []))
    assert response.json() == {"school_year": ["required"]}


def test_only_the_school_admin_imports_and_only_in_their_school(admin, alice, roster, schools):
    board = make_account("board@example.com", display_name="Board")
    member(schools[0], board, RoleAssignment.Role.PRINCIPAL_BOARD)
    file = xlsx("guardians", [["HS1", None, None, "Bình", "Mẹ", None]])
    batch = upload(admin, "guardians", file).json()
    board_client = sign_in(A, "board@example.com")
    assert board_client.get(f"/api/setup/imports/{batch['id']}/", HTTP_HOST=A).status_code == 200
    assert upload(board_client, "guardians", file).status_code == 403
    assert commit(board_client, batch["id"]).status_code == 403
    teacher = sign_in(A, "alice@example.com")
    assert teacher.get("/api/setup/imports/templates/staff.xlsx", HTTP_HOST=A).status_code == 403
    other = make_account("admin-b2@example.com", display_name="Admin B")
    member(schools[1], other, RoleAssignment.Role.SCHOOL_ADMIN)
    client_b = sign_in(B, "admin-b2@example.com")
    assert client_b.get(f"/api/setup/imports/{batch['id']}/", HTTP_HOST=B).status_code == 404
