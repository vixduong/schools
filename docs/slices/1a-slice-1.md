# Phase 1a, slice 1: Timetable

Slice 1 of `docs/phase-1a.md`. Standing rules: `backend/CODING_STANDARDS.md`, `frontend/CODING_STANDARDS.md`, the Constraints sections of `docs/phase-0.md`, `DESIGN.md` (§ Screens, Teacher home; § Dense components for the grid).

Done when a School admin enters a week for two classes, a teacher or room clash is refused with the clashing entry named, and a teacher sees today's periods on the home screen.

## Model (new app `timetable`)

- **`BellPeriod`** (tenant): `school_year`, `session` (`morning`, `afternoon`), `number` (1–5 within the session), `starts_at`, `ends_at` (times). Unique `(school, school_year, session, number)`; check `starts_at < ends_at`; the periods of a year never overlap (`bellperiod_no_overlap`, half-open, so one may start the minute another ends): a break between periods is the gap between one's end and the next one's start, with no record of its own. Times may be edited (they are a schedule, not a dated fact); a bell period is never deleted once used.
- **`TimetableEntry`** (tenant): `school_year`, `school_class`, `weekday` (ISO, 1 = Monday … 7 = Sunday), `bell_period`, `subject`, `teacher` (a Membership), `room` (nullable), `valid_from`, `valid_to` (nullable, inclusive). Composite FKs: `(school, school_year, school_class)` → class, `(school, school_year, bell_period)` → bell period, and `(school, x)` for subject, teacher and room.
- **Clash checks are exclusion constraints**, over `(school, X, weekday, bell_period, daterange(valid_from, valid_to))` for X = class, teacher and room: `timetableentry_class_clash`, `timetableentry_teacher_clash`, `timetableentry_room_clash` (a NULL room never clashes).
- **Triggers** (cross-table, locking the parent `FOR SHARE`): `timetableentry_inside_school_year` (as `enrollment_inside_school_year`) and `school_year_keeps_its_timetable` (a year cannot shrink past its entries, as `school_year_keeps_its_enrollments`); `timetableentry_teacher_teaches` — on insert, the teacher's Membership is active and holds an active `subject_teacher` Role Assignment for that subject × class whose period contains `valid_from`. A later change to the Role Assignment does not touch the entry: the School replaces the timetable from a day.

## Replacing a class's timetable from a day

The admin edits one week per class and applies it from a date (`DESIGN.md` grid). `POST /api/classes/{id}/timetable/ {valid_from, entries: [{weekday, bell_period, subject, teacher, room}]}`, in one transaction, `valid_from` after today (a replacement never rewrites today's or past periods, which attendance references; one-off changes for today are out of scope) and inside the class's year:

- entries of the class that have not started by `valid_from` (their `valid_from` ≥ it) are deleted: an entry not yet in force never governed a period, so nothing is lost (the one hard delete, like cancelling a scheduled leave);
- entries in force on `valid_from` end the day before;
- the new entries start on `valid_from`, open-ended (in force only within the year).

A clash is answered 400 `{"constraint": [<name>], "clash": {weekday, bell_period, class, subject, teacher, room}}` naming the existing entry; the serializer looks it up for the message, the constraint is the protection. Saving the same week twice for the same day is the normal way to correct a draft timetable.

## API

- `bell-periods/`: list by `school_year`, create, update times; `school.configure` (read for the principal board).
- `GET classes/{id}/timetable/?on=<date>`: the class's entries in force on the date (default today). Readers: `school.configure` (read) or `class_records.view` on the class.
- `GET timetable/mine/?on=<date>`: the signed-in member's own entries in force on that date's weekday, ordered by session and number, with times, class, subject and room. Any staff member; empty for others.

## Screens

- **`/timetable`** (School admin, principal board read only): pick the year and a class; a grid with bell periods as rows (morning, then afternoon) and Thứ 2 to Thứ 7 as columns; each cell picks a subject, then a teacher (only those with a subject-teacher Role Assignment for that subject × class), then a room; "Áp dụng từ ngày" and Lưu. A clash shows as one red-ink message naming the other entry. The bell schedule is a small table above the grid (session, number, start, end). Navigation link only for members who may read it.
- **`/` (teacher home)**: the left column "Hôm nay" lists today's periods (time, class, subject, room), with the current period on the `--color-select` wash; an empty state when none. The attendance result and the "Điểm danh" action arrive in slice 2; "Cần cô xử lý" arrives in slice 3.

## Not in this slice

Sunday columns in the grid (the model allows weekday 7), split groups sharing one slot, one-off changes for a single day, substitute teachers, copying a timetable between classes or years, importing it from Excel.
