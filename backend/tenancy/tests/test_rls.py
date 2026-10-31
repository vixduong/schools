"""The checks from docs/spikes/rls-checks.sql, run against the migrated schema as the app role."""

import psycopg
import pytest
from django.conf import settings
from django.db import connection

from tenancy.rls import school_scope

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
GLOBAL_TABLES = {"tenancy_school", "django_migrations"}


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
