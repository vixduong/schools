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

- `Student`: `full_name`, `date_of_birth`, `gender`, `ministry_student_id` (nullable), `national_id` (nullable), `account` (nullable, global; only Lower/Upper Secondary get one), `status` (studying, transferred_out, dropped_out, graduated). Unique `(school, ministry_student_id)` and `(school, national_id)` when set.
- `StudentStatusEvent`: append-only history (status, on, reason, by whom).
- `Enrollment`: `student`, `school_year`, `school_class`, `status`; unique `(school, student, school_year)`.
- `GuardianLink`: guardian `membership`, `student`, `relation` (mother, father, grandparent, other).
- RoleAssignment `student` scope FK and the student/guardian checks switched on.
- `AssessmentProfileVersion` (global, read-only to the app role): `level_kind`, `effective_from`, `effective_to`, `rules` (JSON). Seed the Lower/Upper Secondary version from Circular 22/2021 as data (score columns by periods per year, weights 1/2/3, one decimal, semester and year averages); Primary and Preschool versions come with their phases.

Done when the School admin can set up a school year end to end through the API (years, terms, Levels, Grades, groups, subjects, rooms, classes, students with enrollments, Guardians linked, role assignments), with every rule above covered by tests.

## Decisions after the 4a review (owner, 2026-10-31)

- **No role is clipped by school-year dates.** Schools run summer activities, extra classes and next-year setup, so admins and teachers stay in force between years; a role is in force by its own period and an active Membership. `school_year` is set only on class-scoped roles (homeroom teacher, subject teacher) and always equals the class's year.
- **Grade scope stays** for grade-wide activities: RoleAssignment carries a nullable `grade` scope; the role that uses it is defined with the activities phase.
- **Schools never act on each other.** Role assignments are managed by the School's own admins; the cross-School case does not exist. Whether an admin may change their own assignments is pending (see below).
- **A School admin may create, change and end their own role assignments**, all audited (slice 7), with one exception: **granting principal_board to themselves is two-step**. The row starts `pending_confirmation` and grants nothing until a different School admin or principal board member (not the requester, not the assignee) confirms it. Ending the last in-force School admin is refused.
