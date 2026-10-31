"""The checks from docs/spikes/rls-checks.sql, run against the migrated schema as the app role."""

import psycopg
import pytest
from django.apps import apps
from django.conf import settings
from django.db import IntegrityError, connection, transaction

from tenancy.rls import composite_fk, school_scope

COUNT = "SELECT count(*) FROM tenancy_probe"


def scope(conn, school):
    conn.execute("SELECT set_config('app.school_id', %s, true)", [str(school.pk)])


def test_no_school_set_sees_no_rows(app_conn):
    assert app_conn.execute(COUNT).fetchone()[0] == 0


def test_empty_setting_sees_no_rows_without_error(app_conn):
    app_conn.execute("SELECT set_config('app.school_id', '', false)")
    assert app_conn.execute(COUNT).fetchone()[0] == 0


def test_school_sees_only_its_rows(app_conn, schools):
    a, b = schools
    with app_conn.transaction():
        scope(app_conn, a)
        names = [r[0] for r in app_conn.execute("SELECT name FROM tenancy_probe ORDER BY name")]
    assert names == ["a1", "a2"]
    with app_conn.transaction():
        scope(app_conn, b)
        assert app_conn.execute(COUNT).fetchone()[0] == 1


def test_insert_for_other_school_is_refused(app_conn, schools):
    a, b = schools
    with pytest.raises(psycopg.errors.InsufficientPrivilege), app_conn.transaction():
        scope(app_conn, a)
        app_conn.execute("INSERT INTO tenancy_probe (school_id, name) VALUES (%s, 'x')", [b.pk])


def test_setting_is_gone_after_commit(app_conn, schools):
    with app_conn.transaction():
        scope(app_conn, schools[0])
        assert app_conn.execute(COUNT).fetchone()[0] == 2
    assert app_conn.execute(COUNT).fetchone()[0] == 0


def test_setting_is_gone_after_rollback(app_conn, schools):
    with app_conn.transaction():
        scope(app_conn, schools[1])
        raise psycopg.Rollback
    assert app_conn.execute(COUNT).fetchone()[0] == 0


def test_update_across_schools_touches_no_rows(app_conn, schools):
    with app_conn.transaction():
        scope(app_conn, schools[1])
        cur = app_conn.execute("UPDATE tenancy_probe SET name = 'hacked' WHERE name = 'a1'")
        assert cur.rowcount == 0


def test_every_table_with_school_id_has_forced_rls_and_policy(db):
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                   (SELECT string_agg(p.qual || ' ' || coalesce(p.with_check, ''), ' ')
                      FROM pg_policies p
                     WHERE p.schemaname = n.nspname AND p.tablename = c.relname)
              FROM pg_attribute a
              JOIN pg_class c ON c.oid = a.attrelid AND c.relkind = 'r'
              JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
             WHERE a.attname = 'school_id' AND NOT a.attisdropped
            """
        )
        tables = cur.fetchall()
    assert "tenancy_probe" in [t[0] for t in tables]
    for name, enabled, forced, policy in tables:
        assert enabled, f"{name}: RLS not enabled"
        assert forced, f"{name}: RLS not forced"
        assert policy and "nullif" in policy.lower(), f"{name}: no fail-closed policy"


def test_nested_school_scope_is_refused(schools):
    a, b = schools
    with school_scope(b.pk):
        with pytest.raises(RuntimeError):
            with school_scope(a.pk):
                pass


def test_delete_across_schools_touches_no_rows(app_conn, schools):
    with app_conn.transaction():
        scope(app_conn, schools[1])
        assert app_conn.execute("DELETE FROM tenancy_probe WHERE name = 'a1'").rowcount == 0


# Global tables the app role may touch without RLS. Anything else it can read or write must
# be a tenant table with forced RLS and exactly the one fail-closed policy.
GLOBAL_TABLES = {
    "tenancy_school",
    "django_migrations",
    "accounts_account",
    "django_session",
}


def test_app_role_reaches_only_global_or_rls_tables(db):
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname, c.relkind, c.relrowsecurity, c.relforcerowsecurity,
                   (SELECT array_agg(p.policyname) FROM pg_policies p
                     WHERE p.schemaname = n.nspname AND p.tablename = c.relname)
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
               AND has_table_privilege(%s, c.oid, 'SELECT, INSERT, UPDATE, DELETE')
            """,
            [settings.APP_DB_USER],
        )
        rows = cur.fetchall()
    assert "tenancy_probe" in [r[0] for r in rows]
    for name, kind, enabled, forced, policies in rows:
        if name in GLOBAL_TABLES:
            continue
        assert kind == "r", f"{name}: app role reaches a {kind!r} relation RLS cannot guard"
        assert enabled and forced, f"{name}: reachable by the app role without forced RLS"
        assert policies == ["tenant_isolation"], f"{name}: expected one policy, got {policies}"


def test_app_role_cannot_create_delete_or_edit_accounts(app_conn):
    """Column grants on accounts_account: sign-in updates password and last_login, nothing else."""
    for sql in (
        "INSERT INTO accounts_account (password, display_name, email, is_active)"
        " VALUES ('x', 'x', 'x@example.com', true)",
        "UPDATE accounts_account SET email = 'x@example.com' WHERE false",
        "UPDATE accounts_account SET is_active = true WHERE false",
        "DELETE FROM accounts_account WHERE false",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app_conn.execute(sql)
    app_conn.execute(
        "UPDATE accounts_account SET password = password, last_login = now() WHERE false"
    )
    app_conn.execute("SELECT id, email FROM accounts_account LIMIT 1")


# Two tables that both carry school_id must be linked by an FK that includes school_id.
SINGLE_COLUMN_SCHOOL_FKS = """
    SELECT con.conname FROM pg_constraint con
      JOIN pg_attribute child ON child.attrelid = con.conrelid
                             AND child.attname = 'school_id' AND NOT child.attisdropped
      JOIN pg_attribute parent ON parent.attrelid = con.confrelid
                              AND parent.attname = 'school_id' AND NOT parent.attisdropped
     WHERE con.contype = 'f' AND con.connamespace = 'public'::regnamespace
       AND NOT child.attnum = ANY (con.conkey)
"""


def test_tenant_foreign_keys_include_school_id(db):
    with connection.cursor() as cur:
        cur.execute(SINGLE_COLUMN_SCHOOL_FKS)
        assert cur.fetchall() == []


def test_composite_fk_blocks_cross_school_references_and_the_check_catches_single_column(db):
    with connection.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE t_parent (id bigserial PRIMARY KEY, school_id bigint NOT NULL,
                                   UNIQUE (school_id, id));
            CREATE TABLE t_child (id bigserial PRIMARY KEY, school_id bigint NOT NULL,
                                  parent_id bigint NOT NULL);
            INSERT INTO t_parent (id, school_id) VALUES (1, 1);
            ALTER TABLE t_child ADD CONSTRAINT t_child_single FOREIGN KEY (parent_id)
              REFERENCES t_parent (id);
            """
        )
        cur.execute(SINGLE_COLUMN_SCHOOL_FKS)
        assert cur.fetchall() == [("t_child_single",)]
        cur.execute("ALTER TABLE t_child DROP CONSTRAINT t_child_single")
        cur.execute(composite_fk("t_child", "parent_id", "t_parent").sql)
        cur.execute(SINGLE_COLUMN_SCHOOL_FKS)
        assert cur.fetchall() == []
        cur.execute("INSERT INTO t_child (school_id, parent_id) VALUES (1, 1)")
        with pytest.raises(IntegrityError, match="t_child_parent_id_same_school"):
            with transaction.atomic():
                cur.execute("INSERT INTO t_child (school_id, parent_id) VALUES (2, 1)")
        cur.execute(composite_fk("t_child", "parent_id", "t_parent").reverse_sql)


def test_every_tenant_foreign_key_declared_without_a_db_constraint_has_a_composite_one(db):
    """A model FK with db_constraint=False must be backed by `FOREIGN KEY (school_id, x_id)
    REFERENCES target (school_id, id)`; forgetting `composite_fk` leaves it unconstrained."""
    fields = [
        f
        for model in apps.get_models()
        for f in model._meta.get_fields()
        if f.many_to_one and f.concrete and not f.db_constraint
    ]
    assert len(fields) >= 10, "the models should declare many composite foreign keys"
    with connection.cursor() as cur:
        cur.execute(
            "SELECT conrelid::regclass::text, pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE contype = 'f' AND connamespace = 'public'::regnamespace"
        )
        definitions = cur.fetchall()
    for f in fields:
        table, target = f.model._meta.db_table, f.related_model._meta.db_table
        expected = f"FOREIGN KEY (school_id, {f.attname}) REFERENCES {target}(school_id, id)"
        assert (table, expected) in definitions, f"{table}.{f.attname}: no composite FK"
