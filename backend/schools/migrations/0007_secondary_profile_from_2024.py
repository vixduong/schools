import datetime

from django.db import migrations

# Circular 22/2021 reached every Lower and Upper Secondary grade only from the 2024-2025 school
# year, so the seeded versions (schools.0004) start on 2024-09-05 (still assumed, as the research
# had no effective date): an earlier school year finds no version and fails closed. The rows are
# updated in place; `apply` and `revert` are idempotent.
KINDS = ("lower_secondary", "upper_secondary")
FIRST_SEEDED = datetime.date(2021, 9, 5)
EFFECTIVE_FROM = datetime.date(2024, 9, 5)
ADDED = {
    "year_average_uses_rounded_semester_averages": True,
    "rounding": "ROUND_HALF_UP",  # a decimal.Decimal rounding mode
    "not_modelled": [
        "Upper Secondary topic clusters (cụm chuyên đề học tập)",
        "periods per year of each subject (the count of regular assessments follows it)",
    ],
}


def apply(apps, schema_editor):
    """Global table, so no school_scope."""
    version = apps.get_model("schools", "AssessmentProfileVersion")
    for row in version.objects.filter(level_kind__in=KINDS, effective_from=FIRST_SEEDED):
        row.effective_from = EFFECTIVE_FROM
        row.rules = {**row.rules, **ADDED}
        row.save(update_fields=["effective_from", "rules"])


def revert(apps, schema_editor):
    version = apps.get_model("schools", "AssessmentProfileVersion")
    for row in version.objects.filter(level_kind__in=KINDS, effective_from=EFFECTIVE_FROM):
        row.effective_from = FIRST_SEEDED
        row.rules = {k: v for k, v in row.rules.items() if k not in ADDED}
        row.save(update_fields=["effective_from", "rules"])


class Migration(migrations.Migration):
    dependencies = [("schools", "0006_student_status_derived_from_events")]

    operations = [migrations.RunPython(apply, revert)]
