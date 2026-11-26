# Phase 1b, slice 1: Averages

Slice 1 of `docs/phase-1b.md`. Standing rules: `backend/CODING_STANDARDS.md`, `frontend/CODING_STANDARDS.md`, `docs/slices/README.md`, the Constraints sections of `docs/phase-0.md`, `docs/roles.md` (row "See scores", rule "Least data"), `docs/research/assessment-regulations.md` (Circular 22/2021 Art. 7 to 9), ADR 0006, `DESIGN.md` § Screens (gradebook). Builds on 1a slices 4 to 6 (gradebook entry, workflow, mid-year transfers) and changes two of their rules, named under Model.

Two parts, built and committed in order, each by one worker: **Part A, backend** (migration, calculation, API) and **Part B, frontend** (grid, dialog, docs). Part B starts from Part A's regenerated client.

Done when a gradebook's grid shows each student's semester average (and, in the second semester's gradebook, the year average) and every case of the fixture table matches to one decimal, with the draft, submitted, approved, carried, comment-only, left and split cases each behaving as stated.

## Terms

- **Semester average** (ĐTBmhk), scored subjects: `(sum of regular scores + 2 × mid-term + 3 × end-term) / (number of regular columns + 5)`, one decimal. **Year average** (ĐTBmcn): `(semester 1 average + 2 × semester 2 average) / 3`. Weights come from the profile version the gradebook is pinned to (`rules.weights`, `rules.semester_average`, `rules.year_average`); never written in code.
- **Comment-only subject**: Đạt when the required number of assessments is entered and all assessments of the book (regular, mid-term, end-term) are Đạt, otherwise Chưa đạt (Art. 9.1.a); the year result equals semester 2's.
- **Semester 2 gradebook**: its term has exactly one earlier term in the same school year ("earlier" = another term of the year with `ends_on` before this term's `starts_on`; `Term` has no ordinal) and the year has exactly two terms. A year with another number of terms gets no year average (state `unavailable`, reason `terms`).
- **Average state**, per student per gradebook: `final` (approved), `provisional` (draft or submitted, every required cell filled), `missing` (draft or submitted, a required cell empty: no value, the empty columns listed), `left`, `split`, `unavailable` (the profile version lacks a key the calculation needs, or the term rule above fails).
- **Previous semester average** (new in `GLOSSARY.md`): the first-semester average of a student who arrived in semester 2, brought from the previous School, one number per scored subject.

## Owner decisions (to confirm before code)

- **O1, rounding**: half-up to one decimal on each semester average; the year average is computed from the **rounded** semester averages (`rules.year_average_uses_rounded_semester_averages` already says so) and rounded again. The research does not state the rule.
- **O7, a carried score fills an empty cell** (replaces "missing counts 0", which cannot occur): 1a refuses to submit a gradebook while any student still in the class lacks a local score in any column (`gradebook_incomplete`, `docs/slices/1a-slice-6.md` left the exemption to 1b). So an arriving student could never be submitted without re-entering what the previous School already gave. Decision here: a column cell counts as filled when a current carried result of the same kind and index exists. A local score always wins over a carried one. The circular's "a missing item counts 0" (Art. 7.4, 7.5) then never arises for a student in the class, because submit refuses an incomplete book.

## Model

- **No new table, and the average is never stored**: it is calculated on read from the current `ScoreEntry` per cell, `CarriedResult` and the profile `rules`. No score is copied, so nothing is added to the audit log ("view only, because derived").
- **`CarriedResult` gains one kind, `previous_semester_average`** (migration `grades/0006`, additive):
  - `kind` is `max_length=10` today, and the new name is 25 characters: the migration widens it to 30 (`AlterField`, reversible), with a round-trip test.
  - `index` 1, `value` only. The existing CHECK `carriedresult_kind_is_known` is replaced to list the kind; `carriedresult_periodic_is_single` already requires `index = 1`.
  - New trigger `carriedresult_previous_average_fits` (cross-table): only a scored subject (a comment-only subject needs no first-semester figure), and only when the term has an earlier term in its school year (rule under Terms). The existing triggers `student_arrived_in_term` and `gradebook_open` apply to it unchanged, so it can be entered only while the gradebooks of that term and subject are drafts.
  - Audit: none, as the other carried results.
- **`gradebook_incomplete` (SQL function of `grades/0003`) is replaced** in the same migration so a column cell is filled by a current local entry or a current carried row of the same `(kind, index)` for that student, term and subject; the Python `empty_cells` (`views.py`, the list the submit error returns) is changed to the same rule. `previous_semester_average` fills no column. The migration follows `0005`: reverse SQL for every operation, grants unchanged (INSERT and SELECT only). The reverse fails once a `previous_semester_average` row exists (0005's kind CHECK and the 10-character column cannot hold it, and carried rows are never deleted).

## Calculation (`backend/grades/averages.py`, pure functions)

No ORM and no clock: inputs are plain values (rules, required columns, per-column values, status, `left`), output is `Average(value, result, state, missing, carried, reason)`. `average_data.py` gathers the inputs for a gradebook's roster and calls it.

- The rounding mode is `getattr(decimal, rules["rounding"])`, passed to `quantize` explicitly; never the context default (half-even).
- `n` is the gradebook's own regular column count (derived from the profile and the subject's periods per year when it was opened).
- A column's value: the current local entry, else the current carried row of the same `(kind, index)`, else empty. Averages are `final` only on an approved book, where every cell of a student in the class is filled by the workflow.
- **Precedence of states** for one student and gradebook: `unavailable` (rules or terms) > `split` > `left` > `missing` > `provisional` > `final`. `split` = the student is on the roster of two gradebooks of the same subject and term (they changed class in the term); the two are not combined (see Not in this slice). `left` = the student's enrolment in this class ended before the term ended; no value. A class change at the term boundary, a school year that has ended and an arrival dated later in the term are not `left`.
- **Year average** (semester 2 gradebook only): semester 1 comes from the student's own semester 1 gradebook of the same subject (any class), or, when the student has none, from the `previous_semester_average` (state `final`, `carried: true`); a local semester 1 gradebook wins over a carried figure. Neither present: `missing`, reason `no_previous_average`. The year state is the worse of the two semesters by the order above; it has a value only when the worse is `final` or `provisional`.
- A profile version missing a needed key gives `unavailable`, never a guess (schema 1 has every key today, so the test crafts a rules dict).

## API

- `GET /api/gradebooks/<id>/` (the existing detail): each row gains `averages: {semester, year}` (`year` null outside a semester 2 book; a comment-only subject returns `result` `pass`/`fail`). Same permission (`CanUseGradebook`, a teaching pair): a Student or Guardian reaches no gradebook endpoint, and the portal shows averages only in slice 10. No matrix change.
- Carried `PUT` (`CarriedView.put`): accepts kind `previous_semester_average`, `index` 1, `value`. The `unknown_column` check still refuses every other pair that is not a column; this kind is the one exception, and only for a gradebook of a later term. The grid's per-column carried cells ignore it (it has no column); `transfer_view` returns it and the dialog shows it.
- Query count is bounded: 30 students, a semester 2 book, a fixed number of queries.
- OpenAPI regenerated (`make api-client`).

## Screen (Part B)

- The grid gets read-only columns after the score columns and before the arrivals column, in the pattern of the carried cell (`tabular-nums`, an `aria-label` per cell): **ĐTB** and, in a semester 2 book, **Cả năm**; for comment-only subjects **Kết quả** (Đạt / Chưa đạt). `final` plain ink; `provisional` italic with "tạm"; `missing` shows "—" with the empty columns in the cell's title and screen-reader label; `left`, `split` and `unavailable` show "—" with the reason in the title; `no_previous_average` shows "Chưa có TB học kỳ trước" in red ink on the year cell of an arriving student.
- The mid-year transfer dialog gets a row **TB học kỳ trước** for a scored subject of a semester 2 gradebook.
- Vietnamese copy; decisions go to `DESIGN.md` § Screens in the same change; `GLOSSARY.md` gets Semester average, Year average, Previous semester average.

## Fixture (the independent check)

Circular 22/2021 profile, three regular columns (n = 3), half-up. Expected values were computed with Python `Decimal` outside the repo by the plan's author and re-derived independently by a reviewer; the implementer writes the tests from this table first, in `backend/grades/tests/fixtures/averages_cases.json`.

| Case | Inputs | Expected |
|---|---|---|
| A, plain | regular 8.0, 7.0, 9.0; mid 6.5; end 7.5; approved | 59.5 / 8 = 7.4375 → **7.4**, `final` |
| B, half-up boundary | regular 7.0, 7.0, 7.0; mid 5.0; end 9.0; approved | 58 / 8 = 7.25 → **7.3** (half-even gives 7.2) |
| C, year from rounded semesters | S1: regular 6, 6, 6; mid 6.5; end 7.0 → 6.5. S2: regular 6, 6, 9; mid 8.0; end 8.0 → 7.625 → 7.6. Both approved | (6.5 + 2 × 7.6) / 3 = 7.2333 → **7.2** (unrounded S2 would give 7.3) |
| D, arrival in semester 2 | previous semester average 6.9; S2 average 8.0, approved | (6.9 + 2 × 8.0) / 3 = 7.6333 → **7.6**, S1 `carried: true` |
| E, arrival in semester 1 | carried regular 1 = 7.0 (no local); local regular 2 = 8.0, 3 = 9.0; mid 6.5; end 7.5; approved | 59.5 / 8 → **7.4**, `final` |
| M, local over carried | carried regular 1 = 5.0 and local regular 1 = 7.0; rest as E | 7.4: the local 7.0 is used |
| K, provisional | as A, status draft | **7.4**, `provisional` |
| F, missing in a draft | as A with end-term empty, draft | value null, `missing`: end-term |
| L, year provisional | S1 approved 6.5; S2 draft with every cell filled giving 7.625 → 7.6 | year **7.2**, `provisional` |
| N, year without a first semester | arrival in semester 2, no previous average entered | year null, `missing`, `no_previous_average` |
| H, comment-only | all assessments of the book (2 regular, mid-term, end-term): all Đạt → Đạt; a regular Chưa đạt → Chưa đạt; end-term Chưa đạt, the rest Đạt → Chưa đạt (H6); one empty, draft → `missing`; carried Đạt + local Đạt → Đạt; year = semester 2's | as stated |
| I, left | student with the row read-only after leaving | `left`, no value |
| J, split | the student on the roster of two gradebooks of one subject and term | `split` in both (wins over `left`) |
| O, terms | a school year with one term, and one with three | year average `unavailable`, reason `terms`; semester averages still computed |

## Checks (each runs on its own)

1. `make check` green.
2. `pytest backend/grades/tests/test_averages.py`: the pure module against the fixture, no database; case B red under half-even and case C red under unrounded semesters, shown with `make red`.
3. API and migration tests (`test_average_rows.py`): the grid carries `averages` in draft, submitted and approved books; carried `previous_semester_average` round-trips (the widened column), is accepted for a scored subject of a later term, and refused (API and a direct insert hitting the trigger) for the first term, a comment-only subject and a student who did not arrive in the term; `gradebook_incomplete` and the submit error treat a carried cell as filled and still refuse a truly empty one; a Student and a Guardian get 403 on the detail; query count fixed at 30 students.
4. Frontend tests for each state; the dialog row only in a semester 2 scored book; screenshots at 375 px and desktop, light and dark, viewed.
5. A reviewer re-derives every fixture row from the circular's formulas without reading the implementation (done for this table; repeated if it changes).

## Files

- **Part A:** new `backend/grades/averages.py`, `average_data.py`, `migrations/0006_previous_semester_average.py`, `tests/test_averages.py`, `tests/test_average_rows.py`, `tests/fixtures/averages_cases.json`; changed `backend/grades/models.py`, `views.py` (`detail`, `CarriedView.put`, `empty_cells`, and, a deviation found in review, `ColumnReleaseView.post`: a current carried row of the column's kind and index counts as filled, as in `empty_cells`), `serializers.py`, `frontend/src/api/openapi.json` and `schema.d.ts` (generated), `docs/phase-1b.md` (row 1 and O7). Deviation: one filter in `frontend/src/components/gradebook-grid.tsx` (the per-column carried cell skips `previous_semester_average`) lands in Part A so the regenerated client typechecks.
- **Part B:** changed `frontend/src/components/gradebook-grid.tsx`, the transfer dialog component, `frontend/src/lib/grades.ts`, frontend tests, `DESIGN.md`, `GLOSSARY.md`.

## Not in this slice

- Schema 2 of the profile `rules` (conduct levels, promotion conditions): slices 3 and 4 add the keys they read.
- Learning ratings, promotion, conduct, awards (slices 3 and 4); the semester lock (slice 2); averages on the Guardian or student view (slice 10); a stored or exported average.
- Combining one subject's cells from two gradebooks after a mid-term class change: the state is `split`.
- Entering a `previous_semester_average` after the semester 2 gradebook is submitted: the existing `gradebook_open` trigger refuses it, so a missing figure is fixed by reopening the book (audited, 1a slice 5); a submit warning for it is left to a later slice.
- Re-assessment after summer training and its effect on the year average.
- A `previous_semester_average` is accepted for any term with an earlier term in its year, a year of three terms included, although such a year shows no year average (`terms`): harmless, left as is.
