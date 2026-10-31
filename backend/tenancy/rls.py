import re
from contextlib import contextmanager

from django.conf import settings
from django.db import connection, migrations, transaction

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def set_school(school_id: int) -> None:
    """Scope the current transaction to a School. Transaction-local: gone at COMMIT/ROLLBACK."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.school_id', %s, true)", [str(school_id)])


@contextmanager
def school_scope(school_id: int):
    """Open a transaction scoped to a School (used by the middleware and by tests).

    Durable, so it refuses to nest: releasing a savepoint does not undo set_config, so a
    nested scope would leave the inner School set for the rest of the outer transaction."""
    with transaction.atomic(durable=True):
        set_school(school_id)
        yield


def enable_tenant_rls(table: str) -> migrations.RunSQL:
    """Migration operation: fail-closed RLS on a table that has a bigint `school_id` column,
    plus the app role's grants. Policy uses NULLIF so an empty GUC means no rows."""
    role = settings.APP_DB_USER
    assert _IDENT.match(table) and _IDENT.match(role), "unsafe identifier"
    match = "school_id = NULLIF(current_setting('app.school_id', true), '')::bigint"
    return migrations.RunSQL(
        sql=f"""
        ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
        CREATE POLICY tenant_isolation ON {table} USING ({match}) WITH CHECK ({match});
        GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role};
        DO $$ BEGIN
          EXECUTE format('GRANT USAGE ON SEQUENCE %s TO {role}',
                         pg_get_serial_sequence('{table}', 'id'));
        END $$;
        """,
        reverse_sql=f"""
        REVOKE ALL ON {table} FROM {role};
        DO $$ BEGIN
          EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM {role}',
                         pg_get_serial_sequence('{table}', 'id'));
        END $$;
        DROP POLICY tenant_isolation ON {table};
        ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
        """,
    )


def grant_app_role(table: str) -> migrations.RunSQL:
    """Migration operation: app-role grants for a global (non-RLS) table."""
    role = settings.APP_DB_USER
    assert _IDENT.match(table) and _IDENT.match(role), "unsafe identifier"
    return migrations.RunSQL(
        sql=f"GRANT SELECT ON {table} TO {role}",
        reverse_sql=f"REVOKE SELECT ON {table} FROM {role}",
    )
