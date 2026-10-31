"""Structure rows for tests. Call inside `school_scope(school.pk)`."""

from datetime import timedelta

from django.utils import timezone

from schools.models import Grade, Level, SchoolClass, SchoolYear, Subject, SubjectGroup


def make_year(school, name="current"):
    """A school year that contains today, so role assignments in it are in force."""
    today = timezone.localdate()
    return SchoolYear.objects.get_or_create(
        school=school,
        name=name,
        defaults={"starts_on": today - timedelta(days=30), "ends_on": today + timedelta(days=300)},
    )[0]


def make_class(school, year=None, name="7A"):
    level = Level.objects.get_or_create(school=school, kind=Level.Kind.LOWER_SECONDARY)[0]
    grade = Grade.objects.get_or_create(school=school, number=7, defaults={"level": level})[0]
    return SchoolClass.objects.get_or_create(
        school=school,
        school_year=year or make_year(school),
        name=name,
        defaults={"grade": grade},
    )[0]


def make_group(school, name="Toán"):
    return SubjectGroup.objects.get_or_create(school=school, name=name)[0]


def make_subject(school, code="MATH", group=None):
    return Subject.objects.get_or_create(
        school=school, code=code, defaults={"name": code, "subject_group": group}
    )[0]
