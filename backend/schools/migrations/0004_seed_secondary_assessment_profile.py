import datetime

from django.db import migrations

# Circular 22/2021/TT-BGDĐT, Lower and Upper Secondary (one regulation, same rules for both).
# Read from docs/research/assessment-regulations.md (branch research/assessment-regulations), which
# was OCR'd from the signed PDF: re-check every value against the PDF before production. The
# research gives the circular's signing date (20 Jul 2021) but no effective date, so 2021-09-05 is
# assumed. Circular 89/2026 amends it from 1 Dec 2026: that becomes a later version, not an edit.
SOURCE = "Circular 22/2021/TT-BGDĐT (20 Jul 2021)"
EFFECTIVE_FROM = datetime.date(2021, 9, 5)

RULES = {
    "schema": 1,
    "verified": "ocr",
    "effective_from_assumed": True,
    "scale": {"max": 10, "decimals": 1, "rounding": "half_up", "rounding_assumed": True},
    "subject_forms": ["scored", "comment_only"],
    "comment_results": ["Đạt", "Chưa đạt"],
    "regular_assessments": {
        "comment_only": 2,
        "scored_by_periods_per_year": [
            {"up_to": 35, "count": 2},
            {"up_to": 70, "count": 3},
            {"up_to": None, "count": 4},
        ],
    },
    "periodic": {"mid_term": 1, "end_term": 1},
    "weights": {"regular": 1, "mid_term": 2, "end_term": 3},
    "semester_average": "(sum(regular) + 2 * mid_term + 3 * end_term) / (count(regular) + 5)",
    "year_average": {
        "weights": {"semester_1": 1, "semester_2": 2},
        "formula": "(semester_1 + 2 * semester_2) / 3",
    },
    "learning_ratings": [
        {
            "name": "Tốt",
            "comment_subjects_not_passed_max": 0,
            "every_scored_at_least": 6.5,
            "scored_at_least": {"subjects": 6, "score": 8.0},
            "no_scored_below": None,
        },
        {
            "name": "Khá",
            "comment_subjects_not_passed_max": 0,
            "every_scored_at_least": 5.0,
            "scored_at_least": {"subjects": 6, "score": 6.5},
            "no_scored_below": None,
        },
        {
            "name": "Đạt",
            "comment_subjects_not_passed_max": 1,
            "every_scored_at_least": None,
            "scored_at_least": {"subjects": 6, "score": 5.0},
            "no_scored_below": 3.5,
        },
        {"name": "Chưa đạt", "otherwise": True},
    ],
    "rating_adjustment": (
        "If the level fell two or more steps only because of one subject, raise it one step."
    ),
}


def seed(apps, schema_editor):
    """Idempotent. Global table, so no school_scope."""
    version = apps.get_model("schools", "AssessmentProfileVersion")
    for kind in ("lower_secondary", "upper_secondary"):
        version.objects.update_or_create(
            level_kind=kind,
            effective_from=EFFECTIVE_FROM,
            defaults={"effective_to": None, "source": SOURCE, "rules": RULES},
        )


class Migration(migrations.Migration):
    """Reverse is a no-op: the table itself goes when schools.0003 is reversed."""

    dependencies = [("schools", "0003_people_and_assessment_profiles")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
