#!/bin/sh
# Restore a dump into a scratch database and prove it usable (docs/slices/slice-9.md): row counts
# match the backup's manifest, every tenant table still forces RLS with the tenant_isolation
# policy, and the app role can still read every table. The scratch database is dropped after.
# Usage: restore-drill.sh <file.dump> (its .manifest beside it). Same libpq environment as
# backup.sh, on a cluster where the owner and app roles exist; DB_APP_USER names the app role.
set -eu
dump=${1:?usage: restore-drill.sh <file.dump>}
manifest=${dump%.dump}.manifest
: "${PGDATABASE:?set PGDATABASE}" "${DB_APP_USER:?set DB_APP_USER}"
scratch="${PGDATABASE}_drill_$$"
createdb "$scratch"
trap 'dropdb --if-exists "$scratch"' EXIT
pg_restore --exit-on-error -d "$scratch" "$dump"

q() { psql -X -q -At -v ON_ERROR_STOP=1 -d "$scratch" -c "$1"; }
fail=0
tables=0
rows=0
while read -r table expected; do
  actual=$(q "SELECT count(*) FROM public.\"$table\"")
  tables=$((tables + 1))
  rows=$((rows + actual))
  if [ "$actual" != "$expected" ]; then
    echo "MISMATCH $table: backup had $expected rows, restore has $actual"
    fail=1
  fi
done < "$manifest"

tenant="FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE c.relkind = 'r' AND n.nspname = 'public'
   AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'school_id')"
unguarded=$(q "SELECT string_agg(c.relname, ', ') $tenant AND NOT (c.relrowsecurity AND c.relforcerowsecurity
  AND EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid AND p.polname = 'tenant_isolation'))")
if [ -n "$unguarded" ]; then echo "RLS MISSING: $unguarded"; fail=1; fi
unreadable=$(q "SELECT string_agg(c.relname, ', ') $tenant AND NOT has_table_privilege('$DB_APP_USER', c.oid, 'SELECT')")
if [ -n "$unreadable" ]; then echo "APP ROLE CANNOT READ: $unreadable"; fail=1; fi
guarded=$(q "SELECT count(*) $tenant")

if [ "$fail" -ne 0 ]; then
  echo "$(date -u +%Y-%m-%d) restore drill FAILED: $(basename "$dump")"
  exit 1
fi
echo "$(date -u +%Y-%m-%d) restore drill OK: $(basename "$dump"), $tables tables, $rows rows, RLS on $guarded tenant tables"
