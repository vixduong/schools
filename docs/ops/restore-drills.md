# Restore drills

One line per drill (`make restore-drill` prints it), once per term from the first production School (`docs/tech-stack.md` § Backups). Record where the dump came from and anything that failed.

- 2026-11-02 restore drill OK: schools-20261102T161105Z.dump, 29 tables, 223 rows, RLS on 20 tenant tables. Local dev database, first run of the scripts (slice 9); a tampered manifest and a table with RLS turned off were both caught.
