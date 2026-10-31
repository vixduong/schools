from django.conf import settings
from django.db import migrations

from tenancy.rls import grant_app_role

ROLE = settings.APP_DB_USER


class Migration(migrations.Migration):
    """The app role only signs people in: it reads Accounts and updates password (hash upgrades)
    and last_login. Creating or editing an Account, or deleting one, needs the owner role."""

    dependencies = [("accounts", "0002_app_role_grants")]

    operations = [
        migrations.RunSQL(
            sql=f"""
            REVOKE INSERT, UPDATE, DELETE ON accounts_account FROM {ROLE};
            DO $$ BEGIN
              EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM {ROLE}',
                             pg_get_serial_sequence('accounts_account', 'id'));
            END $$;
            """,
            reverse_sql=f"""
            GRANT INSERT, UPDATE, DELETE ON accounts_account TO {ROLE};
            DO $$ BEGIN
              EXECUTE format('GRANT USAGE ON SEQUENCE %s TO {ROLE}',
                             pg_get_serial_sequence('accounts_account', 'id'));
            END $$;
            """,
        ),
        grant_app_role("accounts_account", (), update_columns=("password", "last_login")),
    ]
