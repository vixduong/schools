from django.db import migrations

from tenancy.rls import grant_app_role

# The worker (django-tasks-db) runs as the app role: it claims and finishes a task (UPDATE) and the
# send view enqueues one (INSERT). No DELETE, so task rows are not pruned (a known limit). The
# table has no school_id, so it is a global table (tenancy/tests/test_rls.py), and a task row
# carries ids only. Its primary key is a UUID: no sequence to grant.
class Migration(migrations.Migration):

    dependencies = [
        ("notices", "0002_recipient_guards"),
        ("django_tasks_database", "0021_conditional_partial_index_ordering"),
    ]

    operations = [
        grant_app_role(
            "django_tasks_database_dbtaskresult", privileges=("SELECT", "INSERT", "UPDATE")
        ),
    ]
