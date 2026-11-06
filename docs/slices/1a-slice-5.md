# Phase 1a, slice 5: Gradebook workflow

Slice 5 of `docs/phase-1a.md`. Standing rules: `backend/CODING_STANDARDS.md`, `frontend/CODING_STANDARDS.md`, `docs/slices/README.md`, the Constraints sections of `docs/phase-0.md`, `docs/roles.md` (Rules: Gradebook; Named duties), `DESIGN.md` § Screens (Teacher home, Gradebook, Gradebook grid; Statechart). Builds on slice 4 (`docs/slices/1a-slice-4.md`): entry, release and the grid stay as they are.

Done when the full cycle submit → return → resubmit → approve → reopen runs through the API and the screen, each step by the right role only.

## Lifecycle

```
draft ──submit──▶ submitted ──approve──▶ approved (locked)
draft ◀─withdraw── submitted
draft ◀─return (comment)── submitted
draft ◀─reopen (reason, red ink)─────── approved
```

| Step | From → to | Who (matrix action, on the gradebook's subject × class, as of today) | Text |
|---|---|---|---|
| `submit` | draft → submitted | `scores.enter` (the subject teacher) | none |
| `withdraw` | submitted → draft | `scores.enter` | none |
| `return` | submitted → draft | `gradebook.review` (group leader of the subject's group, principal board) | comment, required |
| `approve` | submitted → approved | `gradebook.review` | none |
| `reopen` | approved → draft | `gradebook.reopen` (principal board with `can_reopen_gradebooks`) | reason, required |

"Returned" is not a state: a draft whose latest step is `return` shows that comment until the next `submit`.

## Model (app `grades`)

- **`Gradebook.status`**: `draft`, `submitted`, `approved` (check `gradebook_status_is_known` widened).
- **`GradebookStep`** (tenant, **append-only**: INSERT and SELECT only, no UPDATE or DELETE grant): `gradebook`, `action` (the five above), `by` (Membership), `at` (`db_default` `now()`, the transaction's start, as `Gradebook.opened_at`), `comment` (≤ 500, blank allowed). Composite FKs to gradebook and Membership. Check `gradebookstep_comment_when_needed`: `return` and `reopen` have a non-blank comment, the others a blank one.
- **The step drives the status** (trigger `gradebookstep_applies`, AFTER INSERT): it locks the gradebook `FOR NO KEY UPDATE` and sets `status` to the step's target. The API only inserts steps; it never writes `status` itself.
- **The status follows a step** (trigger `gradebook_lifecycle`, BEFORE UPDATE OF `status`, beside slice 4's `gradebook_only_status_changes`): the change is one of the five transitions above, and a step of this gradebook with that action and `at = now()` exists (so a bare `UPDATE … SET status` by any writer, the app role included, is refused). It also holds:
  - → `submitted`: every student enrolled in the class on the School's today (`(now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`) with an Enrollment overlapping the term has a current entry with a value or result in every column (`incomplete`). Same roster rule as `scoreentry_student_in_class`; reuse its SQL.
  - → `approved`: every column is released (`unreleased_columns`). The approve step releases them first (below).
  - `return` and `approve`: the step's `by` is not the `by` of the latest `submit` (`own_submission`): nobody reviews their own gradebook, even when they also lead the group.
- **Approval releases the rest** (owner decision, `docs/phase-1a.md`): in the approve transaction, after the lock and before the step, every column with `released_at` null gets `released_at` = the clock read once (as slice 4's release) and `released_by` = the approver. `gradebookcolumn_release_once` already refuses moving an earlier release.
- **Locked means no entry**: `scoreentry_gradebook_open` (slice 4) already refuses an entry unless the gradebook is `draft`; nothing new. Release while `submitted` stays allowed (the teacher's act; it changes no score).
- **Edits after a reopen are logged**: score entries are their own append-only log with who and when, and every column is released by then, so any later entry shows `changed_after_release` (slice 4) to the grid and, in slice 8, to families. The reopen step itself carries who, when and the reason. Nothing more is stored.
- **Audit**: `audit_row_change` on `grades_gradebookstep` with `comment` hidden (the School admin reads the log and must not read a reason about scores; `audit/tests/test_audit_privacy.py`). The status update on `grades_gradebook` is already audited.
- **Concurrency**: every step locks the gradebook `FOR NO KEY UPDATE` first (slice 4's `lock()`), so a step and a cell save take turns; a save that waited behind a submit then fails with `not_draft`.

## API (under `/api/setup/`)

- `POST gradebooks/{id}/submit/`, `…/withdraw/`, `…/approve/`, `…/return/ {comment}`, `…/reopen/ {reason}`: each checks its matrix action as in the table, then the from-state. Errors (400, declared in OpenAPI): `{"status": ["wrong_state"]}`, `{"status": ["own_submission"]}`, `{"cells": [{column, student}]}` with code `incomplete` for submit, `{"comment": ["required"]}`, `{"constraint": [name]}` for a rule only the database holds. 403 for the wrong role. Each returns the gradebook detail.
- `GET gradebooks/{id}/` adds `status`, `steps` (oldest first: action, by name, at, comment), `return_comment` (the latest step's comment when it is a `return`, else null) and `can` (the steps this member may take now: same checks as the endpoints, so the screen shows only those buttons).
- `GET gradebooks/?to_review=1`: `submitted` gradebooks the member may review (`gradebook.review` through the engine), without those they submitted themselves. Newest submit first.
- `GET gradebooks/mine/`: each gradebook gains `status` and whether its latest step is a `return`.

Comments and reasons are read by `scores.view` readers (the teacher, the homeroom teacher, reviewers); they never reach Guardians or students (slice 8 shows released scores only).

## Screens

- **Gradebook** (`/gradebook/$gradebookId`): the mini lifecycle beside the title, three chips Đang nhập, Chờ duyệt, Đã khoá with the current one inked. The latest return comment in a red-ink box above the grid (who and when under it) until resubmitted. Actions from `can`, beside Lưu:
  - teacher: Nộp sổ (filled, asks first; an `incomplete` answer marks the empty cells in red ink with "Chưa có điểm"); while submitted the cells lock and the action becomes Rút lại để sửa (secondary).
  - reviewer: Duyệt (filled, asks first) and Trả lại (red outline), which opens a comment field that must be filled (as Từ chối on a leave request).
  - principal board with the duty, on a locked gradebook: Mở lại (red outline), with a reason field that must be filled; the dialog says every change after it is logged.
  - The steps as a short list under the grid (Đã nộp, Đã rút lại, Trả lại, Đã duyệt, Mở lại; who, when, the comment).
- **Teacher home**: **Cần cô xử lý** adds a pinned ticket per returned gradebook of the teacher (subject, class, term, the comment in red ink, Mở sổ) and per gradebook waiting for this member's review (subject, class, term, "Nộp bởi …", Mở sổ to review in the grid). **Hồ sơ khác của cô**: Đang nhập = draft, Chờ người khác = submitted, Đã khoá = approved.
- `DESIGN.md` § Screens, Gradebook grid: drop "the lifecycle chip shows Đang nhập only until the workflow is built" and record the above.

## Not in this slice

Students exempted from a subject or a column (an empty cell blocks submit until 1b decides exemptions); notifying anyone of a step by email or push (slice 7); a deadline per term for submitting; bulk approve of many gradebooks; reopening only some columns; averages and ratings (phase 1b); carried results of transferred students (slice 6).
