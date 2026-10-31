# Slice 5: Permissions

Slice 5 of `docs/phase-0.md`. One permission engine answers "may this member do this action on this target, on this date?" from the facts already modelled: Role Assignments in force, a student's own Membership and Enrollment periods, Guardian links. `docs/roles.md` is the contract; every cell of its matrix becomes a test. All Constraints sections of `docs/phase-0.md` and the decisions in `docs/slices/slice-4.md` apply.

Features behind most actions (scores, leave requests, tests, notices) do not exist yet. This slice builds the engine and proves it on targets that do exist (School, subject group, class, subject × class, student); each later feature calls it instead of writing its own checks.

## Engine

- New app `permissions`. An **actor** is a Membership plus a date (default today). Its facts, computed once per request: Role Assignments in force on the date (active, confirmed, period covering the date, active Membership); the student whose `membership` it is, with that student's Enrollment periods; the Guardian links in force and the linked students' Enrollment periods.
- **Actions** are English slugs mirroring the matrix rows: `school.configure`, `accounts.manage`, `guardian_invite.issue`, `student_profile.view`, `student_profile.view_sensitive`, `attendance.take`, `attendance.view`, `leave_request.send`, `leave_request.approve`, `scores.enter`, `gradebook.review`, `gradebook.reopen`, `scores.view`, `conduct.rate`, `lessons.author`, `lessons.view`, `tests.author`, `tests.publish_regular`, `tests.approve_periodic`, `tests.take`, `tests.grade`, `notices.send`, `report_card.sign_subject`, `report_card.sign_class`, `report_card.sign_principal`, `ministry_reports.export`, `support_access.grant`, `audit.read`, plus the post-transfer reads `class_activities.view`, `classmates.view_basic`, `class_teachers.view`, `class_records.view`.
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

## Decisions after slice 5 (owner, 2026-10-31)

- **Principal board reads the School setup** (years, classes, subjects, role assignments) without editing it, as the matrix's 👁 says.
- **Continuing students keep access between school years.** A student whose last enrollment ended with `year_end` (not a leave) and their Guardians keep their access through the break until the next enrollment starts; leavers follow the post-transfer rule.
- **Teachers may read other classes.** Any member with a teaching role in force (subject teacher, homeroom teacher, group leader) may view the profiles and scores of students in every class of the School, read only; writing stays within their own scope. Sensitive fields (national ID, Ministry IDs, Guardian contact details, later health data) stay limited to the student's own homeroom teacher, the principal board and the School admin. Every cross-class read is audited from slice 7.
- **A student still at the School sees every class they have been in**: all class information (activities, classmates' basic profile, teachers, class records) of every past and current class, read only, together with their own scores of all years; the same for their Guardians. The post-transfer limits apply only to students who left.
- These change the matrix in `docs/roles.md`; the doc and `permissions/matrix.py` change together in one commit so the doc-vs-code test stays green.
- Confirmed by the owner: sensitive fields (national ID, Ministry IDs, Guardian contact details, later health data) stay limited to the student's own homeroom teacher, the principal board and the School admin, through a separate `student_profile.view_sensitive` action.
- From the slice 5 review: every leaver (transfer out, drop-out, graduation) keeps the post-leave reads until that year's `ends_on`; nobody may turn on their own principal-board duties (`can_reopen_gradebooks`, `signs_for_principal`, `title=principal`), another admin or board member does it; `class_records.view` covers class-level content only, per-student data always goes through the per-student actions.

### How the review fixes implement them

These supersede the Engine section above where they differ.

- **Setup reads**: `Can(action, read=True)` lets a 👁 cell through for GET, HEAD and OPTIONS only, so the setup viewsets are readable by the principal board and writable by the School admin; the one write gated by a 👁 cell is `confirm` (`read_on_writes=True`).
- **Where a student stands** (`Actor.student_access`): in a class on the date or a continuing student between years (last enrollment `year_end`, or still open after its year) is *at the School* and has every student-scoped cell plus the class reads of every class started so far; a leaver (transfer out, drop-out, graduation) keeps `student_profile.view`, `scores.view` and three class reads on the class left until that year's `ends_on`. A last enrollment ended by `class_change` with no next one grants nothing.
- **Teachers**: the `student_profile` and `scores_view` cells of group leader, homeroom and subject teacher are School-wide 👁; `student_profile.view_sensitive` is its own matrix row, and `StudentSerializer` leaves `national_id` and `ministry_student_id` out for anyone without it (no serializer exposes Guardian contact details yet).
- **Class reads for staff** come from their class scopes (`STAFF_CLASS_READS` in `permissions/engine.py`); `visible_classes` and `can` share `_scope_classes`, so they agree by construction, and `visible_pairs` returns a `Q` for rows that carry a subject × class.
- **Duties** (`RoleAssignmentSetupSerializer`): `self_duty_change` and `pending_confirmation` (400, keyed by field); `title` is settable once while NULL; the exclusion constraint `roleassignment_one_principal_at_a_time` allows one `title=principal` row per School at any date.
- **Database guard** (schools.0008): triggers keep a student's Membership free of role assignments and Guardian links, and the other way round; the Membership row is locked FOR SHARE on the role/link side and FOR NO KEY UPDATE on the student side.
- **The break between years ends** 30 days after the next school year's `starts_on`, or 120 days after the old year's `ends_on` when no next year exists yet; a continuing student not enrolled by then loses access (their Guardians too). A leave (graduation, transfer out, drop-out) can be recorded during the break, without an open enrollment.
