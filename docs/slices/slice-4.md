# Slice 4: School setup

Slice 4 of `docs/phase-0.md`, split in two so each half ends green and reviewable. All rules in phase-0.md's constraint sections apply (composite same-School FKs via `composite_fk`, RLS on every tenant table, no open views, history instead of deletes).

## 4a: structure and the RoleAssignment redesign

Tenant tables, all with `school` FK, RLS, `(school_id, id)` unique for composite FKs:

| Model | Fields (beyond `school`) | Notes |
|---|---|---|
| `SchoolYear` | `name` ("2026-2027"), `starts_on`, `ends_on` | unique `(school, name)`; no overlapping years per School |
| `Term` | `school_year`, `name` (HK I, HK II), `starts_on`, `ends_on` | inside its year |
| `Level` | `kind` (preschool, primary, lower_secondary, upper_secondary) | the Levels this School teaches; unique `(school, kind)` |
| `Grade` | `level`, `number` (1 to 12; preschool uses age groups later) | number must fit the Level |
| `SubjectGroup` | `name` (tổ Toán) | |
| `Subject` | `name`, `code`, `subject_group` (nullable), `ministry_code` (nullable), `assessment` (scored, comment_only) | unique `(school, code)` |
| `Room` | `name`, `is_active` | |
| `SchoolClass` | `school_year`, `grade`, `name` ("7A"), `room` (nullable) | unique `(school, school_year, name)` |
| `Membership` | add `ministry_staff_id` (nullable) | unique `(school, ministry_staff_id)` when set |

**RoleAssignment redesign** (replaces `scope_kind`/`scope_id` and the text `school_year`):

- `school_year` composite FK to `SchoolYear`.
- Typed nullable composite FKs: `subject_group`, `school_class`, `subject`, and `student` (added in 4b; leave room).
- A check constraint per role on which scope columns are set:
  - `school_admin`, `principal_board`: none.
  - `group_leader`: `subject_group` only.
  - `homeroom_teacher`: `school_class` only.
  - `subject_teacher`: `subject` + `school_class` (one row per subject × class, the "teaching row").
  - `student`, `guardian`: `student` only (enforced from 4b; until then these two roles cannot be created).
- `valid_from` required, `valid_to` nullable; no two overlapping periods for the same membership, role and scope (exclusion constraint on a date range, `btree_gist`), so a role can end and resume in one year with history kept.
- Rewrite the migration path: existing rows are dev data; the migration may drop and recreate the scope columns.

API (School admin only for now: a temporary `IsSchoolAdmin` permission = a `school_admin` RoleAssignment in force; slice 5 generalises it): list/create/update for every model above; no hard delete for years, classes and role assignments (end them instead); rooms and subjects can be deactivated, not deleted.

## 4b: people and assessment rules

- `Student`: `full_name`, `date_of_birth`, `gender`, `ministry_student_id` (nullable), `national_id` (nullable), `membership` (nullable, unique; only Lower/Upper Secondary students get one), `status` (studying, transferred_out, dropped_out, graduated). Unique `(school, ministry_student_id)` and `(school, national_id)` when set.
- `StudentStatusEvent`: append-only history (status, on, reason, by whom).
- `Enrollment` as **periods**, so a student can move during the year: `student`, `school_year`, `school_class`, `valid_from`, `valid_to`, `reason_started` (new_year, transfer_in, class_change, return), `reason_ended` (transfer_out, class_change, dropped_out, graduated, year_end). No overlapping periods per student; the period lies inside its school year. Actions: move class mid-year (end + new row in one request), transfer out (end the enrollment + a `transferred_out` status event in one transaction; records stay with the School), transfer in or return (new enrollment starting mid-year). Carried-over results from the previous School come with the gradebook in phase 1.
- `GuardianLink`: guardian `membership`, `student`, `relation` (mother, father, grandparent, other), `valid_from`, `valid_to`; no overlapping links for the same pair.
- `Student.membership` (nullable, unique) replaces `Student.account`, so a student signs in through a Membership like everyone else.
- Leftovers from 4a: lock the in-force School admin rows before the last-admin count; PATCH of an immutable field answers 400 instead of being ignored.
- ~~RoleAssignment `student` scope FK~~ Changed after the 4a review: students and Guardians get no RoleAssignment rows. A student's rights come from `Student.membership` + `Enrollment`, a Guardian's from `GuardianLink`, so each link has one source of truth.
- `AssessmentProfileVersion` (global, read-only to the app role): `level_kind`, `effective_from`, `effective_to`, `rules` (JSON). Seed the Lower/Upper Secondary version from Circular 22/2021 as data (score columns by periods per year, weights 1/2/3, one decimal, semester and year averages); Primary and Preschool versions come with their phases.

Done when the School admin can set up a school year end to end through the API (years, terms, Levels, Grades, groups, subjects, rooms, classes, students with enrollments, Guardians linked, role assignments), with every rule above covered by tests.

## Decisions after the 4a review (owner, 2026-10-31)

- **No role is clipped by school-year dates.** Schools run summer activities, extra classes and next-year setup, so admins and teachers stay in force between years; a role is in force by its own period and an active Membership. `school_year` is set only on class-scoped roles (homeroom teacher, subject teacher) and always equals the class's year.
- **Grade scope stays** for grade-wide activities: RoleAssignment carries a nullable `grade` scope; the role that uses it is defined with the activities phase.
- **Schools never act on each other.** Role assignments are managed by the School's own admins; the cross-School case does not exist. Whether an admin may change their own assignments is pending (see below).
- **A School admin may create, change and end their own role assignments**, all audited (slice 7), with one exception: **granting principal_board to themselves is two-step**. The row starts `pending_confirmation` and grants nothing until a different School admin or principal board member (not the requester, not the assignee) confirms it. Ending the last in-force School admin is refused: an admin's role can end only while another membership already holds a School admin role in force right now (a pending or future-dated replacement does not count), so the handover is to appoint the replacement first, then end the old role. The same rule will apply to deactivating a Membership.

## Decisions after the 4b review (owner, 2026-10-31)

- **Leaving can be scheduled in advance.** A transfer, drop-out or graduation may be recorded with a future date: the enrollment stays in force until that day, a student's status is computed as of a date from the status events (a future event does not change today's status), and a scheduled leave can be cancelled before it takes effect, which is the only case where an end date may be cleared.
- **School admins see a student's national ID masked in lists** (last 3 digits) and in full only on the single student's record; from slice 7 every full view is audited.

### How the 4b review fixes implement them

- **Status is derived, not stored.** `Student.status` and its sync triggers are dropped (schools.0006); the status on a date is the latest `StudentStatusEvent` with `on` up to that date (then highest id), `studying` when none. The API shows `status` (today) and `scheduled_change` (`{status, on}`, or null); `students/?status=` filters on today's status.
- **Leaving is one action**: `students/{id}/leave/` (`reason` transfer_out, dropped_out or graduated; `on`; `destination` for a transfer out) ends the open enrollment on `on` and records the event with that date, in one transaction. `on` may be in the future: the leave is scheduled, the student stays in the class and `studying` until then. `students/{id}/leave/cancel/` undoes a leave whose `on` is still in the future (a `studying` event with the same `on`, enrollment re-opened); it is the only path that clears a `valid_to`. `status-events` accepts only `studying` (a return, possibly scheduled).
- **Enrollment edits**: only `year_end` is accepted as `reason_ended`; `school_class` changes in place only while the row is open and has not started (otherwise `enrollments/{id}/move/`); `reason_ended` changes only with `valid_to`. An open enrollment is in force only inside its school year; `school-years/{id}/close/` ends the open ones with `year_end` so continuing students can start the next year.
- **Membership kinds**: a student's Membership holds no role assignment and no Guardian link and is not the requester's own; no Guardian link or role assignment uses a student's Membership. Staff may be Guardians.
- **Student list privacy**: the list masks `national_id` to its last 3 digits; one student shows it in full. `national_id` is 12 digits when set.
- **Slice 5 note**: derive access (class lists, After-a-transfer-out rules in `docs/roles.md`) from Enrollment periods as of the date, never from a stored status.
