"""After the first production data, a migration never empties a table: schema changes go
expand/contract, with per-School data migrations inside `school_scope` (docs/phase-0.md). Only
the migrations below, written while the data was still disposable dev rows, may do it."""

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
DESTRUCTIVE = re.compile(r"\bTRUNCATE\b|\bDELETE\s+FROM\b", re.IGNORECASE)
PRE_PRODUCTION = {"accounts/migrations/0005_role_assignment_scope.py"}

MIGRATIONS = sorted(p for p in BACKEND.glob("*/migrations/0*.py") if ".venv" not in p.parts)


def test_migrations_are_found():
    assert len(MIGRATIONS) >= 8
    assert PRE_PRODUCTION <= {str(p.relative_to(BACKEND)) for p in MIGRATIONS}


@pytest.mark.parametrize("path", MIGRATIONS, ids=lambda p: f"{p.parent.parent.name}.{p.stem}")
def test_migration_never_truncates_or_bulk_deletes(path):
    relative = str(path.relative_to(BACKEND))
    if relative in PRE_PRODUCTION:
        pytest.skip("allowlisted: pre-production")
    assert not DESTRUCTIVE.search(path.read_text()), f"{relative} empties a table"


def test_the_guard_catches_destructive_sql():
    assert DESTRUCTIVE.search('migrations.RunSQL("truncate accounts_roleassignment")')
    assert DESTRUCTIVE.search("RunSQL('DELETE  FROM t')")
    assert not DESTRUCTIVE.search("RunSQL('UPDATE t SET a = 1')")
