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


_PRIVILEGES = {"SELECT", "INSERT", "UPDATE", "DELETE"}


def grant_app_role(
    table: str,
    privileges: tuple[str, ...] = ("SELECT",),
    sequence: bool = False,
    update_columns: tuple[str, ...] = (),
) -> migrations.RunSQL:
    """Migration operation: app-role grants for a global (non-RLS) table. `sequence=True` also
    grants the app role the table's `id` sequence (needed to INSERT into a table with an `id`).
    `update_columns` grants UPDATE on those columns only (instead of "UPDATE" in `privileges`)."""
    role = settings.APP_DB_USER
    assert _IDENT.match(table) and _IDENT.match(role), "unsafe identifier"
    assert set(privileges) <= _PRIVILEGES, "unsafe privileges"
    assert privileges or update_columns, "nothing to grant"
    assert all(_IDENT.match(c) for c in update_columns), "unsafe identifier"
    assert not (update_columns and "UPDATE" in privileges), "UPDATE is table-wide already"
    columns = [f"UPDATE ({', '.join(update_columns)})"] if update_columns else []
    grants = ", ".join([*privileges, *columns])
    seq = f"pg_get_serial_sequence('{table}', 'id')"
    grant_seq = revoke_seq = ""
    if sequence:
        run = f"DO $$ BEGIN EXECUTE format('%s ON SEQUENCE %%s %s {role}', {seq}); END $$;"
        grant_seq = run % ("GRANT USAGE", "TO")
        revoke_seq = run % ("REVOKE ALL", "FROM")
    return migrations.RunSQL(
        sql=f"GRANT {grants} ON {table} TO {role}; {grant_seq}",
        reverse_sql=f"{revoke_seq} REVOKE {grants} ON {table} FROM {role};",
    )


def composite_fk(
    table: str, column: str, ref_table: str, ref_column: str = "id"
) -> migrations.RunSQL:
    """Migration operation: FOREIGN KEY (school_id, column) -> ref_table (school_id, ref_column),
    so a tenant row can only point at a row of its own School. The target needs a unique
    constraint on (school_id, ref_column). Declare the model field with `db_constraint=False`."""
    names = (table, column, ref_table, ref_column)
    assert all(_IDENT.match(n) for n in names), "unsafe identifier"
    name = f"{table}_{column}_same_school"
    assert len(name) <= 63, "constraint name too long"
    return migrations.RunSQL(
        sql=f"ALTER TABLE {table} ADD CONSTRAINT {name} "
        f"FOREIGN KEY (school_id, {column}) REFERENCES {ref_table} (school_id, {ref_column})",
        reverse_sql=f"ALTER TABLE {table} DROP CONSTRAINT {name}",
    )
