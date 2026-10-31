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

### How 6a implements it

These refine the bullets above where they differ.

- **Expiry is derived**, not stored: `status` is `pending`, `accepted` or `revoked`; the API reads `expired` for a pending invitation past `expires_at` (history rule: derived state is computed).
- **Codes**: 10 characters from an alphabet without 0/O/1/I/L, shown as `XXXXX-XXXXX`; case, spaces and dashes are ignored when typed. Stored as an HMAC keyed by `SECRET_KEY` (`code_digest`, unique per School), so rotating `SECRET_KEY` voids pending codes.
- **Printing issues fresh codes.** A digest cannot be shown again, so `POST /api/setup/invitations/print/` (`school_class`) gives every pending guardian and student invitation of the class's students today a new code and a new 30-day expiry; the previous print's codes stop working.
- **Errors at activation**: the generic `invalid_invitation` for a bad code or credentials; after both check out, `{"invitation": ["cannot_apply"]}` (inactive subject, the student already has a sign-in) or `{"constraint": [name]}` (an overlapping period, the membership-kind triggers, the secondary-level trigger), and nothing is written, the Account included. A weak password for a new Account answers `{"password": [...]}` (Django's minimum length and common-password validators).
- **An inactive Membership is reactivated only by a staff invitation** (issued under `accounts.manage`); a guardian or student code, which a homeroom teacher may print, answers `cannot_apply` for a deactivated person.
- **Self-grant through an invitation**: an admin redeeming their own `principal_board` invitation gets a `pending_confirmation` row, as in the setup API.
- **No identifier probing**: the password rules apply to every activation, before the Account lookup, and both branches spend one hash; authorisation runs before any check that describes the student.
- **Staff invitations carry no named duties** (`title`, `can_reopen_gradebooks`, `signs_for_principal`): another admin or board member sets them after acceptance, as for any row.
- **Listing**: each member lists the invitations they may issue; the principal board reads staff invitations (`accounts.manage` 👁) and revokes none.
- **Memberships**: `GET /api/setup/memberships/` (School admin, principal board read) shows id, the Account's display name, status and Ministry staff ID, no identifiers. Deactivating ends the rows still running after today on today, or on their first day for a future row.
- **Known limit**: deactivating ends a role or link that has not started on its first day (a period cannot end before it starts), so reactivating before that day brings it back for that one day.
- **Deferred**: rate limiting of activation (with login); an `accepted_at` timestamp (the audit log, slice 7); proof of owning the identifier (no SMS or email check in the MVP), so whoever holds a printed code can create an Account for a phone or email that has none, and its real owner then has no recovery path.

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
