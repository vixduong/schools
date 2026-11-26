# Phase 1a, slice 8: Guardian and student views

Slice 8 of `docs/phase-1a.md`, the last of 1a. Standing rules: `backend/CODING_STANDARDS.md`, `frontend/CODING_STANDARDS.md`, `docs/slices/README.md`, the Constraints sections of `docs/phase-0.md`, `docs/roles.md` (rule "Least data"; rows "See student profiles", "See attendance", "See scores"), `DESIGN.md` § Screens (Guardian view). Builds on slices 1 to 7 without changing them.

Done when a Guardian with two children and a student each see only their own data, on a 375px screen, and the app installs as a PWA.

Owner decisions (2026-11-26):
- **D1, timetable**: the Hôm nay block shows only the periods of the student's class on the chosen day (default today), never the class's weekly grid.
- **D2, landing**: a member whose only roles are Guardian or student lands on `/guardian`; the student uses the same page without Đơn xin nghỉ.

## Terms

- **Child**: a student in `actor.own_student_ids | actor.linked_student_ids` (the member's own student record, or a GuardianLink in force), each admitted by `can(actor, "scores.view", student, released=True, scope=Scope.SELF)` or the `Scope.LINKED` equivalent. Not `visible_students` alone: its SCHOOL cell would list every student for a teacher who is also a Guardian. A student who left stays a child for scores only (`POST_LEAVE_STUDENT_ACTIONS`).
- **Released score**: the current entry of a cell whose column has `released_at`. A cell whose current entry was entered after the release is flagged `changed_after_release` (same rule as the teacher grid, `grades/views.py` `detail`).

## Model

No new tables, no migration. Every read goes through tables whose grants and RLS already exist (SELECT for the app role); the School's RLS is the database net, and the member-to-student scope is enforced by the API through `can` on the SELF and LINKED cells ("view only, because a Guardian is not a database role: the per-member rule lives in the permission engine, the one place `docs/roles.md` names"). Nothing is written, so there is nothing new to audit.

## API (new app `portal`, no models; read only; all under `/api/portal/`)

| Endpoint | Returns | Permission |
|---|---|---|
| `GET children/` | the member's children: `id`, `name`, `class_name` today (null when left), `left` | own and linked students only; an empty list for anyone with none (a plain teacher included) |
| `GET children/<id>/today/?on=` | the periods of the class the child is enrolled in on `on` (School's day; default today): bell period, session, times, subject, teacher's `display_name`, room; each with the child's attendance `status` or null when not taken (the mark's `note` is not returned: free text, Least data) | the child is own or linked (else 404); `can(actor, "class_records.view", klass)` for that class (false after leaving, so a left child gets an empty list) and `class_teachers.view` for teacher names; attendance only when `attendance.view` reaches the child. Reuse `timetable.views.in_force` |
| `GET children/<id>/scores/?term=` | `term` defaults to the term in force on the School's day (400 on an unknown or other-year id). Per gradebook of that term whose class overlaps one of the child's own Enrollments (the `roster` rule of `grades/views.py` applied from the student's side, so a class change or a leaving date is covered): subject name and the released columns (`kind`, `index`) with the cell's current `value` or `result` and `changed_after_release`; unreleased columns are absent, not null | own or linked, `scores.view` with `released=True` through `_open_students`; a left child still reads their results up to the leaving date |

Rules and enforcement:
- A child outside the member's reach is 404, never 403 (no existence leak). Enforced by the own-or-linked queryset; tests per endpoint: a Guardian of another student, a student of the same class, a plain subject teacher (empty `children/`, 404 on any child), and a teacher who is also a Guardian (sees only the linked child).
- Names only: the serializers expose `display_name` and no `Account` relation (`accounts_account` has no RLS, so a nested serializer would leak email and phone); a test asserts the response keys hold no contact field.
- A cleared current entry shows blank, never an older value: scores come from `current_entries` (`grades/views.py`), with no value filter on top. A correction after release reaches the Guardian at once, flagged `changed_after_release` (the owner's per-column release rule, `docs/phase-1a.md`).
- Released only: the query joins `GradebookColumn.released_at IS NOT NULL`; test that an unreleased column and its entries never appear, and that approving (which releases the rest) makes them appear.
- "Today" is the School's day (`timezone.localdate()`, Asia/Ho_Chi_Minh).
- The teacher's name is shown, never their contact details (Least data).
- Query count is bounded (no N+1): a test with two children and several periods asserts a fixed number of queries.
- OpenAPI schema is regenerated (`make api-client`); the frontend uses the generated types.

## Screens (frontend)

- `/guardian` (`routes/_app/guardian.tsx`) rebuilt per `DESIGN.md`: one column up to 440px; child switcher as pills (hidden for one child); blocks **Hôm nay** (periods with the child's mark per period: Có mặt, Muộn, Vắng có phép, Vắng không phép; the current period marked), **Điểm mới** (released scores by subject, a changed score marked), **Đơn xin nghỉ** (the existing `LeaveBlock`), **Thông báo** (latest received notices, link to `/notices`).
- Student: the same page without Đơn xin nghỉ. The leave block is per child: shown for a child the member may send for (`/leave-requests/children/`), so a left child has none.
- Landing: after login, a member with no teacher or admin reach goes to `/guardian` (the `/` route redirects); the nav shows the link only to a member with children. "Current period" uses the School's clock (`on` and times come from the API), not the browser's.
- PWA: `manifest.webmanifest` (name, short name, `display: standalone`, theme and background colours from `DESIGN.md`, 192 and 512 icons plus a maskable one), `<link rel="manifest">`, `theme-color`, an apple-touch-icon. No service worker and no offline mode.
- Copy in Vietnamese; empty states for no periods today, no released scores, no notices.

## Checks (each runs on its own)

1. `make check` green (backend ruff + pytest, frontend lint, typecheck, OpenAPI diff, vitest, smoke).
2. New backend tests for the three endpoints: happy, other-student 404, unreleased hidden, changed flag, left child, empty class day, query count.
3. Frontend tests: two-child switch, student view without leave block, empty states.
4. Screenshots at 375px and desktop, light and dark, of the Guardian page in each state; `/manifest.webmanifest` parses (a smoke check) and DevTools Application › Manifest shows it installable.
5. `DESIGN.md` § Screens updated in the same change: attendance mark labels, the changed-score marker, PWA colours, a "Built (slice 8)" note; the specimen if it shows the pattern.

## Not in this slice

- Averages, ratings, conduct and report cards (1b); carried results from a previous School on the Guardian view.
- Attendance history beyond the chosen day, a score history per cell, push notifications, offline mode, a service worker.
- Student leave requests; a Guardian's profile editing.
- Changes to the matrix or to any earlier slice's endpoints.
