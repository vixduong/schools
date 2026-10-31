"""AssessmentProfileVersion: a global table the app role can only read, seeded by migration."""

import decimal
import importlib
from datetime import date

import pytest
from django.apps import apps
from django.db import IntegrityError, ProgrammingError, connection, transaction

from schools.models import AssessmentProfileVersion

D = date
seed_migration = importlib.import_module(
    "schools.migrations.0004_seed_secondary_assessment_profile"
)
start_migration = importlib.import_module("schools.migrations.0007_secondary_profile_from_2024")
KINDS = ("lower_secondary", "upper_secondary")


FUTURE = D(2030, 1, 1)


def version(kind="primary", start=FUTURE, end=None):
    return AssessmentProfileVersion.objects.create(
        level_kind=kind, effective_from=start, effective_to=end, source="test", rules={"schema": 1}
    )


@pytest.fixture
def seeded(db):
    """The rows the migrations seed, rebuilt by running their data steps: transactional tests
    flush the table (and `--reuse-db` keeps it flushed), so the rows cannot be assumed to be
    there. Rolled back with the test."""
    AssessmentProfileVersion.objects.all().delete()
    seed_migration.seed(apps, None)
    start_migration.apply(apps, None)


def test_lower_and_upper_secondary_are_seeded_from_circular_22_2021(seeded):
    versions = AssessmentProfileVersion.objects.order_by("level_kind")
    assert [v.level_kind for v in versions] == list(KINDS)
    for v in versions:
        assert (v.effective_from, v.effective_to) == (D(2024, 9, 5), None)
        assert "Circular 22/2021" in v.source
        rules = v.rules
        assert (rules["verified"], rules["effective_from_assumed"]) == ("ocr", True)
        assert rules["weights"] == {"regular": 1, "mid_term": 2, "end_term": 3}
        assert rules["scale"] == {
            "max": 10,
            "decimals": 1,
            "rounding": "half_up",
            "rounding_assumed": True,
        }
        bands = rules["regular_assessments"]["scored_by_periods_per_year"]
        assert [(b["up_to"], b["count"]) for b in bands] == [(35, 2), (70, 3), (None, 4)]
        assert rules["year_average"]["weights"] == {"semester_1": 1, "semester_2": 2}
        ratings = {r["name"]: r for r in rules["learning_ratings"]}
        assert list(ratings) == ["Tốt", "Khá", "Đạt", "Chưa đạt"]
        assert ratings["Tốt"]["every_scored_at_least"] == 6.5
        assert ratings["Tốt"]["scored_at_least"] == {"subjects": 6, "score": 8.0}
        assert ratings["Khá"]["scored_at_least"] == {"subjects": 6, "score": 6.5}
        assert ratings["Đạt"]["no_scored_below"] == 3.5
        assert ratings["Đạt"]["comment_subjects_not_passed_max"] == 1
        assert rules["year_average_uses_rounded_semester_averages"] is True
        assert getattr(decimal, rules["rounding"]) == decimal.ROUND_HALF_UP
        assert len(rules["not_modelled"]) == 2


def test_a_school_year_before_the_first_version_finds_none(seeded):
    """Circular 22/2021 applies to every grade from 2024-09-05: earlier dates fail closed."""
    for kind in KINDS:
        found = AssessmentProfileVersion.objects.filter(
            level_kind=kind, effective_from__lte=D(2024, 9, 4)
        )
        assert not found.exists()


def test_the_2024_start_is_applied_once_and_can_be_reverted(seeded):
    def rows():
        return list(
            AssessmentProfileVersion.objects.order_by("level_kind").values_list(
                "level_kind", "effective_from", "rules"
            )
        )

    applied = rows()
    start_migration.apply(apps, None)  # nothing left to update
    assert rows() == applied
    start_migration.revert(apps, None)
    assert {effective_from for _, effective_from, _ in rows()} == {D(2021, 9, 5)}
    assert all("rounding" not in rules for _, _, rules in rows())
    start_migration.apply(apps, None)
    assert rows() == applied


def test_versions_of_one_level_kind_cannot_overlap(seeded):
    version(start=D(2030, 1, 1), end=D(2030, 12, 31))
    version(start=D(2031, 1, 1))  # adjacent
    version("preschool", D(2030, 6, 1))  # another kind
    for start, end in ((D(2030, 12, 31), D(2031, 1, 1)), (D(2029, 1, 1), D(2030, 1, 1))):
        with (
            pytest.raises(IntegrityError, match="assessmentprofileversion_no_overlap"),
            transaction.atomic(),
        ):
            version(start=start, end=end)
    # The seeded Lower Secondary version is open-ended: nothing may start after it unless it ends.
    with (
        pytest.raises(IntegrityError, match="assessmentprofileversion_no_overlap"),
        transaction.atomic(),
    ):
        version("lower_secondary", D(2030, 1, 1))


@pytest.mark.django_db
def test_a_version_cannot_end_before_it_starts():
    with pytest.raises(IntegrityError, match="assessmentprofileversion_ends_after_start"):
        with transaction.atomic():
            version(start=D(2030, 1, 2), end=D(2030, 1, 1))


@pytest.mark.usefixtures("as_app_role")
def test_the_app_role_can_only_read_them(schools):
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM schools_assessmentprofileversion")
        for sql in (
            "INSERT INTO schools_assessmentprofileversion"
            " (level_kind, effective_from, source, rules) VALUES ('primary', now(), 'x', '{}')",
            "UPDATE schools_assessmentprofileversion SET source = 'x'",
            "DELETE FROM schools_assessmentprofileversion",
        ):
            with pytest.raises(ProgrammingError, match="permission denied"):
                cursor.execute(sql)
