# Slice 5: Permissions

Slice 5 of `docs/phase-0.md`. One permission engine answers "may this member do this action on this target, on this date?" from the facts already modelled: Role Assignments in force, a student's own Membership and Enrollment periods, Guardian links. `docs/roles.md` is the contract; every cell of its matrix becomes a test. All Constraints sections of `docs/phase-0.md` and the decisions in `docs/slices/slice-4.md` apply.

Features behind most actions (scores, leave requests, tests, notices) do not exist yet. This slice builds the engine and proves it on targets that do exist (School, subject group, class, subject × class, student); each later feature calls it instead of writing its own checks.

## Engine

- New app `permissions`. An **actor** is a Membership plus a date (default today). Its facts, computed once per request: Role Assignments in force on the date (active, confirmed, period covering the date, active Membership); the student whose `membership` it is, with that student's Enrollment periods; the Guardian links in force and the linked students' Enrollment periods.
- **Actions** are English slugs mirroring the matrix rows: `school.configure`, `accounts.manage`, `guardian_invite.issue`, `student_profile.view`, `attendance.take`, `attendance.view`, `leave_request.send`, `leave_request.approve`, `scores.enter`, `gradebook.review`, `gradebook.reopen`, `scores.view`, `conduct.rate`, `lessons.author`, `lessons.view`, `tests.author`, `tests.publish_regular`, `tests.approve_periodic`, `tests.take`, `tests.grade`, `notices.send`, `report_card.sign_subject`, `report_card.sign_class`, `report_card.sign_principal`, `ministry_reports.export`, `support_access.grant`, `audit.read`, plus the post-transfer reads `class_activities.view`, `classmates.view_basic`, `class_teachers.view`, `class_records.view`.
- **Targets**: `School`, `SubjectGroup`, `SchoolClass`, `(Subject, SchoolClass)` teaching pair, `Student`. Scope rules:
  - School admin, principal board: the whole School (the School admin only for configuration rows; least data).
  - Group leader: the classes where a subject of their group is taught (from subject-teacher rows), for the group's subjects only.
  - Homeroom teacher: their class, all subjects, read where the matrix says read.
  - Subject teacher: their subject × class pairs.
  - Student: themself; class reads through their Enrollment in force on the date.
  - Guardian: linked students in force on the date.
  - **After a transfer out** (enrollment ended with `transfer_out`, until that school year's `ends_on`): the student and their Guardians keep `scores.view` and `student_profile.view` on the student, `class_activities.view`, `classmates.view_basic`, `class_teachers.view` on the class they left; never `class_records.view`. After the year ends, nothing, unless another link keeps access open.
- **Named principal-board duties** (from `docs/roles.md`): principal-board rows gain `title` (`principal`, `vice_principal`) and two flags, `can_reopen_gradebooks` and `signs_for_principal`. `gradebook.reopen` needs the flag; `report_card.sign_principal` needs `title = principal` or the flag. A check constraint keeps these fields NULL/false on every other role.
- **API surface**: one function `can(actor, action, target) -> bool`, queryset helpers (`visible_students(actor)`, `visible_classes(actor)`) that filter in SQL rather than loading rows, and a DRF permission `Can(action, target_getter)`. `IsSchoolAdmin` is replaced by `Can("school.configure", …)` (and `accounts.manage` for role assignments); behaviour of slice 4 endpoints stays the same.
- `GET /api/auth/me/` adds the actor's capabilities summary (actions with the scopes they apply to) for the frontend to show or hide controls; the server still checks every request.

## The matrix as a test

- `permissions/matrix.py` holds the matrix as data, one entry per (action, role) with ✔ / 👁 / ✘ and its scope qualifier.
- A test parses the permission table in `docs/roles.md` and fails if it differs from `matrix.py`, so the document and the code cannot drift.
- A table-driven test builds one School with one member per role (plus a transferred-out student and their Guardian, a second class, a second subject group, and a second School) and asserts every cell: allowed on an in-scope target, refused on an out-of-scope target (other class, other subject, other group, other student, other School), and read-only cells refused for write actions.
- Date cases: a role ending yesterday grants nothing today; a scheduled leave keeps access until its day; post-transfer reads stop after the year's `ends_on`.

Done when every matrix cell has a passing test, the doc-vs-code test passes, slice 4 endpoints run on the engine, and no endpoint hand-rolls a role check.
