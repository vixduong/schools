"""Structure rules, held by the database and exercised as the app role."""

from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from django.db import IntegrityError, ProgrammingError, connection

from accounts.models import RoleAssignment
from accounts.tests.conftest import make_account
from schools.models import (
    Enrollment,
    Grade,
    GuardianLink,
    Level,
    Room,
    SchoolClass,
    SchoolYear,
    Student,
    StudentStatusEvent,
    Subject,
    Term,
    scheduled_change,
    status_as_of,
)
from tenancy.rls import school_scope

from .factories import (
    make_class,
    make_group,
    make_membership,
    make_primary_class,
    make_student,
    make_year,
)

pytestmark = pytest.mark.usefixtures("as_app_role")

D = date
START, END = D(2025, 9, 1), D(2026, 8, 31)


def year(school, name="2025-2026", start=START, end=END):
    return SchoolYear.objects.create(school=school, name=name, starts_on=start, ends_on=end)


def test_school_year_must_end_after_it_starts(schools):
    a, _ = schools
    with pytest.raises(IntegrityError, match="schoolyear_ends_after_start"), school_scope(a.pk):
        year(a, start=D(2025, 9, 1), end=D(2025, 9, 1))


def test_school_years_of_a_school_cannot_overlap(schools):
    a, b = schools
    with school_scope(a.pk):
        year(a)
        year(a, "2026-2027", D(2026, 9, 1), D(2027, 8, 31))  # adjacent is fine
    with school_scope(b.pk):
        year(b)  # the same dates in another School are fine
    with pytest.raises(IntegrityError, match="schoolyear_no_overlap"), school_scope(a.pk):
        year(a, "other", D(2026, 8, 31), D(2026, 12, 31))  # shares the last day


def test_school_year_name_is_unique_per_school(schools):
    a, b = schools
    with school_scope(b.pk):
        year(b)
    with school_scope(a.pk):
        year(a)
    with pytest.raises(IntegrityError, match="schoolyear_name_key"), school_scope(a.pk):
        year(a, start=D(2030, 9, 1), end=D(2031, 8, 31))


def term(school, y, start, end, name="HK I"):
    return Term.objects.create(
        school=school, school_year=y, name=name, starts_on=start, ends_on=end
    )


@pytest.mark.parametrize(
    "start, end, constraint",
    [
        (D(2025, 8, 31), D(2025, 12, 31), "term_inside_school_year"),
        (D(2025, 9, 1), D(2026, 9, 1), "term_inside_school_year"),
        (D(2025, 12, 31), D(2025, 12, 1), "term_ends_after_start"),
    ],
)
def test_term_must_lie_inside_its_year_and_in_order(schools, start, end, constraint):
    a, _ = schools
    with school_scope(a.pk):
        y = year(a)
        term(a, y, D(2025, 9, 1), D(2026, 8, 31))  # the whole year is fine
    with pytest.raises(IntegrityError, match=constraint), school_scope(a.pk):
        term(a, y, start, end)


def test_a_year_cannot_shrink_past_its_terms(schools):
    a, _ = schools
    with school_scope(a.pk):
        y = year(a)
        term(a, y, D(2025, 9, 1), D(2026, 1, 15))
        y.ends_on = D(2026, 6, 1)
        y.save()  # still contains the term
    with pytest.raises(IntegrityError, match="school_year_keeps_its_terms"), school_scope(a.pk):
        y.ends_on = D(2026, 1, 1)
        y.save()


def test_term_update_is_checked_too(schools):
    a, _ = schools
    with school_scope(a.pk):
        y = year(a)
        t = term(a, y, D(2025, 9, 1), D(2026, 1, 15))
    with pytest.raises(IntegrityError, match="term_inside_school_year"), school_scope(a.pk):
        t.ends_on = D(2027, 1, 1)
        t.save()


KINDS = Level.Kind


@pytest.mark.parametrize(
    "kind, number, fits",
    [
        (KINDS.PRIMARY, 1, True),
        (KINDS.PRIMARY, 5, True),
        (KINDS.PRIMARY, 6, False),
        (KINDS.LOWER_SECONDARY, 5, False),
        (KINDS.LOWER_SECONDARY, 6, True),
        (KINDS.LOWER_SECONDARY, 9, True),
        (KINDS.LOWER_SECONDARY, 10, False),
        (KINDS.UPPER_SECONDARY, 9, False),
        (KINDS.UPPER_SECONDARY, 10, True),
        (KINDS.UPPER_SECONDARY, 12, True),
        (KINDS.UPPER_SECONDARY, 13, False),
        (KINDS.PRESCHOOL, 1, False),
    ],
)
def test_grade_number_must_fit_its_level(schools, kind, number, fits):
    a, _ = schools
    with school_scope(a.pk):
        level = Level.objects.create(school=a, kind=kind)
    if fits:
        with school_scope(a.pk):
            Grade.objects.create(school=a, level=level, number=number)
    else:
        with pytest.raises(IntegrityError, match="grade_number_"), school_scope(a.pk):
            Grade.objects.create(school=a, level=level, number=number)


def test_grade_number_is_unique_per_school_and_a_level_keeps_its_kind(schools):
    a, _ = schools
    with school_scope(a.pk):
        level = Level.objects.create(school=a, kind=KINDS.LOWER_SECONDARY)
        Grade.objects.create(school=a, level=level, number=7)
    with pytest.raises(IntegrityError, match="grade_number_key"), school_scope(a.pk):
        Grade.objects.create(school=a, level=level, number=7)
    with pytest.raises(IntegrityError, match="level_kind_is_fixed"), school_scope(a.pk):
        level.kind = KINDS.PRIMARY
        level.save()
    with pytest.raises(IntegrityError, match="level_kind_key"), school_scope(a.pk):
        Level.objects.create(school=a, kind=KINDS.LOWER_SECONDARY)


def test_uniques_are_per_school(schools):
    a, b = schools
    for school in (a, b):  # the same codes and names in two Schools do not clash
        with school_scope(school.pk):
            make_class(school)
            make_class(school, name="7B")
            make_group(school)
            Subject.objects.create(school=school, name="Maths", code="MATH")
    with pytest.raises(IntegrityError, match="subject_code_key"), school_scope(a.pk):
        Subject.objects.create(school=a, name="Other", code="MATH")
    with pytest.raises(IntegrityError, match="schoolclass_name_per_year_key"), school_scope(a.pk):
        existing = SchoolClass.objects.get(school=a, name="7A")
        SchoolClass.objects.create(
            school=a, school_year_id=existing.school_year_id, grade_id=existing.grade_id, name="7A"
        )


def test_class_names_may_repeat_in_another_year(schools):
    a, _ = schools
    with school_scope(a.pk):
        make_class(a)
        make_class(a, year=year(a, "old", D(2000, 9, 1), D(2001, 8, 31)))


def test_every_tenant_to_tenant_reference_must_stay_in_one_school(schools):
    """Each composite FK refuses a row of the other School (the error names the constraint)."""
    a, b = schools
    with school_scope(b.pk):
        klass_b = make_class(b)
        group_b = make_group(b)
        room_b = Room.objects.create(school=b, name="R1")
    with school_scope(a.pk):
        klass_a = make_class(a)

    def refuses(constraint, create):
        with pytest.raises(IntegrityError, match=constraint), school_scope(a.pk):
            create()

    # The Term and Grade triggers fire before the FK check and refuse as well.
    refuses(
        "schools_term_school_year_id_same_school|term_inside_school_year",
        lambda: Term.objects.create(
            school=a,
            school_year_id=klass_b.school_year_id,
            name="HK I",
            starts_on=D(2026, 1, 1),
            ends_on=D(2026, 2, 1),
        ),
    )
    refuses(
        "schools_grade_level_id_same_school|grade_number_fits_level",
        lambda: Grade.objects.create(school=a, level_id=klass_b.grade.level_id, number=8),
    )
    refuses(
        "schools_subject_subject_group_id_same_school",
        lambda: Subject.objects.create(school=a, name="X", code="X", subject_group_id=group_b.pk),
    )
    for field, value in (
        ("school_year_id", klass_b.school_year_id),
        ("grade_id", klass_b.grade_id),
        ("room_id", room_b.pk),
    ):
        refuses(
            f"schools_schoolclass_{field}_same_school",
            lambda field=field, value=value: SchoolClass.objects.create(
                school=a,
                name="9Z",
                **{
                    "school_year_id": klass_a.school_year_id,
                    "grade_id": klass_a.grade_id,
                    **{field: value},
                },
            ),
        )


def test_triggers_that_read_a_parent_row_lock_it_so_a_concurrent_change_cannot_slip_past(schools):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT prosrc FROM pg_proc "
            "WHERE proname IN ('term_inside_school_year', 'grade_number_fits_level',"
            " 'enrollment_fits_student_membership')"
        )
        sources = [source for (source,) in cursor.fetchall()]
    assert len(sources) == 3 and all("FOR SHARE" in source for source in sources)
    # The student row is locked whether or not it has a Membership yet, then the rule is applied.
    (membership_rule,) = [source for source in sources if "INTO m" in source]
    assert "membership_id IS NOT NULL" not in membership_rule


# --- People: students, enrollments, Guardian links ----------------------------------------------


def enroll(school, student, klass, start=None, closed=False):
    """A period from the year's first day (or `start`); `closed` ends it with the year."""
    year = klass.school_year
    return Enrollment.objects.create(
        school=school,
        student=student,
        school_year=year,
        school_class=klass,
        valid_from=start or year.starts_on,
        valid_to=year.ends_on if closed else None,
        reason_started=Enrollment.ReasonStarted.NEW_YEAR,
        reason_ended=Enrollment.ReasonEnded.YEAR_END if closed else None,
    )


NATIONAL_ID = "012345678901"


def test_student_ids_are_unique_per_school_and_blank_means_none(schools):
    a, b = schools
    with school_scope(a.pk):
        blank = make_student(a, ministry_student_id="  ", national_id="")
        make_student(a, "Second blank", ministry_student_id="", national_id="")  # not a clash
        make_student(a, "Third", ministry_student_id="M1", national_id=NATIONAL_ID)
        assert (blank.ministry_student_id, blank.national_id) == (None, None)
    with school_scope(b.pk):
        make_student(b, "Other School", ministry_student_id="M1", national_id=NATIONAL_ID)  # fine
    for field, constraint in (
        ("ministry_student_id", "student_ministry_student_id_key"),
        ("national_id", "student_national_id_key"),
    ):
        with pytest.raises(IntegrityError, match=constraint), school_scope(a.pk):
            make_student(a, "Clash", **{field: "M1" if "ministry" in field else NATIONAL_ID})
    with pytest.raises(IntegrityError, match="student_ids_are_null_not_blank"):
        with school_scope(a.pk):  # a raw write that skips Student.save()
            Student.objects.filter(pk=blank.pk).update(national_id="")


def test_national_id_is_12_digits_when_set(schools):
    a, _ = schools
    with school_scope(a.pk):
        make_student(a, national_id=None)
        make_student(a, "Twelve", national_id="000000000012")
    for bad in ("12345678901", "1234567890123", "12345678901a", "٠١٢٣٤٥٦٧٨٩٠١٢"):
        with pytest.raises(IntegrityError, match="student_national_id_is_12_digits"):
            with school_scope(a.pk):
                make_student(a, "Bad", national_id=bad)


def test_a_membership_signs_in_one_student_only_and_only_in_lower_or_upper_secondary(schools):
    a, _ = schools
    accounts = [make_account(f"s{i}@example.com") for i in range(2)]
    with school_scope(a.pk):
        secondary, primary = make_class(a), make_primary_class(a)
        first, second = make_student(a, "First"), make_student(a, "Second")
        sign_in = make_membership(a, accounts[0])
        other_year = SchoolYear.objects.create(
            school=a, name="next", starts_on=D(2090, 9, 1), ends_on=D(2091, 8, 31)
        )
        later_primary = make_primary_class(a, other_year)
    constraint = "student_membership_needs_secondary_level"
    with pytest.raises(IntegrityError, match=constraint), school_scope(a.pk):
        make_student(a, "Born with one", membership=sign_in)
    with pytest.raises(IntegrityError, match=constraint), school_scope(a.pk):  # not enrolled yet
        Student.objects.filter(pk=first.pk).update(membership=sign_in)
    with school_scope(a.pk):
        enroll(a, first, primary, closed=True)
    with pytest.raises(IntegrityError, match=constraint), school_scope(a.pk):  # primary only
        Student.objects.filter(pk=first.pk).update(membership=sign_in)
    with school_scope(a.pk):
        enroll(a, second, secondary)
        Student.objects.filter(pk=second.pk).update(membership=sign_in)
    # A student who signs in has no use for a primary class afterwards.
    with pytest.raises(IntegrityError, match="enrollment_fits_student_membership"):
        with school_scope(a.pk):
            enroll(a, second, later_primary)
    # One Membership, one student.
    with school_scope(a.pk):
        enroll(a, first, make_class(a, other_year, "8A"))
    with pytest.raises(IntegrityError, match="student_membership_key"), school_scope(a.pk):
        Student.objects.filter(pk=first.pk).update(membership=sign_in)


@contextmanager
def refused(constraint):
    """The write is refused by the database, naming `constraint` (what the API answers with)."""
    with pytest.raises(IntegrityError) as caught:
        yield
    assert caught.value.__cause__.diag.constraint_name == constraint


def test_a_students_membership_holds_no_role_assignment_or_guardian_link_and_the_reverse(schools):
    a, _ = schools
    accounts = [make_account(f"m{i}@example.com") for i in range(3)]
    with school_scope(a.pk):
        klass = make_class(a)
        student, child = make_student(a, "Student"), make_student(a, "Child")
        sign_in, teacher, parent = (make_membership(a, account) for account in accounts)
        enroll(a, student, klass)
        Student.objects.filter(pk=student.pk).update(membership=sign_in)
        RoleAssignment.objects.create(
            school=a, membership=teacher, role="school_admin", valid_from=date(2025, 9, 1)
        )
        GuardianLink.objects.create(
            school=a,
            membership=parent,
            student=child,
            relation="mother",
            valid_from=date(2025, 9, 1),
        )
    with refused("roleassignment_membership_is_not_a_student"):
        with school_scope(a.pk):
            RoleAssignment.objects.create(
                school=a, membership=sign_in, role="school_admin", valid_from=date(2025, 9, 1)
            )
    with refused("guardianlink_membership_is_not_a_student"):
        with school_scope(a.pk):
            GuardianLink.objects.create(
                school=a,
                membership=sign_in,
                student=child,
                relation="father",
                valid_from=date(2025, 9, 1),
            )
    # Moving an existing row onto a student's Membership is checked too.
    with refused("roleassignment_membership_is_not_a_student"):
        with school_scope(a.pk):
            RoleAssignment.objects.filter(membership=teacher).update(membership=sign_in)
    # And a student's sign-in cannot be a Membership that already has a role or a link.
    with school_scope(a.pk):
        enroll(a, child, klass)
    with refused("student_membership_has_no_role_assignment"):
        with school_scope(a.pk):
            Student.objects.filter(pk=child.pk).update(membership=teacher)
    with refused("student_membership_has_no_guardian_link"):
        with school_scope(a.pk):
            Student.objects.filter(pk=child.pk).update(membership=parent)


def test_the_membership_guard_triggers_lock_the_membership_row(schools):
    """The role/link side shares the lock, the student side takes the conflicting one, so two
    transactions racing on the same Membership cannot both miss the other's uncommitted row."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT proname, prosrc FROM pg_proc WHERE proname IN "
            "('membership_is_not_a_student', 'student_membership_holds_no_role_or_link')"
        )
        sources = dict(cursor.fetchall())
    assert "FOR SHARE" in sources["membership_is_not_a_student"]
    assert "FOR NO KEY UPDATE" in sources["student_membership_holds_no_role_or_link"]


def test_an_enrollment_needs_a_class_of_its_own_year(schools):
    a, _ = schools
    with school_scope(a.pk):
        klass = make_class(a)
        next_year = SchoolYear.objects.create(
            school=a, name="next", starts_on=D(2090, 9, 1), ends_on=D(2091, 8, 31)
        )
        student = make_student(a)
    with pytest.raises(IntegrityError, match="schools_enrollment_class_in_school_year"):
        with school_scope(a.pk):  # the class is in the current year, not "next"
            Enrollment.objects.create(
                school=a,
                student=student,
                school_year=next_year,
                school_class=klass,
                valid_from=D(2090, 9, 1),
                reason_started="new_year",
            )


def test_enrollment_periods_of_one_student_cannot_overlap_and_lie_inside_the_year(schools):
    a, _ = schools
    with school_scope(a.pk):
        year = make_year(a)
        klass, other = make_class(a, year), make_class(a, year, "7B")
        student, other_student = make_student(a), make_student(a, "Other student")
        first = enroll(a, student, klass, start=year.starts_on)
        enroll(a, other_student, klass)  # the class takes many students
        # The class change: end the first period, start the second the next day.
        Enrollment.objects.filter(pk=first.pk).update(
            valid_to=year.starts_on + timedelta(days=9), reason_ended="class_change"
        )
        move = year.starts_on + timedelta(days=10)
        Enrollment.objects.create(
            school=a,
            student=student,
            school_year=year,
            school_class=other,
            valid_from=move,
            reason_started="class_change",
        )
    # Two periods of one student cannot share a day, and an open period overlaps everything after.
    with pytest.raises(IntegrityError, match="enrollment_no_overlapping_periods"):
        with school_scope(a.pk):
            enroll(a, student, klass, start=move + timedelta(days=5))
    # A period must lie inside its school year and end with a reason.
    for bad, constraint in (
        ({"valid_from": year.starts_on - timedelta(days=1)}, "enrollment_inside_school_year"),
        ({"valid_from": year.ends_on + timedelta(days=1)}, "enrollment_inside_school_year"),
        (
            {
                "valid_from": year.starts_on,
                "valid_to": year.ends_on + timedelta(days=1),
                "reason_ended": "year_end",
            },
            "enrollment_inside_school_year",
        ),
        ({"valid_from": year.starts_on, "valid_to": year.ends_on}, "enrollment_end_has_a_reason"),
        ({"valid_from": year.starts_on, "reason_ended": "year_end"}, "enrollment_end_has_a_reason"),
        (
            {"valid_from": year.ends_on, "valid_to": year.starts_on, "reason_ended": "year_end"},
            "enrollment_valid_to_after_valid_from",
        ),
    ):
        with pytest.raises(IntegrityError, match=constraint), school_scope(a.pk):
            Enrollment.objects.create(
                school=a,
                student=make_student(a, "Newcomer"),
                school_year=year,
                school_class=klass,
                reason_started="transfer_in",
                **bad,
            )
    # A school year cannot shrink past its enrollments (as with terms).
    with pytest.raises(IntegrityError, match="school_year_keeps_its_enrollments"):
        with school_scope(a.pk):
            year.starts_on = move + timedelta(days=1)
            year.save()


def test_people_references_must_stay_in_one_school(schools):
    a, b = schools
    accounts = [make_account("ga@example.com"), make_account("gb@example.com")]
    with school_scope(b.pk):
        klass_b = make_class(b)
        student_b = make_student(b)
        member_b = make_membership(b, accounts[1])
    with school_scope(a.pk):
        klass_a = make_class(a)
        student_a = make_student(a)
        member_a = make_membership(a, accounts[0])
    year_a, year_b = klass_a.school_year_id, klass_b.school_year_id
    period = {"valid_from": klass_a.school_year.starts_on, "reason_started": "new_year"}

    def refuses(constraint, create):
        with pytest.raises(IntegrityError, match=constraint), school_scope(a.pk):
            create()

    # Enrollment: the class check names the 3-column key as well as the plain one.
    refuses(
        "schools_enrollment_student_id_same_school",
        lambda: Enrollment.objects.create(
            school=a, student=student_b, school_year_id=year_a, school_class=klass_a, **period
        ),
    )
    refuses(
        "schools_enrollment_(school_class_id_same_school|class_in_school_year)",
        lambda: Enrollment.objects.create(
            school=a, student=student_a, school_year_id=year_a, school_class=klass_b, **period
        ),
    )
    refuses(
        "schools_enrollment_(school_year_id_same_school|class_in_school_year)"
        "|enrollment_inside_school_year",
        lambda: Enrollment.objects.create(
            school=a, student=student_a, school_year_id=year_b, school_class=klass_a, **period
        ),
    )
    refuses(
        "schools_guardianlink_student_id_same_school",
        lambda: GuardianLink.objects.create(
            school=a, membership=member_a, student=student_b, relation="mother", valid_from=START
        ),
    )
    refuses(
        "schools_guardianlink_membership_id_same_school",
        lambda: GuardianLink.objects.create(
            school=a, membership=member_b, student=student_a, relation="mother", valid_from=START
        ),
    )
    refuses(
        "schools_studentstatusevent_student_id_same_school",
        lambda: StudentStatusEvent.objects.create(
            school=a, student=student_b, status="graduated", on=START, recorded_by=member_a
        ),
    )
    refuses(
        "schools_studentstatusevent_recorded_by_id_same_school",
        lambda: StudentStatusEvent.objects.create(
            school=a, student=student_a, status="graduated", on=START, recorded_by=member_b
        ),
    )
    refuses(
        "schools_student_membership_id_same_school|student_membership_needs_secondary_level",
        lambda: make_student(a, "X", membership=member_b),
    )


def test_the_status_history_is_append_only_for_the_app_role(schools):
    a, _ = schools
    account = make_account("recorder@example.com")
    with school_scope(a.pk):
        recorder = make_membership(a, account)
        student = make_student(a)
        event = StudentStatusEvent.objects.create(
            school=a, student=student, status="dropped_out", on=START, recorded_by=recorder
        )
    for change in (
        lambda: StudentStatusEvent.objects.filter(pk=event.pk).update(reason="edited"),
        lambda: StudentStatusEvent.objects.filter(pk=event.pk).delete(),
    ):
        with pytest.raises(ProgrammingError, match="permission denied"), school_scope(a.pk):
            change()
    with school_scope(a.pk):
        assert StudentStatusEvent.objects.get(pk=event.pk).reason == ""


def test_student_status_is_derived_from_the_events_as_of_a_date(schools):
    a, _ = schools
    account = make_account("recorder@example.com")
    with school_scope(a.pk):
        recorder = make_membership(a, account)
        student, other = make_student(a), make_student(a, "Other")

    def record(status, on, who=None):
        return StudentStatusEvent.objects.create(
            school=a, student=who or student, status=status, on=on, recorded_by=recorder
        )

    def status_on(day, who=None):
        found = Student.objects.with_status(day).get(pk=(who or student).pk)
        events = StudentStatusEvent.objects.filter(student=found)
        # The SQL annotation and the Python rule agree.
        assert status_as_of(events, day) == found.current_status
        return found.current_status

    with school_scope(a.pk):
        assert status_on(D(2026, 1, 1)) == "studying"  # no event: studying
        record("transferred_out", D(2026, 1, 10))
        record("studying", D(2026, 3, 1))  # came back
        record("dropped_out", D(2026, 2, 1))  # entered late with an earlier date
        record("graduated", D(2026, 3, 1))  # same day: the later event decides
        record("dropped_out", D(2026, 1, 5), other)
        assert [status_on(D(2026, *md)) for md in ((1, 9), (1, 10), (2, 1), (2, 28), (3, 1))] == [
            "studying",
            "transferred_out",
            "dropped_out",
            "dropped_out",
            "graduated",
        ]
        assert status_on(D(2026, 1, 4), other) == "studying"
        assert status_on(D(2026, 1, 5), other) == "dropped_out"
        events = list(StudentStatusEvent.objects.filter(student=student))
    # The next change after a day; a change cancelled by a later event of its day is none.
    assert scheduled_change(events, D(2025, 12, 1)) == {
        "status": "transferred_out",
        "on": D(2026, 1, 10),
    }
    assert scheduled_change(events, D(2026, 1, 10)) == {
        "status": "dropped_out",
        "on": D(2026, 2, 1),
    }
    assert scheduled_change(events, D(2026, 3, 1)) is None
    cancelled = [e for e in events if e.on != D(2026, 3, 1)] + [
        StudentStatusEvent(id=10**6, student=student, status="studying", on=D(2026, 1, 10)),
        StudentStatusEvent(id=10**6 - 1, student=student, status="graduated", on=D(2026, 1, 10)),
    ]
    assert scheduled_change(cancelled, D(2025, 12, 1)) == {
        "status": "dropped_out",
        "on": D(2026, 2, 1),
    }


def test_the_stored_status_and_its_triggers_are_gone(schools):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM information_schema.columns"
            " WHERE table_name = 'schools_student' AND column_name = 'status'"
        )
        assert cursor.fetchone() == (0,)
        cursor.execute(
            "SELECT count(*) FROM pg_trigger WHERE tgname IN"
            " ('student_status_follows_events', 'status_event_sets_student_status')"
        )
        assert cursor.fetchone() == (0,)


def test_guardian_links_of_one_pair_cannot_overlap(schools):
    a, _ = schools
    guardian, other = make_account("g1@example.com"), make_account("g2@example.com")
    with school_scope(a.pk):
        mother, aunt = make_membership(a, guardian), make_membership(a, other)
        child, sibling = make_student(a), make_student(a, "Sibling")

    def link(membership, student, start, end=None):
        return GuardianLink.objects.create(
            school=a,
            membership=membership,
            student=student,
            relation="mother",
            valid_from=start,
            valid_to=end,
        )

    with school_scope(a.pk):
        link(mother, child, D(2025, 9, 1), D(2026, 6, 30))
        link(mother, child, D(2026, 7, 1))  # ended, then linked again
        link(aunt, child, D(2025, 9, 1))  # another Guardian of the same student
        link(mother, sibling, D(2025, 9, 1))  # the same Guardian of another student
    for start, end in (
        (D(2026, 6, 30), D(2026, 6, 30)),
        (D(2027, 1, 1), None),
        (D(2025, 1, 1), None),
    ):
        with pytest.raises(IntegrityError, match="guardianlink_no_overlapping_periods"):
            with school_scope(a.pk):
                link(mother, child, start, end)
    with pytest.raises(IntegrityError, match="guardianlink_valid_to_after_valid_from"):
        with school_scope(a.pk):
            link(aunt, sibling, D(2026, 2, 1), D(2026, 1, 1))
