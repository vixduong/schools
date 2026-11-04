# Writing a slice plan

A slice plan (`<phase>-slice-<n>.md`) is the worker's contract: it builds what the plan states and stops at anything the plan leaves out. Write it so the contract already carries the standing rules in `backend/CODING_STANDARDS.md`.

- **Every rule names its enforcement** beside it: a check constraint, an exclusion constraint, a trigger (cross-table), a grant, or "view only, because …". A rule the API enforces is also a database rule (CODING_STANDARDS § Invariants), so "view only" needs its reason. Keep no separate list of triggers: a worker reads such a list as complete.
- **Every table about people, roles or scores names its audit**: which writes are logged, and which free-text columns are hidden from the log (the School admin reads it; `audit/tests/test_audit_privacy.py` fails on an exposed `reason`, `note` or `*comment`).
- **Dates that mean "today"** are the School's day (`Asia/Ho_Chi_Minh`), never the database session's (UTC).
- **Name what the slice leaves out** in a closing section, so the worker reports a gap instead of filling it.
