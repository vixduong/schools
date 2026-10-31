"""Structure rules, held by the database and exercised as the app role."""

from datetime import date

import pytest
from django.db import IntegrityError, connection

from schools.models import Grade, Level, Room, SchoolClass, SchoolYear, Subject, Term
from tenancy.rls import school_scope

from .factories import make_class, make_group

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
            "WHERE proname IN ('term_inside_school_year', 'grade_number_fits_level')"
        )
        sources = [source for (source,) in cursor.fetchall()]
    assert len(sources) == 2 and all("FOR SHARE" in source for source in sources)
