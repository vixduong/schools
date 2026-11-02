# Slice 7: Audit log and support access

Slice 7 of `docs/phase-0.md`. Standing rules: `backend/CODING_STANDARDS.md`, the Constraints sections of `docs/phase-0.md`, `docs/roles.md` (rows "Grant time-limited support access to the operator" and "Read the audit log", rule "Least data"), `docs/tech-stack.md` (Audit log).

Done when score-like edits and support grants appear in the School's log: a change to a role, a Guardian link, a student or an enrollment, an invitation's acceptance, a grant and every operator command in it each leave an entry the School admin and the principal board can read, and no one, the app included, can edit or delete an entry.

## Owner decisions (2026-11-02)

- **The operator reaches School data only through a server command**, `manage.py support_session --school <subdomain> --operator <name>`, run as the app role. It refuses to open the School unless a support grant is in force and logs the session and every command to the School's log. No operator accounts and no web sign-in for operators.
- **A support session is read only.** Every command runs in a read-only transaction; a fix is made by the School in the app, or by a reviewed migration.

## Audit log

- New app `audit`. `AuditEvent` (tenant, RLS): `at`, `actor_membership` (composite FK, null when no member acted), `actor` (`member`, `activation`, `operator:<name>`, `system`), `action`, `target_table`, `target_id`, `details` (JSON).
- **Append-only in the database.** The app role gets `SELECT` only. Entries are written by two `SECURITY DEFINER` functions owned by the migration owner: a row trigger and `audit_record(action, target_table, target_id, details)` for events that are not row writes. So the app cannot forge, edit or delete an entry with plain SQL, and RLS still applies (the owner is under FORCE RLS).
- **Row writes are logged by a trigger**, so bulk `.update()`s (deactivation, closing a year) and every future view are covered without code in views. `AFTER INSERT OR UPDATE OR DELETE` on `accounts_membership`, `accounts_roleassignment`, `accounts_invitation`, `accounts_invitationrole`, `schools_student`, `schools_studentstatusevent`, `schools_enrollment`, `schools_guardianlink` and `audit_supportgrant`. `details` for an insert is the new row; for an update only the changed columns as `{column: [old, new]}` (an update that changes nothing logs nothing); for a delete the old row. `school_id` and secrets (`code_digest`) are left out. Gradebook and score tables add the same trigger when they arrive.
- **Who acted** comes from transaction-local settings: `HasMembership` sets `app.membership_id` and `app.actor = member` once it has found the Membership; activation sets `app.actor = activation`; the support command sets `operator:<name>`. Nothing set means `system` (management commands, migrations).
- **Reads that must be logged**: retrieving one student with the full national ID (`student.view_sensitive`, promised in slice 4). Cross-class reads of scores and profiles (slice 5) are logged by those endpoints when they exist.
- `GET /api/setup/audit-events/` (`audit.read`: School admin and principal board, read only), newest first, cursor-paginated, filters `target_table`, `target_id`, `actor_membership`, `since`, `until`.
- Not logged: setup structure (years, classes, subjects, rooms) and import batches (their effects are logged row by row). The Account table is global and written only by activation and sign-in; activation shows in the log as the Membership and invitation rows it writes.

## Support grants

- `SupportGrant` (tenant, RLS, in `audit`): `granted_by`, `reason`, `starts_at` (now), `ends_at` (1 to 72 hours later), `revoked_at`, `revoked_by`. In force while `starts_at <= now < ends_at` and not revoked.
- `POST /api/setup/support-grants/` (`hours`, `reason`), list, `revoke/`; `support_access.grant` (School admin and principal board). Never edited or deleted.
- `support_session`: refuses unless the connection is the app role; looks up the School; per command, first (in its own committed transaction) checks a grant is in force and logs `support.command` with the source, then runs the command in a separate School-scoped `READ ONLY` transaction. Session start and end are logged too. A grant revoked or ended mid-session stops the next command. `--command` runs one command and exits (scripts and tests); without it an interactive console.
- **Known limit**: entries keep the values they log (a corrected national ID's old value stays in its entry), readable by the School admin and the principal board, who may see those details anyway.
- **Known limit**: anyone with shell access on the server can run other code or connect as the owner; the command is the sanctioned, logged path, not a boundary against a rogue operator. Server access itself is the operations control (slice 9).
