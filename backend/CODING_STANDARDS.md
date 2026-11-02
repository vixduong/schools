# Backend coding standards (for review)

Read during review, not implementation. Each rule is a judgement call that no automated check covers; the mechanical ones already run as tests (open views, composite FKs, RLS coverage, migration safety, the roles matrix vs `docs/roles.md`). Rules came from the slice 1–5 reviews; `docs/phase-0.md` and `docs/slices/` hold the reasons.

## Tenancy

- **Every School-owned row is reached under RLS.** A new table carries `school_id`, `enable_tenant_rls`, and composite FKs via `composite_fk`; a global table is added to `GLOBAL_TABLES` with the narrowest grant (column-level `UPDATE` when only some columns change).
- **Work outside a request scopes itself.** Tasks, management commands and data migrations enter `school_scope(school_id)` per School; nothing streams DB rows after the response; `school_scope` is never nested.
- **Grants are as narrow as the API.** When the API changes only some columns of a table, the app role gets column-level `UPDATE` on those; a limit the API enforces (a window, a range) is also a check constraint.
- **A School never writes another person's Account.** Views reach `Account` through `Membership`; credentials and identifiers change only through the person's own flows or invites.

## History

- **Periods move forward only.** `valid_from` is immutable; `valid_to` is set while it is NULL or in the future, never earlier than `valid_from`, never cleared (the one exception: cancelling a scheduled leave before its day). Corrections are "end and create".
- **Facts with a date are append-only.** Status changes are events; derived state (a student's status) is computed as of a date, not stored.
- **Immutable fields answer 400 `immutable`** when a different value is sent; the same value is accepted.
- **No hard deletes** of School data; end or deactivate. Migrations never TRUNCATE or bulk-delete after the first production data; schema changes go expand/contract.

## Audit

- **A new table about people, roles or scores gets the audit trigger** (`AUDITED` in `audit/migrations/0001_initial.py` shows the pattern: `CREATE TRIGGER audit_row_change ...`), with secrets passed as hidden columns. Reads of sensitive details call `audit.log.record`.
- **Nothing writes `audit_auditevent` directly**; the app role cannot. A view that acts for someone other than the signed-in member calls `set_actor` first.

## Invariants

- **The database holds cross-table rules.** A rule spanning two tables (term inside its year, enrollment inside its year, membership kinds) is a trigger that locks the parent row (`FOR SHARE`, or `FOR NO KEY UPDATE` on the side that must conflict); a serializer check alone is UX, not protection. Concurrent writers that count rows (last School admin) lock the counted rows in a fixed order.
- **Constraint names are API.** DB violations map to 400 `{"constraint": [<name>]}`; renaming a constraint is a breaking change.

## Permissions

- **Every check goes through the engine.** `can()`, `visible_students/classes/pairs()` and `Can(...)`; no hand-rolled role checks in views or serializers.
- **List helpers agree with `can()`.** A queryset that lists targets uses the matching `visible_*` helper with the same action, `read` and `released` arguments as the per-object check.
- **Per-student data goes through per-student actions** (`scores.view`, `attendance.view`, `student_profile.view_sensitive`) on a Student, pair or class target; `class_records.view` covers class-level content only.
- **`read=True` gates reads.** It never opens a write; the single precedent is `confirm` (`read_on_writes=True`).
- **Authorise as of today.** `Actor(..., on=past)` is for as-of reads only; writes authorise with today.
- **Targets come from stored objects**, not from raw `request.data`.

## Tests

- **Every new rule has a test that goes red without it.** For a guard or constraint, show it in the review notes: `make red FILE=... OLD=... NEW=... K=...` swaps the guard out, runs the matching tests and restores the file.
- **Requests are tested as the app role** (`as_app_role`); data set-up that needs the owner uses the owner helpers.
