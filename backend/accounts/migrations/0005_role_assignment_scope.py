import django.contrib.postgres.constraints
import django.contrib.postgres.fields.ranges
import django.db.models.deletion
import django.db.models.expressions
import django.db.models.functions.comparison
from django.db import migrations, models

from tenancy.rls import composite_fk


def scope_fk(to):
    return models.ForeignKey(
        blank=True,
        null=True,
        db_constraint=False,
        on_delete=django.db.models.deletion.PROTECT,
        to=to,
    )


def role_scope(role, *scoped):
    q = models.Q(role=role)
    for column in ("subject_group", "school_class", "subject"):
        q &= models.Q(**{f"{column}__isnull": column not in scoped})
    return q


class Migration(migrations.Migration):
    """Slice 4a: typed scope on RoleAssignment and the Ministry staff ID on Membership.

    RoleAssignment drops `scope_kind`, `scope_id` and the text `school_year`, so its rows cannot
    be carried over: this migration EMPTIES the table (dev data only; TRUNCATE because FORCE RLS
    hides every row from DELETE). Reversing it empties the table again."""

    dependencies = [
        ("accounts", "0004_vn_mobile_phone"),
        ("schools", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL("TRUNCATE accounts_roleassignment", migrations.RunSQL.noop),
        migrations.RemoveConstraint(
            model_name="roleassignment", name="roleassignment_unique_per_scope_and_year"
        ),
        migrations.RemoveConstraint(
            model_name="roleassignment", name="roleassignment_scope_kind_and_id_together"
        ),
        migrations.RemoveField(model_name="roleassignment", name="scope_kind"),
        migrations.RemoveField(model_name="roleassignment", name="scope_id"),
        migrations.RemoveField(model_name="roleassignment", name="school_year"),
        migrations.AddField(
            model_name="roleassignment",
            name="school_year",
            field=models.ForeignKey(
                db_constraint=False,
                on_delete=django.db.models.deletion.PROTECT,
                to="schools.schoolyear",
            ),
        ),
        migrations.AddField(
            model_name="roleassignment", name="subject_group", field=scope_fk("schools.subjectgroup")
        ),
        migrations.AddField(
            model_name="roleassignment", name="school_class", field=scope_fk("schools.schoolclass")
        ),
        migrations.AddField(
            model_name="roleassignment", name="subject", field=scope_fk("schools.subject")
        ),
        migrations.AddConstraint(
            model_name="roleassignment",
            constraint=models.CheckConstraint(
                condition=role_scope("school_admin")
                | role_scope("principal_board")
                | role_scope("group_leader", "subject_group")
                | role_scope("homeroom_teacher", "school_class")
                | role_scope("subject_teacher", "subject", "school_class"),
                name="roleassignment_scope_matches_role",
            ),
        ),
        migrations.AddConstraint(
            model_name="roleassignment",
            constraint=django.contrib.postgres.constraints.ExclusionConstraint(
                name="roleassignment_no_overlapping_periods",
                expressions=[
                    ("school", "="),
                    ("membership", "="),
                    ("role", "="),
                    (
                        django.db.models.functions.comparison.Coalesce(
                            "subject_group", django.db.models.expressions.Value(0)
                        ),
                        "=",
                    ),
                    (
                        django.db.models.functions.comparison.Coalesce(
                            "school_class", django.db.models.expressions.Value(0)
                        ),
                        "=",
                    ),
                    (
                        django.db.models.functions.comparison.Coalesce(
                            "subject", django.db.models.expressions.Value(0)
                        ),
                        "=",
                    ),
                    (
                        django.db.models.expressions.Func(
                            "valid_from",
                            "valid_to",
                            django.db.models.expressions.Value("[]"),
                            function="daterange",
                            output_field=django.contrib.postgres.fields.ranges.DateRangeField(),
                        ),
                        "&&",
                    ),
                ],
            ),
        ),
        composite_fk("accounts_roleassignment", "school_year_id", "schools_schoolyear"),
        composite_fk("accounts_roleassignment", "subject_group_id", "schools_subjectgroup"),
        composite_fk("accounts_roleassignment", "school_class_id", "schools_schoolclass"),
        composite_fk("accounts_roleassignment", "subject_id", "schools_subject"),
        migrations.AddField(
            model_name="membership",
            name="ministry_staff_id",
            field=models.CharField(blank=True, max_length=30, null=True),
        ),
        migrations.AddConstraint(
            model_name="membership",
            constraint=models.UniqueConstraint(
                fields=("school", "ministry_staff_id"), name="membership_ministry_staff_id_key"
            ),
        ),
        migrations.RunSQL(migrations.RunSQL.noop, "TRUNCATE accounts_roleassignment"),
    ]
