"""Mid-year transfers (docs/slices/1a-slice-6.md): the homeroom teacher records an arriving
student's source School, document and carried results; the gradebook shows them beside this
School's columns; a left student's row is read only. The database rules under it come last."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import ProgrammingError
from django.utils import timezone

from accounts.models import RoleAssignment
from audit.models import AuditEvent
from grades import views
from grades.models import CarriedResult, TransferIn
from grades.tests.conftest import TODAY, staff
from schools.models import Enrollment
from schools.tests.factories import make_student
from tenancy.rls import school_scope
from testing import A

HOMEROOM = "alice@example.com"  # homeroom teacher of 7A; Eve arrived in 7A three days ago
TEACHER = "t1@example.com"
PDF = b"%PDF-1.7\n%transfer document\n"


@pytest.fixture(autouse=True)
def _storage_in_a_temp_dir(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture
def upload(client_of):
    """`upload(who, book, student, **fields)`: POST the transfer record (a response)."""

    def post(who, book, student, source_school="THCS Lê Lợi", content=PDF, name="eve.pdf"):
        fields = {"document": SimpleUploadedFile(name, content)}
        if source_school is not None:
            fields["source_school"] = source_school
        return client_of(who).post(
            f"/api/setup/gradebooks/{book['id']}/students/{student.pk}/transfer/",
            fields,
            HTTP_HOST=A,
        )

    return post


@pytest.fixture
def filled(w, book, columns, save):
    """MATH, 7A, HK I with a score for An, Bao and Eve (those in the class) in every column."""
    cells = [
        {"column": column, "student": w[student].pk, "value": 7, "expected": None}
        for column in columns(book).values()
        for student in ("an", "bao", "eve")
    ]
    assert save(book["id"], cells).status_code == 200
    return book


@pytest.fixture
def carry(call, client_of):
    """`carry(who, book, student, results)`: PUT the carried results (a response)."""

    def put(who, book, student, results):
        return call(
            client_of(who),
            "put",
            f"gradebooks/{book['id']}/students/{student.pk}/carried/",
            {"results": results},
        )

    return put


def row(book, student):
    return next(r for r in book["students"] if r["id"] == student.pk)


def get(call, client_of, who, book):
    return call(client_of(who), "get", f"gradebooks/{book['id']}/").json()


# --- the homeroom teacher records an arrival -----------------------------------------------------


def test_the_homeroom_teacher_records_the_source_the_document_and_the_carried_results(
    schools, w, book, upload, carry, call, client_of
):
    before = row(book, w["eve"])
    assert before["can_carry"] is False  # the detail was fetched by t1, a subject teacher
    assert before["arrival"]["source_school"] is None and before["carried"] == []
    sent = upload(HOMEROOM, book, w["eve"])
    assert sent.status_code == 201, sent.content
    saved = carry(
        HOMEROOM,
        book,
        w["eve"],
        [
            {"kind": "regular", "index": 1, "value": 8},
            {"kind": "regular", "index": 2, "value": 7.5},
            {"kind": "mid_term", "index": 1, "value": 6},
        ],
    )
    assert saved.status_code == 200, saved.content
    eve = row(saved.json(), w["eve"])
    assert eve["can_carry"] is True
    assert eve["arrival"]["source_school"] == "THCS Lê Lợi"
    assert eve["arrival"]["document_name"] == "eve.pdf"
    assert [(c["kind"], c["index"], c["value"]) for c in eve["carried"]] == [
        ("mid_term", 1, 6.0),
        ("regular", 1, 8.0),
        ("regular", 2, 7.5),
    ]
    # The subject teacher reads it, and cannot change it.
    seen = row(get(call, client_of, TEACHER, book), w["eve"])
    assert seen["can_carry"] is False and len(seen["carried"]) == 3
    # The other students have no arrival, and the School's own cells are untouched.
    assert row(saved.json(), w["an"])["arrival"] is None
    assert row(saved.json(), w["eve"])["cells"] == []


def test_a_resend_without_changes_writes_nothing_and_an_empty_value_clears_a_result(
    schools, w, book, carry
):
    first = [{"kind": "regular", "index": 1, "value": 8}]
    assert carry(HOMEROOM, book, w["eve"], first).status_code == 200
    assert carry(HOMEROOM, book, w["eve"], first).status_code == 200
    with school_scope(schools[0].pk):
        assert CarriedResult.objects.count() == 1
    cleared = carry(HOMEROOM, book, w["eve"], [{"kind": "regular", "index": 1, "value": None}])
    assert row(cleared.json(), w["eve"])["carried"] == []
    with school_scope(schools[0].pk):
        assert CarriedResult.objects.count() == 2  # the history keeps both


def test_a_comment_only_subject_carries_a_result_not_a_value(schools, w, open_book, carry):
    pe = open_book(subject=w["pe"])
    ok = carry(HOMEROOM, pe, w["eve"], [{"kind": "regular", "index": 1, "result": "pass"}])
    assert row(ok.json(), w["eve"])["carried"][0]["result"] == "pass"
    bad = carry(HOMEROOM, pe, w["eve"], [{"kind": "mid_term", "index": 1, "value": 5}])
    assert bad.status_code == 400
    assert bad.json() == {"results": [{"kind": "mid_term", "index": 1, "code": "wrong_form"}]}


def test_a_bad_result_is_refused_by_kind_and_index_and_nothing_is_saved(schools, w, book, carry):
    response = carry(
        HOMEROOM,
        book,
        w["eve"],
        [
            {"kind": "regular", "index": 1, "value": 8},
            {"kind": "regular", "index": 2, "value": 11},
            {"kind": "regular", "index": 3, "value": 7.55},
            {"kind": "mid_term", "index": 1, "value": "x"},
            {"kind": "regular", "index": 9, "value": 5},
        ],
    )
    assert response.status_code == 400
    assert response.json() == {
        "results": [
            {"kind": "regular", "index": 2, "code": "out_of_range"},
            {"kind": "regular", "index": 3, "code": "too_many_decimals"},
            {"kind": "mid_term", "index": 1, "code": "wrong_form"},
            {"kind": "regular", "index": 9, "code": "unknown_column"},
        ]
    }
    with school_scope(schools[0].pk):
        assert CarriedResult.objects.count() == 0
    duplicate = carry(
        HOMEROOM,
        book,
        w["eve"],
        [{"kind": "regular", "index": 1, "value": 1}, {"kind": "regular", "index": 1, "value": 2}],
    )
    assert (duplicate.status_code, duplicate.json()) == (400, {"results": ["duplicate"]})


def test_only_an_arriving_student_has_carried_results(w, book, upload, carry):
    for student in (w["an"], w["bao"]):  # in the class since the year began
        assert upload(HOMEROOM, book, student).json() == {"student": ["not_arrived"]}
        refused = carry(HOMEROOM, book, student, [{"kind": "regular", "index": 1, "value": 5}])
        assert refused.json() == {"student": ["not_arrived"]}


def test_a_student_outside_the_gradebooks_roster_is_not_found(schools, w, book, carry):
    with school_scope(schools[0].pk):
        stranger = make_student(schools[0], "Stranger")
    response = carry(HOMEROOM, book, stranger, [{"kind": "regular", "index": 1, "value": 5}])
    assert response.status_code == 404


# --- who may write and who may read --------------------------------------------------------------


def test_only_the_homeroom_teacher_of_the_class_records_and_enters(
    schools, w, book, upload, carry, reviewers, board_member, guardian_of_an
):
    result = [{"kind": "regular", "index": 1, "value": 5}]
    for who in (TEACHER, "t2@example.com", "gl@example.com", board_member, "admin-a@example.com"):
        assert upload(who, book, w["eve"]).status_code == 403, who
        assert carry(who, book, w["eve"], result).status_code == 403, who
    assert upload(guardian_of_an, book, w["eve"]).status_code == 403
    with school_scope(schools[0].pk):
        assert TransferIn.objects.count() == 0 and CarriedResult.objects.count() == 0


def test_the_homeroom_teacher_of_another_class_is_refused(schools, w, book, upload):
    other = staff(schools[0], "other-homeroom@example.com")
    with school_scope(schools[0].pk):
        RoleAssignment.objects.create(
            school=schools[0],
            membership=other,
            role=RoleAssignment.Role.HOMEROOM_TEACHER,
            school_year=w["7B"].school_year,
            school_class=w["7B"],
            valid_from=TODAY - timedelta(days=30),
        )
    assert upload("other-homeroom@example.com", book, w["eve"]).status_code == 403


# --- the document --------------------------------------------------------------------------------


def test_the_document_is_read_by_the_gradebooks_readers_and_each_read_is_logged(
    schools, w, book, upload, call, client_of, guardian_of_an
):
    assert upload(HOMEROOM, book, w["eve"]).status_code == 201
    path = f"gradebooks/{book['id']}/students/{w['eve'].pk}/transfer/document/"
    for who in (TEACHER, HOMEROOM):
        response = call(client_of(who), "get", path)
        assert response.status_code == 200, who
        assert b"".join(response.streaming_content) == PDF
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"].startswith("attachment")
        assert response["X-Content-Type-Options"] == "nosniff"
        assert "sandbox" in response["Content-Security-Policy"]
        assert response["Cache-Control"] == "no-store"
    assert call(client_of(guardian_of_an), "get", path).status_code == 403
    with school_scope(schools[0].pk):
        reads = AuditEvent.objects.filter(action="transfer_document.view")
        assert reads.count() == 2


def test_there_is_no_document_before_one_is_recorded(w, book, call, client_of):
    path = f"gradebooks/{book['id']}/students/{w['eve'].pk}/transfer/document/"
    assert call(client_of(TEACHER), "get", path).status_code == 404
    other = f"gradebooks/{book['id']}/students/{w['an'].pk}/transfer/document/"
    assert call(client_of(TEACHER), "get", other).status_code == 404


def test_a_new_record_corrects_the_one_before_and_the_files_get_generated_names(
    schools, w, book, upload, call, client_of
):
    upload(HOMEROOM, book, w["eve"], source_school="Wrong School", name="../../etc/passwd.pdf")
    second = upload(HOMEROOM, book, w["eve"], source_school="Right School", name="eve2.pdf")
    assert row(second.json(), w["eve"])["arrival"]["source_school"] == "Right School"
    with school_scope(schools[0].pk):
        keys = list(TransferIn.objects.order_by("id").values_list("document", flat=True))
        names = list(TransferIn.objects.order_by("id").values_list("document_name", flat=True))
    assert names == ["passwd.pdf", "eve2.pdf"]
    assert all(k.startswith(f"{schools[0].pk}/transfers/") and "passwd" not in k for k in keys)
    assert len(set(keys)) == 2


def test_a_document_is_refused_by_its_content_its_size_and_a_missing_field(
    w, book, upload, monkeypatch
):
    assert upload(HOMEROOM, book, w["eve"], content=b"hello", name="a.pdf").json() == {
        "document": ["unsupported_type"]
    }
    assert upload(HOMEROOM, book, w["eve"], content=b"<script>", name="a.png").status_code == 400
    assert upload(HOMEROOM, book, w["eve"], source_school=None).json() == {
        "source_school": ["required"]
    }
    assert upload(HOMEROOM, book, w["eve"], source_school="  ").json() == {
        "source_school": ["required"]
    }
    assert upload(HOMEROOM, book, w["eve"], source_school="x" * 201).json() == {
        "source_school": ["too_long"]
    }
    monkeypatch.setattr(views, "MAX_DOCUMENT_BYTES", len(PDF) - 1)
    assert upload(HOMEROOM, book, w["eve"]).json() == {"document": ["too_large"]}
    monkeypatch.setattr(views, "MAX_DOCUMENT_BYTES", len(PDF))
    assert upload(HOMEROOM, book, w["eve"]).status_code == 201
    monkeypatch.setattr(views, "MAX_DOCUMENT_BYTES", 1024)
    for content, name in ((b"\xff\xd8\xff\xe0jpeg", "a.jpg"), (b"\x89PNG\r\n\x1a\nxx", "a.png")):
        assert upload(HOMEROOM, book, w["eve"], content=content, name=name).status_code == 201


def test_an_oversized_request_is_refused_before_it_is_read(w, book, client_of):
    response = client_of(HOMEROOM).post(
        f"/api/setup/gradebooks/{book['id']}/students/{w['eve'].pk}/transfer/",
        {"source_school": "x", "document": SimpleUploadedFile("a.pdf", PDF)},
        HTTP_HOST=A,
        CONTENT_LENGTH=str(views.MAX_DOCUMENT_BYTES + views.ENVELOPE_BYTES + 1),
    )
    assert (response.status_code, response.json()) == (400, {"document": ["too_large"]})


def test_a_request_without_a_usable_length_is_refused_before_it_is_read(w, book, client_of):
    for length in ("", "abc"):
        response = client_of(HOMEROOM).post(
            f"/api/setup/gradebooks/{book['id']}/students/{w['eve'].pk}/transfer/",
            {"source_school": "x", "document": SimpleUploadedFile("a.pdf", PDF)},
            HTTP_HOST=A,
            CONTENT_LENGTH=length,
        )
        assert response.status_code == 411, length


def test_the_audit_log_shows_a_transfer_record_without_the_file(schools, w, book, upload):
    upload(HOMEROOM, book, w["eve"], name="nguyen-van-eve-hoc-ba.pdf")
    with school_scope(schools[0].pk):
        events = AuditEvent.objects.filter(target_table="grades_transferin")
        assert events.count() == 1
        shown = str(events.get().details)
    assert "nguyen-van-eve" not in shown and "transfers/" not in shown and "THCS" in shown


# --- a signed gradebook locks the carried results ------------------------------------------------


def test_a_submitted_gradebook_refuses_carried_results_and_a_withdrawn_one_takes_them(
    schools, w, filled, carry, call, client_of
):
    submit = call(client_of(TEACHER), "post", f"gradebooks/{filled['id']}/submit/", {})
    assert submit.status_code == 200, submit.content
    result = [{"kind": "regular", "index": 1, "value": 5}]
    refused = carry(HOMEROOM, filled, w["eve"], result)
    assert (refused.status_code, refused.json()) == (400, {"gradebook": ["not_draft"]})
    call(client_of(TEACHER), "post", f"gradebooks/{filled['id']}/withdraw/", {})
    assert carry(HOMEROOM, filled, w["eve"], result).status_code == 200


# --- a student who left --------------------------------------------------------------------------


def test_a_student_who_left_keeps_a_read_only_row_with_the_leaving_date(
    schools, w, book, save, columns, call, client_of
):
    first = columns(book)["regular", 1]
    dung = row(get(call, client_of, TEACHER, book), w["dung"])
    assert dung["in_class"] is False
    with school_scope(schools[0].pk):
        ended = Enrollment.objects.get(student=w["dung"]).valid_to
    assert dung["left_on"] == ended.isoformat()
    refused = save(
        book["id"], [{"column": first, "student": w["dung"].pk, "value": 9, "expected": None}]
    )
    assert refused.status_code == 400
    assert refused.json()["cells"][0]["code"] == "not_enrolled"
    # Still in the class: no leaving date.
    assert row(get(call, client_of, TEACHER, book), w["an"])["left_on"] is None


def test_the_results_of_a_student_who_leaves_mid_term_stay_and_new_ones_are_refused(
    schools, w, book, save, columns, call, client_of
):
    first = columns(book)["regular", 1]
    with school_scope(schools[0].pk):
        fay = make_student(schools[0], "Fay")
        enrollment = Enrollment.objects.create(
            school=schools[0],
            student=fay,
            school_year=w["7A"].school_year,
            school_class=w["7A"],
            valid_from=w["7A"].school_year.starts_on,
            reason_started=Enrollment.ReasonStarted.NEW_YEAR,
        )
    assert (
        save(
            book["id"], [{"column": first, "student": fay.pk, "value": 6, "expected": None}]
        ).status_code
        == 200
    )
    with school_scope(schools[0].pk):
        enrollment.valid_to = timezone.localdate() - timedelta(days=1)
        enrollment.reason_ended = Enrollment.ReasonEnded.TRANSFER_OUT
        enrollment.save()
    detail = get(call, client_of, TEACHER, book)
    left = row(detail, fay)
    assert left["in_class"] is False and left["left_on"] == enrollment.valid_to.isoformat()
    assert [c["value"] for c in left["cells"]] == [6.0]  # the result up to the leaving date stays
    again = save(
        book["id"],
        [{"column": first, "student": fay.pk, "value": 7, "expected": left["cells"][0]["entry"]}],
    )
    assert again.json()["cells"][0]["code"] == "not_enrolled"


# --- the rules the database holds ----------------------------------------------------------------


@pytest.fixture
def eve_arrival(schools, w):
    with school_scope(schools[0].pk):
        return Enrollment.objects.get(student=w["eve"])


def carried(a, w, **kw):
    fields = {"student": w["eve"], "term": w["hk1"], "subject": w["math"], "kind": "regular"}
    fields |= {"index": 1, "value": 5, "entered_by": w["t1"]} | kw
    return CarriedResult.objects.create(school=a, **fields)


def test_a_transfer_record_belongs_to_the_students_transfer_in_enrollment(
    schools, w, refused, eve_arrival
):
    a = schools[0]
    with school_scope(a.pk):
        an_enrollment = Enrollment.objects.get(student=w["an"])
    for student, enrollment in ((w["eve"], an_enrollment), (w["an"], an_enrollment)):
        refused(
            "transferin_is_an_arrival",
            a,
            lambda s=student, e=enrollment: TransferIn.objects.create(
                school=a,
                student=s,
                enrollment=e,
                source_school="X",
                document="k.pdf",
                document_name="k.pdf",
                recorded_by=w["t1"],
            ),
        )
    refused(
        "transferin_source_not_blank",
        a,
        lambda: TransferIn.objects.create(
            school=a,
            student=w["eve"],
            enrollment=eve_arrival,
            source_school=" ",
            document="k.pdf",
            document_name="k.pdf",
            recorded_by=w["t1"],
        ),
    )


def test_a_carried_result_is_for_a_student_who_arrived_in_the_term(schools, w, refused):
    a = schools[0]
    with school_scope(a.pk):
        carried(a, w)  # Eve arrived inside HK I
    refused("carriedresult_student_arrived_in_term", a, lambda: carried(a, w, student=w["an"]))
    refused("carriedresult_student_arrived_in_term", a, lambda: carried(a, w, term=w["hk2"]))


def test_a_carried_result_fits_the_subject_and_the_scale(schools, w, refused):
    a = schools[0]
    refused("carriedresult_fits_subject", a, lambda: carried(a, w, value=None, result="pass"))
    refused("carriedresult_fits_subject", a, lambda: carried(a, w, subject=w["pe"], value=5))
    refused("carriedresult_value_in_scale", a, lambda: carried(a, w, value=10.5))
    refused("carriedresult_value_in_scale", a, lambda: carried(a, w, value=-1))
    refused("carriedresult_kind_is_known", a, lambda: carried(a, w, kind="final"))
    refused("carriedresult_index_from_1", a, lambda: carried(a, w, index=0))
    refused("carriedresult_periodic_is_single", a, lambda: carried(a, w, kind="end_term", index=2))
    with school_scope(a.pk):
        carried(a, w, subject=w["pe"], value=None, result="fail")
        carried(a, w, value=None)  # a cleared cell


def test_a_signed_gradebook_refuses_a_carried_result_in_the_database(
    schools, w, filled, refused, call, client_of
):
    a = schools[0]
    with school_scope(a.pk):
        carried(a, w)
    call(client_of(TEACHER), "post", f"gradebooks/{filled['id']}/submit/", {})
    refused("carriedresult_gradebook_open", a, lambda: carried(a, w, value=6))
    # Another subject's gradebook is not affected.
    with school_scope(a.pk):
        carried(a, w, subject=w["pe"], value=None, result="pass")


def test_the_histories_cannot_be_rewritten(schools, w, eve_arrival):
    a = schools[0]
    with school_scope(a.pk):
        row_ = carried(a, w)
    for change in (
        lambda: CarriedResult.objects.filter(pk=row_.pk).update(value=9),
        lambda: CarriedResult.objects.filter(pk=row_.pk).delete(),
        lambda: TransferIn.objects.all().update(source_school="y"),
        lambda: TransferIn.objects.all().delete(),
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
            change()
