#!/bin/sh
# Back up the database: a custom-format dump plus a manifest of row counts, both read from one
# snapshot so the restore drill can prove the restore complete (docs/slices/slice-9.md).
# Usage: backup.sh <dir>. Connection from the libpq environment (PGHOST, PGUSER, PGDATABASE...).
# PGUSER must bypass RLS (a superuser, or the provider's admin role): the table owner is under
# FORCE ROW LEVEL SECURITY and would dump empty tenant tables.
set -eu
dir=${1:?usage: backup.sh <dir>}
: "${PGDATABASE:?set PGDATABASE}"
mkdir -p "$dir"
base="$dir/$PGDATABASE-$(date -u +%Y%m%dT%H%M%SZ)"
export DUMP="$base.dump"
psql -X -q -At -v ON_ERROR_STOP=1 <<SQL
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT pg_export_snapshot() AS snapshot \gset
\setenv SNAPSHOT :snapshot
\o $base.manifest
SELECT format('SELECT %L || '' '' || count(*) FROM public.%I', c.relname, c.relname)
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relkind = 'r' AND n.nspname = 'public' ORDER BY c.relname \gexec
\o
\! pg_dump -Fc --snapshot="\$SNAPSHOT" -f "\$DUMP" || rm -f "\$DUMP"
COMMIT;
SQL
# psql does not fail on a failed \! command: a missing or empty dump is the failure.
if [ ! -s "$DUMP" ]; then
  echo "backup FAILED: pg_dump did not write $DUMP" >&2
  rm -f "$DUMP" "$base.manifest"
  exit 1
fi
echo "$DUMP"
