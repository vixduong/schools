# Phase 1a, slice 2: Attendance

Slice 2 of `docs/phase-1a.md`. Standing rules: `backend/CODING_STANDARDS.md`, `frontend/CODING_STANDARDS.md`, the Constraints sections of `docs/phase-0.md`, `DESIGN.md` (§ Screens, Teacher home). Builds on slice 1 (`docs/slices/1a-slice-1.md`): a held period is a timetable entry on a date, and an entry that has started is never deleted or moved, so marks can point at it.

Done when a teacher takes a period, the homeroom teacher sees it in the overview, and a teacher of another class is refused.

## Model (app `timetable`, beside the entries it points at)

- **`AttendanceMark`** (tenant): `entry` (TimetableEntry), `on` (date), `student`, `status` (`present`, `late`, `absent_excused`, `absent_unexcused`), `note` (≤ 200 chars, blank allowed), `recorded_by` (Membership), `recorded_at`. Unique `(school, entry, on, student)`; composite FKs to entry, student and Membership. The app role gets INSERT, SELECT and column-level UPDATE on `status`, `note`, `recorded_by`, `recorded_at`; no DELETE.
- **A period is taken** when it has marks; the sheet is saved whole (one mark per student enrolled in the class on that date), so a taken period has a mark for every student enrolled when it was taken. A student whose Enrollment ends afterwards (a move or a leave, even backdated) keeps the mark and stays on that sheet.
- **Triggers** (locking the parent `FOR SHARE`): `attendancemark_fits_entry` — the entry is in force on `on` (inside its period and its school year) and `on`'s ISO weekday is the entry's weekday; `attendancemark_student_enrolled` — the student has an Enrollment in the entry's class whose period contains `on`.
- **Guards**: `attendancemark_not_in_the_future` — `on` is not after the School's today (`now() AT TIME ZONE 'Asia/Ho_Chi_Minh'`, as in the audit trigger below); `timetableentry_keeps_its_attendance` — an entry with marks is not deleted and does not end before its last mark (the replace in slice 1 starts after today, so it never trips this; a bug or a hand-written statement answers 400 `constraint`).
- **Audit**: the `audit_row_change` trigger on updates of a mark dated before the update's day (`WHEN (OLD.on < current_date)`): a correction after the day is logged; taking and correcting on the day is not (a period's sheet per day would flood the log).

## Rules

- **Who takes it**: `attendance.take` on the entry's subject × class (`TeachingPair`), through the engine, as of today. Not only the entry's own teacher: anyone with that subject × class in force (a co-teacher of the pair), which is what the matrix says.
- **When**: `on` is today or earlier, and within a held period of the entry (the triggers). No later lock in this slice: the teacher corrects their own periods any time in the year, logged after the day.
- **Who reads**: `attendance.view` — the period's sheet for its subject × class (subject teacher), the class overview for the homeroom class, everything for the principal board.

## API (under `/api/setup/` like slice 1)

- `GET attendance/{entry}/{on}/`: the period (time, class, subject, room), and one row per student enrolled in the class on `on`, plus any student already marked in this period that day who has left the class since (id, name, mark or null), ordered by name. Readers: `attendance.take` or `attendance.view` on the pair.
- `PUT attendance/{entry}/{on}/ {marks: [{student, status, note}]}`: exactly the students enrolled on that date, and also the already-marked ones who have left, who may be listed to correct their mark and are not required (400 `students` naming the missing or extra ids otherwise); upserts in one transaction; unchanged marks are not rewritten (no audit noise). `attendance.take`.
- `GET classes/{id}/attendance/?from=&to=` (at most 31 days): `students`: every student enrolled in the class during the range or marked in its periods, each with their non-present marks by day (day, bell period, subject, status), ordered by name; `periods`: the periods the class held on each day of the range up to today (day, bell period, subject, `taken`), so "all present" reads apart from "not taken". `attendance.view` on the class.
- `timetable/mine/` gains per period `attendance`: null when not taken, else `{absent, late}` counts.

## Screens

- **Teacher home**: each of today's periods shows its attendance result ("Chưa điểm danh", or "Vắng 2 · Muộn 1", or "Đủ"); the current period carries the one filled action Điểm danh, other periods a plain link.
- **`/attendance/$entryId/$on`**: the class list, one row per student with the four statuses as a segmented control (default Có mặt for an untaken period), a note field, and Lưu; a save status line. Read only for a reader without `attendance.take`.
- **`/classes/$classId/attendance`** (homeroom teacher, principal board): a week at a time, students as rows and days as columns, each cell the day's non-present marks as compact codes (P = vắng có phép, K = vắng không phép, M = muộn), tabular figures, a total column for the week; a held period nobody has taken shows in the cell as a light "chưa điểm danh" (so an empty cell is "all present" or a day with no period).

## Not in this slice

Pre-filling from approved leave (slice 3); attendance of a student or Guardian (slice 8); locking a day's attendance; per-student attendance on the profile; reports and exports; SMS or notices to Guardians on absence.
