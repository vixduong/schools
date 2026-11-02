"""Excel import of staff, students and Guardians (docs/slices/slice-6.md, 6b).

`parse` reads an uploaded .xlsx into cleaned rows and per-cell errors; `apply` writes the rows
(students and enrollments; invitations, never Accounts) one row (or staff member) per savepoint,
so a bad row is reported and the others still run. The preview runs `apply` and rolls it all
back, the commit runs it again for real, so both check exactly the same rules."""

import datetime
import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Protection
from rest_framework.exceptions import ValidationError

from accounts.models import PHONE_PATTERN, Invitation, RoleAssignment, normalize_phone
from accounts.serializers import IdentifierField

from .models import (
    Enrollment,
    GuardianLink,
    ImportBatch,
    SchoolClass,
    Student,
    Subject,
    SubjectGroup,
    status_as_of,
)
from .serializers import InvitationSerializer

MAX_BYTES = 5 * 1024 * 1024
MAX_UNZIPPED_BYTES = 50 * 1024 * 1024  # a 5 MB zip can hide a far larger XML (zip bomb)
MAX_ROWS = 3000
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class CellError(Exception):
    def __init__(self, code: str, column: str | None = None, row: dict | None = None):
        super().__init__(code)
        self.code, self.column, self.row = code, column, row


# Cell parsers: an openpyxl value in, a JSON value out (None when blank), or CellError.


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # a number typed into a General cell
    text = unicodedata.normalize("NFC", str(value)).strip()
    return text or None


def _bounded(length):
    def parse(value):
        text = _text(value)
        if text is not None and len(text) > length:
            raise CellError("too_long")
        return text

    return parse


def _date(value):
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    text = _text(value)
    if text is None:
        return None
    try:
        return datetime.datetime.strptime(text, "%d/%m/%Y").date().isoformat()
    except ValueError:
        raise CellError("invalid_date") from None


def _national_id(value):
    text = _text(value)
    if text is not None and not re.fullmatch(r"[0-9]{12}", text):
        raise CellError("invalid_national_id")  # also a number that lost its leading zeros
    return text


def _phone(value):
    text = _text(value)
    if text is None:
        return None
    if not re.fullmatch(PHONE_PATTERN, phone := normalize_phone(text)):
        raise CellError("invalid_phone")
    return phone


def _identifier(value):
    text = _text(value)
    if text is None:
        return None
    try:
        return IdentifierField().run_validation(text)
    except ValidationError:
        raise CellError("invalid_identifier") from None


def _choice(labels: dict[str, str]):
    def parse(value):
        text = _text(value)
        if text is None:
            return None
        try:
            return labels[text.casefold()]
        except KeyError:
            raise CellError("invalid_choice") from None

    return parse


GENDERS = {"nam": Student.Gender.MALE, "nữ": Student.Gender.FEMALE}
RELATIONS = {
    "mẹ": GuardianLink.Relation.MOTHER,
    "bố": GuardianLink.Relation.FATHER,
    "cha": GuardianLink.Relation.FATHER,
    "ông bà": GuardianLink.Relation.GRANDPARENT,
    "ông": GuardianLink.Relation.GRANDPARENT,
    "bà": GuardianLink.Relation.GRANDPARENT,
    "khác": GuardianLink.Relation.OTHER,
}
ROLES = {
    "quản trị trường": RoleAssignment.Role.SCHOOL_ADMIN,
    "ban giám hiệu": RoleAssignment.Role.PRINCIPAL_BOARD,
    "tổ trưởng chuyên môn": RoleAssignment.Role.GROUP_LEADER,
    "giáo viên chủ nhiệm": RoleAssignment.Role.HOMEROOM_TEACHER,
    "giáo viên bộ môn": RoleAssignment.Role.SUBJECT_TEACHER,
}
# The scope columns each role needs; the others must stay blank (invitationrole_scope_matches_role).
ROLE_SCOPE = {
    RoleAssignment.Role.SCHOOL_ADMIN: (),
    RoleAssignment.Role.PRINCIPAL_BOARD: (),
    RoleAssignment.Role.GROUP_LEADER: ("subject_group",),
    RoleAssignment.Role.HOMEROOM_TEACHER: ("school_class",),
    RoleAssignment.Role.SUBJECT_TEACHER: ("school_class", "subject"),
}


@dataclass(frozen=True)
class Column:
    key: str
    header: str
    parse: Any
    help: str
    example: str
    required: bool = False
    text: bool = False  # formatted as text in the template (IDs and phones keep leading zeros)


def _labels(choices: dict[str, str]) -> str:
    return ", ".join(label.capitalize() for label in choices)


NAME = _bounded(200)
STUDENT_IDS = (
    Column(
        "ministry_student_id",
        "Mã học sinh",
        _bounded(30),
        "Mã học sinh trên CSDL ngành. Cần mã học sinh hoặc số định danh.",
        "7901234567",
        text=True,
    ),
    Column(
        "national_id",
        "Số định danh cá nhân",
        _national_id,
        "12 chữ số, giữ số 0 ở đầu.",
        "079212000123",
        text=True,
    ),
)
COLUMNS: dict[str, tuple[Column, ...]] = {
    ImportBatch.Kind.STUDENTS: (
        *STUDENT_IDS,
        Column("full_name", "Họ và tên", NAME, "Họ và tên học sinh.", "Nguyễn Văn An", True),
        Column("date_of_birth", "Ngày sinh", _date, "dd/mm/yyyy.", "05/09/2013", True),
        Column("gender", "Giới tính", _choice(GENDERS), _labels(GENDERS) + ".", "Nam", True),
        Column("school_class", "Lớp", _text, "Tên lớp trong năm học đã chọn.", "7A", True),
        Column(
            "valid_from",
            "Ngày vào lớp",
            _date,
            "dd/mm/yyyy. Để trống: ngày đầu năm học (học sinh mới) hoặc hôm nay (chuyển lớp).",
            "",
        ),
    ),
    ImportBatch.Kind.GUARDIANS: (
        *STUDENT_IDS,
        Column(
            "student_name",
            "Họ và tên học sinh",
            NAME,
            "Để đối chiếu: phải trùng với tên học sinh có mã trên.",
            "Nguyễn Văn An",
        ),
        Column("display_name", "Họ và tên phụ huynh", NAME, "", "Trần Thị Bình", True),
        Column("relation", "Quan hệ", _choice(RELATIONS), _labels(RELATIONS) + ".", "Mẹ", True),
        Column(
            "identifier",
            "Số điện thoại",
            _phone,
            "Số di động Việt Nam. Để trống: mã kích hoạt in ra dùng được với số bất kỳ.",
            "0912345678",
            text=True,
        ),
    ),
    ImportBatch.Kind.STAFF: (
        Column("display_name", "Họ và tên", NAME, "", "Lê Văn Cường", True),
        Column(
            "identifier",
            "Email hoặc số điện thoại",
            _identifier,
            "Dùng để kích hoạt tài khoản.",
            "cuong@example.com",
            True,
            text=True,
        ),
        Column(
            "role",
            "Vai trò",
            _choice(ROLES),
            _labels(ROLES) + ". Mỗi dòng một vai trò; nhiều vai trò thì nhiều dòng.",
            "Giáo viên bộ môn",
            True,
        ),
        Column("school_class", "Lớp", _text, "Giáo viên chủ nhiệm, bộ môn.", "7A"),
        Column("subject", "Mã môn", _text, "Giáo viên bộ môn.", "TOAN"),
        Column("subject_group", "Tổ chuyên môn", _text, "Tổ trưởng chuyên môn.", ""),
        Column("valid_from", "Từ ngày", _date, "dd/mm/yyyy. Để trống: hôm nay.", ""),
    ),
}


def template(kind: str) -> bytes:
    """The blank workbook for `kind`: a data sheet with a locked header row and text-formatted
    ID and phone columns, and a sheet explaining each column with an example."""
    workbook = Workbook()
    data = workbook.active
    data.title = "Dữ liệu"
    guide = workbook.create_sheet("Hướng dẫn")
    guide.append(["Cột", "Bắt buộc", "Cách ghi", "Ví dụ"])
    for index, column in enumerate(COLUMNS[kind], start=1):
        cell = data.cell(row=1, column=index, value=column.header)
        cell.font = Font(bold=True)
        letter = cell.column_letter
        data.column_dimensions[letter].width = max(14, len(column.header) + 4)
        data.column_dimensions[letter].protection = Protection(locked=False)
        if column.text:
            data.column_dimensions[letter].number_format = "@"
        guide.append([column.header, "Có" if column.required else "", column.help, column.example])
    for cell in guide[1]:
        cell.font = Font(bold=True)
    data.freeze_panes = "A2"
    data.protection.sheet = True  # only the header row is locked; data cells are not
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _file_error(code):
    return ValidationError({"file": [code]})


def parse(kind: str, upload) -> tuple[list[dict], list[dict], str]:
    """Rows (`{"row": n, <key>: value}`) of the first sheet, the cell errors as
    `{row, column, code}`, and the file's SHA-256. A file that is no .xlsx of this template is
    refused whole (400 `file`)."""
    if not upload.name.lower().endswith(".xlsx"):
        raise _file_error("not_xlsx")
    if upload.size > MAX_BYTES:
        raise _file_error("too_large")
    content = upload.read()
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            parts = archive.infolist()
        if sum(part.file_size for part in parts) > MAX_UNZIPPED_BYTES:
            raise _file_error("too_large")
        if any(part.filename.lower().endswith("vbaproject.bin") for part in parts):
            raise _file_error("not_xlsx")  # an .xlsm renamed
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except ValidationError:
        raise
    except Exception:  # openpyxl raises many types on a malformed file
        raise _file_error("not_xlsx") from None
    try:
        rows, errors = _read(COLUMNS[kind], workbook.worksheets[0])
    finally:
        workbook.close()
    return rows, errors, hashlib.sha256(content).hexdigest()


def _read(columns, sheet):
    sheet.reset_dimensions()  # some writers store wrong dimensions; read every row
    lines = sheet.iter_rows(values_only=True)
    header = [_text(v) for v in next(lines, ())]
    while header and header[-1] is None:
        header.pop()
    if header != [c.header for c in columns]:
        raise _file_error("wrong_template")
    rows, errors = [], []
    for number, values in enumerate(lines, start=2):
        if all(_text(v) is None for v in values):
            continue
        if len(rows) == MAX_ROWS:
            raise _file_error("too_many_rows")
        values = (*values, *[None] * len(columns))
        row, found = {"row": number}, len(errors)
        for column, value in zip(columns, values, strict=False):
            try:
                row[column.key] = column.parse(value)
                if column.required and row[column.key] is None:
                    raise CellError("required")
            except CellError as error:
                row[column.key] = None
                errors.append({"row": number, "column": column.header, "code": error.code})
        for error in _row_rules(row) if len(errors) == found else ():  # cells first
            header = {c.key: c.header for c in columns}.get(error.column)
            errors.append({"row": number, "column": header, "code": error.code})
        rows.append(row)
    return rows, errors


def _row_rules(row) -> list[CellError]:
    """Rules across the cells of one row."""
    found = []
    if "national_id" in row and not (row["ministry_student_id"] or row["national_id"]):
        found.append(CellError("student_id_required", "ministry_student_id"))
    if row.get("role"):
        needed = ROLE_SCOPE[row["role"]]
        for key in ("school_class", "subject", "subject_group"):
            if key in needed and not row[key]:
                found.append(CellError("required", key))
            elif key not in needed and row[key]:
                found.append(CellError("not_for_role", key))
    return found


class _Run:
    """One pass over a batch's rows. Writes go through the request's School (RLS) and, for
    invitations, through InvitationSerializer, so its rules and the permission engine apply."""

    def __init__(self, batch: ImportBatch, request):
        self.batch, self.request = batch, request
        self.today = timezone.localdate()
        self.headers = {c.key: c.header for c in COLUMNS[batch.kind]}
        self.results, self.errors = [], []
        year = batch.school_year
        self.classes = {c.name: c for c in SchoolClass.objects.filter(school_year=year)}

    def error(self, row, code, column=None):
        self.errors.append({"row": row["row"], "column": self.headers.get(column), "code": code})

    def each(self, rows, write):
        """`write(rows)` in a savepoint; any error is reported on these rows and undone."""
        try:
            with transaction.atomic():
                write(rows)
        except CellError as error:
            self.error(error.row or rows[0], error.code, error.column)
        except IntegrityError as error:
            name = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
            self.error(rows[0], name or "unknown", None)
        except ValidationError as error:
            self.serializer_errors(rows, error.detail)

    def serializer_errors(self, rows, detail):
        detail = detail if isinstance(detail, dict) else {"non_field_errors": detail}
        for field, messages in detail.items():
            if field == "roles" and isinstance(messages, list) and len(messages) == len(rows):
                for row, role_errors in zip(rows, messages, strict=True):
                    self.serializer_errors([row], role_errors or {})
                continue
            column = "ministry_student_id" if field == "student" else field
            for message in messages if isinstance(messages, list) else [messages]:
                # Our rules raise codes ("subject_inactive"); DRF's own carry a `code`.
                code = message if re.fullmatch(r"[a-z_]+", str(message)) else message.code
                self.error(rows[0], str(code), column)

    def student(self, row) -> Student | None:
        for key in ("ministry_student_id", "national_id"):
            if row[key] and (
                found := Student.objects.select_for_update().filter(**{key: row[key]})
            ):
                return found.get()
        return None

    def school_class(self, row) -> SchoolClass:
        if (klass := self.classes.get(row["school_class"])) is None:
            raise CellError("unknown_class", "school_class")
        return klass

    def invite(self, data) -> Invitation:
        serializer = InvitationSerializer(data=data, context={"request": self.request})
        serializer.is_valid(raise_exception=True)
        return serializer.save(created_by=self.request.membership)

    # One writer per kind.

    def students(self, rows):
        (row,) = rows
        klass = self.school_class(row)
        fields = {k: row[k] for k in ("full_name", "date_of_birth", "gender")}
        student = self.student(row)
        if student is None:
            student = Student.objects.create(
                school=self.request.school,
                ministry_student_id=row["ministry_student_id"],
                national_id=row["national_id"],
                **fields,
            )
            result = {"result": "created"}
        else:
            for name, value in fields.items():
                setattr(student, name, value)
            student.save(update_fields=list(fields))
            result = {"result": "updated"}
        result["enrollment"] = self.enroll(student, klass, row["valid_from"])
        self.results.append({"row": row["row"], "student": student.pk, **result})

    def enroll(self, student, klass, given) -> str:
        """Start the student in `klass` unless their open period of the year is already there:
        a new period, a move from `given` (default today), or, for a period that has not
        started yet, the class changed in place."""
        year = self.batch.school_year
        current = (
            Enrollment.objects.select_for_update()
            .filter(student=student, school_year=year, valid_to__isnull=True)
            .first()
        )
        if current is not None and current.school_class_id == klass.pk:
            return "unchanged"
        on = datetime.date.fromisoformat(given) if given else None
        on = on or (self.today if current else year.starts_on)
        events = student.studentstatusevent_set.all()
        if any(status_as_of(events, day) != Student.Status.STUDYING for day in (on, self.today)):
            raise CellError("student_not_studying")
        if current is not None and on <= current.valid_from:
            current.school_class = klass
            current.save(update_fields=["school_class"])
            return "moved"
        reason = Enrollment.ReasonStarted.NEW_YEAR
        if current is not None:
            current.valid_to = on - datetime.timedelta(days=1)
            current.reason_ended = Enrollment.ReasonEnded.CLASS_CHANGE
            current.save(update_fields=["valid_to", "reason_ended"])
            reason = Enrollment.ReasonStarted.CLASS_CHANGE
        Enrollment.objects.create(
            school=self.request.school,
            student=student,
            school_year=year,
            school_class=klass,
            valid_from=on,
            reason_started=reason,
        )
        return "moved" if current else "started"

    def guardians(self, rows):
        (row,) = rows
        student = self.student(row)
        if student is None:
            raise CellError("student_not_found", "ministry_student_id")
        if row["student_name"] and _same(row["student_name"]) != _same(student.full_name):
            raise CellError("student_name_mismatch", "student_name")
        running = Q(valid_to__isnull=True) | Q(valid_to__gte=self.today)
        phone = row["identifier"]
        if (
            phone
            and GuardianLink.objects.filter(
                running, student=student, membership__account__phone=phone
            ).exists()
        ):
            return self.skip(rows, "already_linked")
        pending = self.pending(Invitation.Kind.GUARDIAN).filter(
            student=student, relation=row["relation"]
        )
        if pending.exists():
            return self.skip(rows, "pending_invitation")
        invitation = self.invite(
            {
                "kind": Invitation.Kind.GUARDIAN,
                "identifier": phone,
                "display_name": row["display_name"],
                "student": student.pk,
                "relation": row["relation"],
            }
        )
        self.invited(rows, invitation)

    def staff(self, rows):
        """One staff member: every row with their identifier is one role of one invitation."""
        first = rows[0]
        if self.pending(Invitation.Kind.STAFF).filter(identifier=first["identifier"]).exists():
            return self.skip(rows, "pending_invitation")
        roles = []
        for row in rows:
            try:
                roles.append(self.role(row))
            except CellError as error:
                error.row = row
                raise
        invitation = self.invite(
            {
                "kind": Invitation.Kind.STAFF,
                "identifier": first["identifier"],
                "display_name": first["display_name"],
                "roles": roles,
            }
        )
        self.invited(rows, invitation)

    def role(self, row) -> dict:
        role = {"role": row["role"], "valid_from": row["valid_from"] or self.today}
        if row["school_class"]:
            klass = self.school_class(row)
            role |= {"school_class": klass.pk, "school_year": klass.school_year_id}
        if row["subject"]:
            if (subject := Subject.objects.filter(code=row["subject"]).first()) is None:
                raise CellError("unknown_subject", "subject")
            role["subject"] = subject.pk
        if row["subject_group"]:
            groups = list(SubjectGroup.objects.filter(name=row["subject_group"])[:2])
            if len(groups) != 1:
                code = "ambiguous_subject_group" if groups else "unknown_subject_group"
                raise CellError(code, "subject_group")
            role["subject_group"] = groups[0].pk
        return role

    def pending(self, kind):
        return Invitation.objects.filter(
            kind=kind, status=Invitation.Status.PENDING, expires_at__gt=timezone.now()
        )

    def skip(self, rows, reason):
        self.results += [{"row": r["row"], "result": "skipped", "reason": reason} for r in rows]

    def invited(self, rows, invitation):
        self.results += [
            {
                "row": r["row"],
                "result": "invited",
                "invitation": invitation.pk,
                "code": invitation.code,
            }
            for r in rows
        ]


def _same(name: str) -> str:
    return " ".join(name.split()).casefold()


def apply(batch: ImportBatch, request) -> tuple[list[dict], list[dict]]:
    """Write `batch.rows`, skipping those with cell errors. Returns the per-row results and
    errors; the caller commits or rolls back. Results of invitations carry their plain `code`:
    show it once, never store it."""
    run = _Run(batch, request)
    failed = {e["row"] for e in batch.errors}
    rows = [r for r in batch.rows if r["row"] not in failed]
    if batch.kind == ImportBatch.Kind.STAFF:
        people: dict[str, list[dict]] = {}
        for row in rows:
            people.setdefault(row["identifier"], []).append(row)
        groups = list(people.values())
    else:
        groups = [[row] for row in rows]
    writer = getattr(run, batch.kind)
    for group in groups:
        run.each(group, writer)
    return run.results, run.errors
