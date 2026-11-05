"""The database rules of the gradebook (constraints, triggers, grants, audit), exercised as the app
role. The API on top of them is in `test_gradebook_api.py` and `test_save_cells.py`."""

from datetime import timedelta
from decimal import Decimal

import psycopg
import pytest
from django.db import DataError, IntegrityError, ProgrammingError, connection
from django.utils import timezone

from grades.models import Gradebook, GradebookColumn, ScoreEntry
from schools.models import (
    AssessmentProfileVersion,
    Enrollment,
    Grade,
    SchoolYear,
    SubjectLoad,
    Term,
)
from schools.tests.factories import make_class, make_primary_class, make_student
from tenancy.rls import school_scope
from testing import owner_role

DAY = timedelta(days=1)


def entry(a, w, column, student, **fields):
    return ScoreEntry.objects.create(
        school=a, column=column, student=student, entered_by=w["t1"], **fields
    )


def run(sql):
    with connection.cursor() as cursor:
        cursor.execute(sql)


def hold_book(a, w, **fields):
    """A gradebook made now (so its columns can still be added), unsaved columns."""
    return Gradebook.objects.create(
        school=a,
        school_year=w["year"],
        term=fields.pop("term", w["hk2"]),
        subject=fields.pop("subject", w["math"]),
        school_class=fields.pop("school_class", w["7A"]),
        profile_version_id=fields.pop("profile_version_id"),
        opened_by=w["t1"],
    )


# --- Gradebook -------------------------------------------------------------------------------


def test_a_gradebook_is_one_per_term_subject_and_class(schools, w, raw_book, refused):
    a, _ = schools
    refused(
        "gradebook_once_per_term_subject_class",
        a,
        lambda: hold_book(
            a, w, term=w["hk1"], profile_version_id=raw_book["book"].profile_version_id
        ),
    )


def test_the_term_and_the_class_belong_to_the_gradebooks_year(schools, w, raw_book, refused):
    a, _ = schools
    version = raw_book["book"].profile_version_id
    with school_scope(a.pk):
        next_year = SchoolYear.objects.create(
            school=a,
            name="next",
            starts_on=w["year"].ends_on + DAY,
            ends_on=w["year"].ends_on + 200 * DAY,
        )
        next_term = Term.objects.create(
            school=a,
            school_year=next_year,
            name="HK I next",
            starts_on=next_year.starts_on,
            ends_on=next_year.ends_on,
        )
        next_class = make_class(a, next_year, "7A")
    refused(
        "gradebook_term_in_school_year",
        a,
        lambda: hold_book(a, w, term=next_term, profile_version_id=version),
    )
    refused(
        "gradebook_class_in_school_year",
        a,
        lambda: hold_book(a, w, school_class=next_class, profile_version_id=version),
    )


def test_a_gradebook_is_for_a_lower_or_upper_secondary_class(schools, w, raw_book, refused):
    a, _ = schools
    with school_scope(a.pk):
        primary = make_primary_class(a, w["year"], "3A")
    refused(
        "gradebook_secondary_level",
        a,
        lambda: hold_book(
            a, w, school_class=primary, profile_version_id=raw_book["book"].profile_version_id
        ),
    )


def test_only_the_status_of_a_gradebook_changes_and_none_is_deleted(schools, w, raw_book, refused):
    a, _ = schools
    book = raw_book["book"]
    # The app role has UPDATE on `status` only, and no DELETE ...
    for change in (
        lambda books: books.update(opened_by=w["t2"]),
        lambda books: books.update(profile_version=None),
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
            change(Gradebook.objects.filter(pk=book.pk))
    with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
        run("DELETE FROM grades_gradebook")
    with school_scope(a.pk):
        assert Gradebook.objects.filter(pk=book.pk).update(status="draft") == 1
    # ... and a trigger holds it against any role: the profile version above all.
    old = book.profile_version
    with owner_role():
        AssessmentProfileVersion.objects.filter(pk=old.pk).update(effective_to=timezone.localdate())
        other = AssessmentProfileVersion.objects.create(
            level_kind="lower_secondary",
            effective_from=timezone.localdate() + DAY,
            source="Circular 89/2026",
            rules=old.rules,
        )
    for field, value in (
        ("opened_by", w["t2"]),
        ("term", w["hk2"]),
        ("subject", w["pe"]),
        ("profile_version", other),
    ):
        with (
            pytest.raises(IntegrityError, match="gradebook_only_status_changes"),
            owner_role(),
            school_scope(a.pk),
        ):
            Gradebook.objects.filter(pk=book.pk).update(**{field: value})


def test_a_status_is_a_known_one(schools, w, raw_book, refused):
    a, _ = schools
    with pytest.raises(IntegrityError, match="gradebook_status_is_known"), school_scope(a.pk):
        Gradebook.objects.filter(pk=raw_book["book"].pk).update(status="locked")


# --- GradebookColumn -------------------------------------------------------------------------


def test_a_column_is_added_only_in_the_transaction_that_opens_its_gradebook(
    schools, w, raw_book, refused
):
    a, _ = schools
    book = raw_book["book"]
    refused(
        "gradebookcolumn_only_at_opening",
        a,
        lambda: GradebookColumn.objects.create(school=a, gradebook=book, kind="regular", index=4),
    )
    # No column is deleted either.
    with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
        run("DELETE FROM grades_gradebookcolumn")


def test_a_column_is_unique_per_kind_and_index_and_a_known_kind_from_one(
    schools, w, raw_book, refused
):
    a, _ = schools
    version = raw_book["book"].profile_version_id

    def opened_with(term, subject, *columns):
        def make():
            book = hold_book(a, w, term=w[term], subject=w[subject], profile_version_id=version)
            for kind, index in columns:
                GradebookColumn.objects.create(school=a, gradebook=book, kind=kind, index=index)

        return make

    with school_scope(a.pk):
        opened_with("hk2", "math", ("regular", 1), ("regular", 2), ("mid_term", 1))()
    refused(
        "gradebookcolumn_once_per_kind_index",
        a,
        opened_with("hk2", "pe", ("regular", 1), ("regular", 1)),
    )
    refused("gradebookcolumn_kind_is_known", a, opened_with("hk2", "pe", ("final", 1)))
    refused("gradebookcolumn_index_from_1", a, opened_with("hk2", "pe", ("regular", 0)))


def test_a_column_is_released_once_and_never_unset_or_moved(schools, w, raw_book, refused):
    a, _ = schools
    column = raw_book["columns"]["regular", 1]
    moved = raw_book["columns"]["regular", 2]
    with school_scope(a.pk):
        GradebookColumn.objects.filter(pk=column.pk).update(
            released_at=column.gradebook.opened_at, released_by=w["t1"]
        )
    for change in (
        {"released_at": None, "released_by": None},  # unset
        {"released_by": w["t3"]},  # moved to someone else
    ):
        with pytest.raises(IntegrityError, match="gradebookcolumn_release"), school_scope(a.pk):
            GradebookColumn.objects.filter(pk=column.pk).update(**change)
    # Both set together, or neither.
    with (
        pytest.raises(IntegrityError, match="gradebookcolumn_release_has_both"),
        school_scope(a.pk),
    ):
        GradebookColumn.objects.filter(pk=moved.pk).update(released_at=column.gradebook.opened_at)
    # Nothing else about a column changes.
    with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
        GradebookColumn.objects.filter(pk=moved.pk).update(kind="end_term")


# --- ScoreEntry ------------------------------------------------------------------------------


def test_a_value_is_between_0_and_10_with_one_decimal(schools, w, raw_book, make_raw_book, refused):
    a, _ = schools
    column = raw_book["columns"]["regular", 1]
    with school_scope(a.pk):
        for value in (0, 10, Decimal("7.5")):
            entry(a, w, column, w["an"], value=value)
    for bad in (Decimal("10.1"), Decimal("-0.1")):
        refused(
            "scoreentry_value_in_scale",
            a,
            lambda bad=bad: entry(a, w, column, w["an"], value=bad),
        )
    with pytest.raises(DataError), school_scope(a.pk):  # numeric(3,1) holds 99.9 at most
        entry(a, w, column, w["an"], value=Decimal("100"))
    comment = make_raw_book(subject=w["pe"])["columns"]["regular", 1]
    refused("scoreentry_result_is_known", a, lambda: entry(a, w, comment, w["an"], result="maybe"))


def test_an_entry_fits_the_form_of_its_subject(schools, w, make_raw_book, refused):
    a, _ = schools
    scored = make_raw_book()["columns"]["regular", 1]
    comment = make_raw_book(subject=w["pe"])["columns"]["regular", 1]
    with school_scope(a.pk):
        entry(a, w, scored, w["an"], value=Decimal("7"))
        entry(a, w, scored, w["an"])  # clearing carries neither
        entry(a, w, comment, w["an"], result="pass")
        entry(a, w, comment, w["an"], result="fail")
        entry(a, w, comment, w["an"])
    refused("scoreentry_fits_subject", a, lambda: entry(a, w, scored, w["an"], result="pass"))
    refused("scoreentry_fits_subject", a, lambda: entry(a, w, comment, w["an"], value=Decimal("7")))


def test_a_student_must_be_in_the_class_today_during_the_term(schools, w, raw_book, refused):
    a, _ = schools
    column = raw_book["columns"]["regular", 1]
    year, k7a = w["year"], w["7A"]
    with school_scope(a.pk):
        # Fan leaves 7A in 50 days: in the class today and during HK I, not during HK II.
        fan = make_student(a, "Fan")
        Enrollment.objects.create(
            school=a,
            student=fan,
            school_year=year,
            school_class=k7a,
            valid_from=year.starts_on,
            valid_to=w["hk1"].ends_on - 50 * DAY,
            reason_started=Enrollment.ReasonStarted.NEW_YEAR,
            reason_ended=Enrollment.ReasonEnded.CLASS_CHANGE,
        )
        for student in (w["an"], w["eve"], fan):
            entry(a, w, column, student, value=Decimal("5"))
    # Binh is in 7B, Dung left 7A three days ago, Chi is a primary student.
    for name in ("binh", "dung", "chi"):
        refused(
            "scoreentry_student_in_class",
            a,
            lambda name=name: entry(a, w, column, w[name], value=Decimal("5")),
        )
    with school_scope(a.pk):
        second = make_raw_book_hk2(a, w, raw_book)
    refused(
        "scoreentry_student_in_class",
        a,
        lambda: entry(a, w, second, fan, value=Decimal("5")),
    )
    with school_scope(a.pk):
        entry(a, w, second, w["an"], value=Decimal("5"))


def make_raw_book_hk2(a, w, raw_book):
    book = hold_book(a, w, profile_version_id=raw_book["book"].profile_version_id)
    return GradebookColumn.objects.create(school=a, gradebook=book, kind="regular", index=1)


def test_a_student_who_left_keeps_their_entries(schools, w, raw_book, refused):
    a, _ = schools
    column = raw_book["columns"]["regular", 1]
    with school_scope(a.pk):
        entry(a, w, column, w["an"], value=Decimal("8"))
        Enrollment.objects.filter(student=w["an"], school_class=w["7A"]).update(
            valid_to=w["year"].starts_on, reason_ended=Enrollment.ReasonEnded.CLASS_CHANGE
        )
    with school_scope(a.pk):
        assert ScoreEntry.objects.filter(student=w["an"]).count() == 1
    refused(
        "scoreentry_student_in_class",
        a,
        lambda: entry(a, w, column, w["an"], value=Decimal("9")),
    )


def test_today_is_the_schools_day_not_the_sessions(schools, w, raw_book):
    a, _ = schools
    column = raw_book["columns"]["regular", 1]
    year, k7a = w["year"], w["7A"]
    today = timezone.localdate()
    with school_scope(a.pk):
        starts_today, ends_today = make_student(a, "Gus"), make_student(a, "Han")
        Enrollment.objects.create(
            school=a,
            student=starts_today,
            school_year=year,
            school_class=k7a,
            valid_from=today,
            reason_started=Enrollment.ReasonStarted.TRANSFER_IN,
        )
        Enrollment.objects.create(
            school=a,
            student=ends_today,
            school_year=year,
            school_class=k7a,
            valid_from=year.starts_on,
            valid_to=today,
            reason_started=Enrollment.ReasonStarted.NEW_YEAR,
            reason_ended=Enrollment.ReasonEnded.CLASS_CHANGE,
        )
        # Put the session in a zone whose date is not the School's (UTC-12 or UTC+14: at any hour
        # one of them is a day off): a student starting today and one ending today still count.
        with connection.cursor() as cursor:
            for zone, student in (("Etc/GMT+12", starts_today), ("Etc/GMT-14", ends_today)):
                cursor.execute("SELECT set_config('TimeZone', %s, true)", [zone])
                entry(a, w, column, student, value=Decimal("6"))


def test_an_entry_in_flight_holds_its_gradebook_and_enrollment_against_changes(
    schools, w, raw_book, app_conn, second_conn
):
    """A score entry in flight holds its gradebook FOR SHARE (a submit that locks it FOR NO KEY
    UPDATE waits) and the student's enrollment FOR SHARE (a concurrent move waits)."""
    a, _ = schools
    column, book = raw_book["columns"]["regular", 1], raw_book["book"]
    app_conn.execute("BEGIN")
    app_conn.execute("SELECT set_config('app.school_id', %s, true)", [str(a.pk)])
    app_conn.execute(
        "INSERT INTO grades_scoreentry (school_id, column_id, student_id, value, entered_by_id,"
        " entered_at) VALUES (%s, %s, %s, 7, %s, now())",
        [a.pk, column.pk, w["an"].pk, w["t1"].pk],
    )
    second_conn.execute("BEGIN")
    second_conn.execute("SELECT set_config('app.school_id', %s, true)", [str(a.pk)])
    second_conn.execute("SET LOCAL lock_timeout = '200ms'")
    with pytest.raises(psycopg.errors.LockNotAvailable):
        second_conn.execute(
            "SELECT 1 FROM grades_gradebook WHERE id = %s FOR NO KEY UPDATE", [book.pk]
        )
    second_conn.execute("ROLLBACK")
    second_conn.execute("BEGIN")
    second_conn.execute("SELECT set_config('app.school_id', %s, true)", [str(a.pk)])
    second_conn.execute("SET LOCAL lock_timeout = '200ms'")
    with pytest.raises(psycopg.errors.LockNotAvailable):
        second_conn.execute(
            "UPDATE schools_enrollment SET valid_to = valid_from + 40 WHERE student_id = %s",
            [w["an"].pk],
        )
    second_conn.execute("ROLLBACK")
    app_conn.execute("ROLLBACK")


def test_an_entry_is_never_dated_before_the_cells_latest_one(schools, w, raw_book, refused):
    a, _ = schools
    columns = raw_book["columns"]
    first, other = columns["regular", 1], columns["regular", 2]
    at = timezone.now()
    with school_scope(a.pk):
        entry(a, w, first, w["an"], value=Decimal("5"), entered_at=at)
        # The same time is fine (the later id wins); so is an earlier one in another cell.
        entry(a, w, first, w["an"], value=Decimal("6"), entered_at=at)
        entry(a, w, other, w["an"], value=Decimal("4"), entered_at=at - DAY)
        entry(a, w, first, w["bao"], value=Decimal("4"), entered_at=at - DAY)
        entry(a, w, first, w["an"], value=Decimal("7"), entered_at=at + DAY)
    refused(
        "scoreentry_in_order",
        a,
        lambda: entry(a, w, first, w["an"], value=Decimal("9"), entered_at=at),
    )
    with school_scope(a.pk):
        assert ScoreEntry.objects.filter(column=first, student=w["an"]).count() == 3


def test_the_history_cannot_be_rewritten_or_deleted(schools, w, raw_book):
    a, _ = schools
    column = raw_book["columns"]["regular", 1]
    with school_scope(a.pk):
        saved = entry(a, w, column, w["an"], value=Decimal("7"))
    for change in (
        lambda entries: entries.update(value=Decimal("9")),
        lambda entries: entries.update(entered_by=w["t2"]),
        lambda entries: entries.delete(),
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
            change(ScoreEntry.objects.filter(pk=saved.pk))
    with school_scope(a.pk):
        assert ScoreEntry.objects.get(pk=saved.pk).value == Decimal("7")


def test_an_entry_needs_a_draft_gradebook(schools, w, raw_book):
    """Slice 5 adds the other statuses; until then the check on `status` is lifted inside a
    rolled-back transaction to show the trigger refuses an entry for a gradebook that is not one."""
    a, _ = schools
    column, book = raw_book["columns"]["regular", 1], raw_book["book"]
    with (
        pytest.raises(IntegrityError, match="scoreentry_gradebook_open"),
        owner_role(),
        school_scope(a.pk),
    ):
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE grades_gradebook DROP CONSTRAINT gradebook_status_is_known")
            cursor.execute(
                "UPDATE grades_gradebook SET status = 'submitted' WHERE id = %s", [book.pk]
            )
        entry(a, w, column, w["an"], value=Decimal("7"))


# --- SubjectLoad -----------------------------------------------------------------------------


def test_a_subject_load_is_frozen_once_a_gradebook_of_its_year_grade_and_subject_exists(
    schools, w, make_raw_book, refused
):
    a, _ = schools
    with school_scope(a.pk):
        grade8 = Grade.objects.create(school=a, level=w["7A"].grade.level, number=8)
        eighth = SubjectLoad.objects.create(
            school=a, school_year=w["year"], grade=grade8, subject=w["math"], periods_per_year=40
        )
        math = SubjectLoad.objects.get(subject=w["math"], grade=w["7A"].grade)
        # Free while no gradebook exists.
        assert SubjectLoad.objects.filter(pk=math.pk).update(periods_per_year=71) == 1
    make_raw_book()  # MATH, 7A: Grade 7, this year
    refused(
        "subjectload_frozen_by_gradebooks",
        a,
        lambda: SubjectLoad.objects.filter(pk=math.pk).update(periods_per_year=35),
    )
    with school_scope(a.pk):
        # An unchanged value is no change; another subject or another Grade is not held.
        assert SubjectLoad.objects.filter(pk=math.pk).update(periods_per_year=71) == 1
        assert SubjectLoad.objects.filter(subject=w["pe"]).update(periods_per_year=36) == 1
        assert SubjectLoad.objects.filter(pk=eighth.pk).update(periods_per_year=41) == 1
    # The year, Grade and subject of a load never move, and none is deleted.
    for change in (lambda loads: loads.update(grade=grade8),):
        with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
            change(SubjectLoad.objects.filter(pk=math.pk))
    with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
        run("DELETE FROM schools_subjectload")
