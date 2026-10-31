from django.db import migrations

from tenancy.rls import grant_app_role

WRITE = ("SELECT", "INSERT", "UPDATE", "DELETE")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("sessions", "0001_initial"),
    ]

    operations = [
        # Global tables the app role writes: login reads and updates Accounts, sessions are
        # saved on every request. Both go on GLOBAL_TABLES in tenancy/tests/test_rls.py.
        grant_app_role("accounts_account", WRITE, sequence=True),
        grant_app_role("django_session", WRITE),
    ]
