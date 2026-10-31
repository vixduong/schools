# Slice 6: Invitations and Excel import

Slice 6 of `docs/phase-0.md`, in two halves. Standing rules: `backend/CODING_STANDARDS.md`, the Constraints sections of `docs/phase-0.md`, the decisions in `docs/slices/slice-4.md` and `slice-5.md`, and `docs/roles.md`.

The shaping constraint: **a School never creates or edits a person's Account** (ADR 0002, slice 3 review). People join a School by **invitation**: the School says who is expected and in what capacity; the person activates it on the School's host, creating their Account or proving they already own one. Imports therefore create invitations, students and enrollments, never Accounts.

## 6a: Invitations, activation, membership lifecycle

- `Invitation` (tenant, RLS): `kind` (staff, guardian, student), `identifier` (normalised VN mobile or lower-case email; optional for printed codes), `display_name`, a hashed one-time `code` (the plain code is shown once at creation and on the printable list), `expires_at` (default 30 days), `status` (pending, accepted, revoked, expired), `created_by`, `accepted_membership`. Kind-specific payload, all composite FKs:
  - staff: the Role Assignments to create on acceptance (role, scope, `valid_from`), checked by the same rules as the setup API at creation time and again at acceptance;
  - guardian: `student` and `relation`;
  - student: `student` (Lower/Upper Secondary only).
- `POST /api/auth/activate/` (AllowAny + CSRF, rate-limited later with login): `code`, `identifier`, `password`, `display_name`. If an Account with that identifier exists, the password must be that Account's (linking, never resetting); otherwise a new Account is created. Then the Membership (or reuse the active one), the Role Assignments / GuardianLink / `Student.membership`, and the invitation `accepted`, all in one transaction; the session starts as in login (key rotated last). Wrong code, expired, revoked, already used, identifier mismatch: one generic error.
- The app role gets `INSERT` on `accounts_account` for activation only (identifiers and password set at creation); no `UPDATE` of identifiers, no `DELETE`. A test proves no other view writes Accounts.
- Issuing: School admin issues any kind (`accounts.manage`, `guardian_invite.issue`); a homeroom teacher issues guardian and student invitations for their own class (`guardian_invite.issue`). Revoke = status `revoked`. A printable list per class (JSON now; PDF with the report-card pipeline) shows student, relation, code, expiry.
- Membership lifecycle: `POST /api/setup/memberships/{id}/deactivate/` ends the person's Role Assignments and Guardian links in force (dated today) and sets the Membership inactive, refusing the last in-force School admin (the slice 4 handover rule); `reactivate/` sets it active without restoring roles.

## 6b: Excel import

- Templates: `GET /api/setup/imports/templates/{kind}.xlsx` for `staff`, `students` (with enrollment class), `guardians`; Vietnamese headers, a locked header row, text-formatted ID and phone columns, a sample row, a sheet explaining each column.
- `POST /api/setup/imports/` uploads one `.xlsx` (≤ 5 MB, ≤ 3,000 data rows, `.xlsm` and other types refused, parsed with openpyxl read-only and `defusedxml` installed): it validates every row and stores an `ImportBatch` (tenant: kind, file hash, uploaded_by, status `previewed`, parsed rows and per-row results as JSON, no file kept). Response: counts and every error as `{row, column, code}`; nothing else is written.
- `POST /api/setup/imports/{id}/commit/` applies a previewed batch in one transaction and marks it `committed`; a batch commits once; a batch older than 24 hours or a file re-uploaded with changes needs a new preview. Any row failing at commit rolls the whole batch back.
- Row rules:
  - Text is NFC-normalised and trimmed; dates accept `dd/mm/yyyy` and Excel dates; national IDs are read as text (12 digits, leading zeros kept), phones normalised to the VN mobile form.
  - Students match existing ones by `ministry_student_id`, then `national_id`; a match updates only name, date of birth and gender, and starts an enrollment if the class differs (a move from the import date) or none is open; no match creates the student and the enrollment (`reason_started = new_year`, `valid_from` = the year's `starts_on` or the given date).
  - Guardians create guardian invitations (one per student and relation), never Accounts; a phone already linked as that student's Guardian is skipped.
  - Staff create staff invitations with their Role Assignments.
- The import runs synchronously (a class or a School of up to 3,000 rows); if it nears Cloudflare's 125 s limit in tests, move commit to a task and poll.

Done when a School can be set up from templates end to end: staff and Guardians receive codes, activate on their School's host, and land in the right roles, links and classes; a bad row is reported with its row and column and nothing is half-written.
