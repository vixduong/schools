# Phase 1a, slice 3: Leave requests

Slice 3 of `docs/phase-1a.md`. Standing rules: `backend/CODING_STANDARDS.md`, `frontend/CODING_STANDARDS.md`, the Constraints sections of `docs/phase-0.md`, `docs/roles.md` (Rules: Leave request), `DESIGN.md` (§ Screens: Teacher home, Guardian view; tickets). Builds on slice 2 (`docs/slices/1a-slice-2.md`): an approved request pre-fills the attendance sheet.

Done when a Guardian's request reaches the homeroom teacher, approval pre-fills attendance, and a Guardian of another student is refused.

## Model (app `timetable`, beside attendance)

- **`LeaveRequest`** (tenant): `student`, `sent_by` (the Guardian's Membership), `from_on`, `to_on` (whole days, inclusive), `reason` (1–500 chars), `status` (`waiting`, `approved`, `declined`, `cancelled`), `sent_at`, `decided_by` (Membership, null), `decided_at` (null), `decision_comment` (≤ 500, blank allowed). Composite FKs to student and both Memberships.
- **Checks**: `to_on >= from_on`; at most 30 days long; `decided_by` and `decided_at` set exactly when the status is `approved` or `declined`; a `declined` request has a comment.
- **One live request per day**: an exclusion constraint over `(school, student, daterange(from_on, to_on))` where the status is `waiting` or `approved` (`leaverequest_no_overlap`); a declined or cancelled request frees its days.
- **The lifecycle is a trigger** (`leaverequest_lifecycle`): only `waiting` → `approved`, `declined` or `cancelled`; a decided or cancelled request never changes again, and no column but the status and decision fields ever changes. The app role gets INSERT, SELECT and column-level UPDATE on `status`, `decided_by`, `decided_at`, `decision_comment`; no DELETE.
- **Audit**: the `audit_row_change` trigger on every insert and update (a request is about a person and is a small volume).

## Rules

- **Send**: `leave_request.send` on the student (a Guardian's own linked student), as of today. `from_on` is today or later and inside the school year of the student's Enrollment on that day; the student is enrolled on `from_on`. Requests for past days are out of scope: the subject teacher marks those as absent with leave when the Guardian tells the School.
- **Decide**: `leave_request.approve` on the student as of today: the homeroom teacher of the student's class (reached through the student) or the principal board. Approve takes an optional comment; decline needs one. Only a `waiting` request.
- **Cancel**: the sender only, while `waiting`.
- **Pre-fill**: the attendance sheet (`GET attendance/{entry}/{on}/`) gives each row `leave`: the approved request covering that day for that student, or null. An untaken sheet defaults such a student to `absent_excused` with the note "Có đơn xin nghỉ"; a taken sheet keeps its marks and only shows the flag, so the teacher can correct a mark taken before the approval. Nothing writes marks by itself: attendance stays the teacher's act.

## API (under `/api/setup/` like slices 1–2)

- `GET leave-requests/?status=&student=`: what the member may see — a Guardian their own sent requests; a homeroom teacher the requests of their class's students; the principal board all; newest first. Through the engine (`visible_students` with the matching action).
- `POST leave-requests/ {student, from_on, to_on, reason}`: the Guardian sends.
- `POST leave-requests/{id}/approve/ {comment}`, `.../decline/ {comment}`, `.../cancel/`.
- Each response carries the student's name and class, the sender's name, and the decider's name.

## Screens

- **Teacher home, "Cần cô xử lý"** (right column): one pinned ticket per waiting request of the homeroom class (student, class, days, reason, sent by), with Duyệt and Từ chối; Từ chối opens a comment field that must be filled. The empty state says nothing is waiting.
- **Guardian, `/guardian`**: an "Đơn xin nghỉ" block — the form (child picker as pills when there are several linked students, from and to dates, reason) and the Guardian's requests as tickets by state: Đang chờ, Đã duyệt, Từ chối (with the comment in red ink), Đã huỷ; Huỷ đơn on a waiting one. The rest of the Guardian view arrives in slice 8.
- **Attendance sheet**: a row with an approved leave carries a quiet "Có đơn" marker.

## Not in this slice

Requests for part of a day or for chosen periods; requests for past days; attachments (a doctor's note); notifying anyone by email or push (notices arrive in slice 7); the student sending their own request; editing a sent request (cancel and send again).
