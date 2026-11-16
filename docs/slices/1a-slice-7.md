# Phase 1a, slice 7: Notices

Slice 7 of `docs/phase-1a.md`. Standing rules: `backend/CODING_STANDARDS.md`, `frontend/CODING_STANDARDS.md`, `docs/slices/README.md`, the Constraints sections of `docs/phase-0.md`, `docs/roles.md` (row "Send notices"; rule "Least data"), `docs/tech-stack.md` (Async work), `DESIGN.md` § Screens. Builds on slices 1 to 6 without changing them, except one argument added to `permissions.engine.can` (see Permission). Shape follows slice 3 (`docs/slices/1a-slice-3.md`).

Done when a homeroom teacher's notice reaches the class's Guardians in the app and by email (Django's test mail backend), and a sender outside the audience is refused.

Owner decision D1 (2026-11-16), who receives the audiences `docs/roles.md` leaves open: whole School = Guardians and students; own group = the teachers of the group's subjects; own classes = Guardians and students of the class. Recorded in `docs/roles.md` § Rules behind the matrix in the same change.

## Terms

- **Notice** (new in `GLOSSARY.md`): a title and a plain-text body from one sender to an audience; its recipients are fixed at sending.
- **Audience**: one of four, each tied to exactly one scope of the matrix row "Send notices" (`notices.send`):

| `audience` | Scope of the sender | Target column | Recipients (active Memberships, on the School's day) |
|---|---|---|---|
| `school` | `SCHOOL` (School admin, principal board) | none | Guardians (a GuardianLink in force) and students (`Student.membership`) of every student with an Enrollment in force |
| `group` | `GROUP_SUBJECTS` (group leader) | `subject_group` | holders of a `subject_teacher` Role Assignment in force for a subject of that group |
| `homeroom_guardians` | `HOMEROOM_CLASS` (homeroom teacher) | `school_class` | Guardians of the students with an Enrollment in force in that class |
| `class` | `TEACHING_CLASSES` (subject teacher) | `school_class` | Guardians and students of the students with an Enrollment in force in that class |

  The sender is never a recipient, and a recipient's Membership is active. "In force" is exactly the Python `Enrollment.objects.in_force`, `RoleAssignment.objects.in_force` and (for a GuardianLink, which has no helper) `Actor.linked_student_ids` rules. A notice names one class or one group; sending to several is several notices.
- **Read mark**: the first time a recipient opens a notice; set once.

## Permission

- `notices.send` and its matrix row already exist (`backend/permissions/matrix.py`); no matrix change. The matrix has one action with four scopes, and `HOMEROOM_CLASS` and `TEACHING_CLASSES` both match a `SchoolClass` target, so `can(actor, "notices.send", klass)` alone cannot tell "own class's Guardians" from "own classes". **`can()` gains `scope: Scope | None = None`**: when given, only cells whose `scope` equals it count (`_cells`). The send service asks one question per audience, through the engine, never a hand-rolled check: `school` → `can(actor, "notices.send", school, scope=Scope.SCHOOL)`; `group` → target the SubjectGroup, `GROUP_SUBJECTS`; `homeroom_guardians` → the SchoolClass, `HOMEROOM_CLASS`; `class` → the SchoolClass, `TEACHING_CLASSES`. A refusal is 403.
- Reading: a recipient reads only its own `NoticeRecipient` rows; a sender reads the notices it sent with the counts of recipients and of read marks. No matrix row for reading (a notice is addressed to the person; the database row is the grant).

## Model (new app `notices`)

- **`Notice`** (tenant; append-only: `enable_tenant_rls` grants all four verbs, so the migration then revokes UPDATE and DELETE, as `NARROW_UP` in `timetable/0005`; a sent notice is never edited or deleted): `sender` (Membership), `audience`, `school_class` (null), `subject_group` (null), `title` (`CharField` 200), `body` (**`TextField`**, the audit-privacy test checks only `text` columns by type), `sent_at` (`db_default` `now()`). Composite FKs to Membership, SchoolClass and SubjectGroup.
  - Checks: `notice_audience_is_known`; `notice_target_fits_audience` (`school`: neither column; `group`: `subject_group` only; the two class audiences: `school_class` only); `notice_title_not_blank`; `notice_title_single_line` (no CR or LF: the title is the mail subject, and Django raises `BadHeaderError` on a newline); `notice_body_not_blank`; `notice_body_length` (≤ 5 000 characters).
  - Audit: `audit_row_change` on INSERT with `title` and `body` hidden (the School admin reads the log: least data). Who sent which audience, to which class or group, and when stays visible.
- **`NoticeRecipient`** (tenant): `notice`, `membership` (composite FKs), `read_at` (null), `emailed_at` (null). Unique `(notice, membership)`.
  - Grants: INSERT, SELECT, and column-level UPDATE on `read_at` and `emailed_at` only.
  - **One SQL function `notice_reaches(notice_id, membership_id) RETURNS boolean`** (STABLE, SECURITY INVOKER, so RLS applies; reads the School's day as `(now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`) holds the four rules of the table above: the single source. The function itself requires the Membership to be active and not the notice's sender (it reads `sender_id` from the notice), so any writer, not only the service, is held to them (README: a rule the API enforces is also a database rule). Trigger `noticerecipient_is_in_audience` (BEFORE INSERT) calls it; the send service inserts with `INSERT … SELECT m.id FROM accounts_membership m WHERE m.school_id = … AND notice_reaches(notice, m.id)`, so Python never re-implements the branches. No row lock: a recipient set is fixed at sending (Known limits), and a lock on the class or group row would not make a concurrent Enrollment, GuardianLink or Role Assignment change wait. A test compares the function with `Enrollment.objects.in_force`, `RoleAssignment.objects.in_force` and `Actor.linked_student_ids` on one fixture per audience.
  - Trigger `noticerecipient_set_once` (BEFORE UPDATE): refuses a change to `school_id`, `notice` or `membership` (`IS DISTINCT FROM`, the pattern of `timetable/0005`), and to a non-null `read_at` or `emailed_at` (a column grant alone allows an overwrite). Who may mark a read is the API's rule: it updates the caller's own row `WHERE read_at IS NULL`.
  - **Audit: not audited**, because a whole-School notice writes one row per family, which would flood the log, and recipients follow from GuardianLinks, Enrollments and Role Assignments, which are audited; the row holds no free text.
- **Tasks tables** of `django-tasks-db` have no `school_id`: added to `GLOBAL_TABLES` and the allowlist of `tenancy/tests/test_rls.py`, with the narrowest grant the worker needs (SELECT, INSERT, UPDATE; no DELETE unless the worker proves it needs one, so task rows are not pruned: Known limits). No `ALTER DEFAULT PRIVILEGES` exists, so the third-party tables start with none: the grant is a migration of `notices` that depends on `django_tasks_db`'s last migration and calls `grant_app_role` (a sequence grant only if the key is serial; check the installed version). The worker runs as the app role (`DB_ROLE=app`). A task row carries `school_id` and `notice_id` only, never a title, body or address.

## Email

- New dependencies in `backend/pyproject.toml` (`docs/tech-stack.md`): `django-tasks` and `django-tasks-db`; `INSTALLED_APPS` gains `django_tasks` and `django_tasks_db`; `TASKS = {"default": {"BACKEND": "django_tasks_db.DatabaseBackend"}}`; the worker is `manage.py db_worker` (a deploy process; documented in `backend/README.md`).
- Task `notices.tasks.email_notice(school_id, notice_id)`, **one task per notice** (not per recipient: a whole-School notice would queue a thousand jobs). Per batch of 50 recipients with `emailed_at` null and an Account email, paged by id (`id > last_id ORDER BY id LIMIT 50`, so a recipient whose send fails is not picked again and a batch of failures cannot loop): a short `school_scope(school_id)` reads the batch; the mail is sent **outside** any transaction (SMTP is slow); a second short scope stamps `emailed_at` on the ones sent. A recipient whose send raises stays unstamped (logged by id, without `exc_info`), the others go on, and after the loop, outside any `except`, the task raises a new exception (`from None`) whose message holds counts only, so the failure shows in the worker: the worker stores the exception text and traceback in a global table without RLS, and `SMTPRecipientsRefused` carries the address. A re-run sends only the unstamped. The stamp is `WHERE emailed_at IS NULL`, so a concurrent re-run does not trip the set-once trigger. Subject = the title; body = the plain text, then the sender's name and the School's name. Logs ids and counts only, never an address or text.
- Enqueued with `transaction.on_commit(..., robust=True)` from the send view, so a rolled-back send emails nobody and an enqueue failure does not turn a committed notice into a 500 (a retry would send a second one).
- Settings: `EMAIL_BACKEND` (console in development), `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` from environment variables: the provider is a deploy setting. Django's test runner forces the locmem backend whatever `EMAIL_BACKEND` says, so tests assert on `django.core.mail.outbox`.
- Task API names (`@task`, `.enqueue()`, `db_worker`) are as in the `django-tasks` documentation (context7 `/realorangeone/django-tasks`); check the installed version's names before relying on them. `school_scope` is `atomic(durable=True)` and refuses nesting, so the worker must run a task outside a transaction: **one test runs `manage.py db_worker --batch` over one queued notice** and sees the mail; the other tests call the task function directly.

## API (under `/api/setup/notices/`)

- `GET audiences/`: what the caller may send to, the `notices.send` entry of `capabilities(actor)` (`engine.py`: `{}` for SCHOOL, `subject_groups` for GROUP_SUBJECTS, `school_classes` for the two class scopes) with names joined (the composer never holds a second rule): `[{audience, school_class?: {id, name}, subject_group?: {id, name}}]`, empty for a member who may send nothing. Only write cells count (`access: "write"`). A test shows it agrees with `can(..., scope=)` for every role.
- `POST /` `{audience, school_class?, subject_group?, title, body}`: sends. The class or group is fetched by id within the School (never trusted from the request); a target the School does not have is 400 `{"school_class": ["unknown"]}`; the engine then decides (403). One transaction: the Notice, the recipient rows, `on_commit` the email task. 400: `{"audience": ["unknown"]}`, `{"title": ["required", "too_long", "single_line"]}`, `{"body": ["required", "too_long"]}`, `{"recipients": ["none"]}` (the audience resolves to nobody; the view **raises** `ValidationError`, because `ATOMIC_REQUESTS` rolls back only on a raised exception, and a returned 400 would leave the Notice and its audit row committed), `{"constraint": [name]}`. Returns the notice (below).
- `GET /`: the caller's received notices, newest first, at most 100 (known limit): `id, title, body, sent_at, sender_name, audience, read_at`. `GET /?sent=1`: the notices the caller sent, with `recipient_count` and `read_count` (a sender sees counts, never who read).
- `POST {id}/read/`: sets `read_at` once; a second call is 200 with the first time; 404 when the caller is not a recipient.
- OpenAPI: every error body is declared; `make api-client` regenerates `frontend/src/api/openapi.json` and `schema.d.ts`, committed with the change.

## Screen

One route `/notices`, in the nav as "Thông báo" for every signed-in member (a Guardian, a student, a teacher), so each recipient has a place to read; slice 8 later embeds the same list in the Guardian's and the student's home.

- **Đã nhận**: a list of cards, newest first: title, sender, date; an unread one carries a pen-blue dot; opening a card shows the body and sets the read mark.
- **Đã gửi** (tab shown only when `GET audiences/` is not empty) with the counts "n người nhận · m đã đọc", and **Gửi thông báo** (a button on the same screen): a dialog with the audience select (a choice per entry of `audiences/`, labelled in Vietnamese: "Toàn trường", "Tổ <name>", "Phụ huynh lớp <name>", "Phụ huynh và học sinh lớp <name>"), title, body with a character count; a refused field is marked in red ink; focus goes to the first refused field (`frontend/CODING_STANDARDS.md`).
- `DESIGN.md` § Screens records the screen in the same change (and the specimen when it shows the pattern).

## Tests (written red first; `make red` for each guard)

Backend: engine `scope=` (a homeroom-only teacher refused for `class`, a subject-only teacher refused for `homeroom_guardians`, a group leader of another group refused, every role against every audience); recipients per audience with the sender excluded, an inactive Membership, an ended GuardianLink, an ended Enrollment, a student without an account, a teacher of another group, a pending Role Assignment; `notice_reaches` against the Python helpers; the trigger refuses a recipient outside the audience; `read` once and its set-once trigger; a rolled-back send emails nobody; send as the app role; RLS (School B sees nothing of School A's notices); audit shows no title or body; email: subject, body, no email address skipped, a failing recipient stays unstamped and the rest are stamped, re-run sends only the unstamped; one `db_worker --batch` run, under `as_app_role` and `transactional_db` (it exercises the narrow grant on the tasks tables and shows `school_scope` works inside the worker); more than 50 failing recipients end the loop; the failed task row's text holds no `@`; the trigger refuses the sender and an inactive Membership; a zero-recipient send leaves zero Notice rows and zero audit events; the app role is refused UPDATE and DELETE on `Notice`; `read` as the app role (the column grant); `title` and `body` absent from the audit log (the privacy test's regex does not match a varchar `title`, so a dedicated test); `can()` without `scope=` answers as before. Frontend (vitest): the list, the read mark, the composer with a refused field and focus, the audiences select from the stub.

## Built as (deviations from the text above)

- The `django_tasks_db` app label is `django_tasks_database`; the table is `django_tasks_database_dbtaskresult` (migration dependency, grant, `GLOBAL_TABLES`).
- The sent list also returns `school_class_name` and `subject_group_name` (null when unused), for the "Tổ <name>" and "Phụ huynh lớp <name>" labels.
- A class or group audience with no target is 400 `{"school_class": ["required"]}` or `{"subject_group": ["required"]}`; a target the audience does not use is 400 `{"constraint": ["notice_target_fits_audience"]}`.
- `GET /` has two response shapes (received, sent), declared as a `PolymorphicProxySerializer`.
- The email task opens one SMTP session per message (`shortcut:` comment in `tasks.py`); batching sessions waits for a provider that rate-limits.
- The shared dialog, popover and select stack at `--z-modal` (they were `z-50`, under the sticky header at `--z-sticky-nav`, which hid a dialog's title at 375 px).

## Known limits

- A notice is fixed at sending: a Guardian who joins the class later does not receive it, and one who leaves keeps it. A student or Guardian between two school years (no Enrollment in force) is outside every audience.
- A Guardian without an activated Membership has no `GuardianLink`, so receives nothing until they activate.
- No retry of a failed email and no re-enqueue if the enqueue after commit fails (the unstamped recipients remain; a later job may re-run them).
- A notice goes to one class or one group; no unread count in the nav.
- Task rows are never pruned (the app role has no DELETE on the tasks tables).
- The SMTP provider is configured, not run against a real one.

## Not in this slice

Attachments and rich text; Zalo and SMS (phase 5); push notifications; editing or deleting a sent notice; replies; an unsubscribe; sending to several classes at once; staff recipients of a whole-School notice (D1); a nav unread count; slice 8's embedding in the Guardian and student homes.
