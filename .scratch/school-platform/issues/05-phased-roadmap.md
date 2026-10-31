# Which features belong to each phase of the roadmap?

Type: grilling
Status: resolved
Blocked by: 01, 04, 10, 11

## Question

Turn the feature list into phases ordered by dependency, starting with the MVP for Lower/Upper Secondary at private and multi-level Schools. For each phase: the features, the acceptance bar that says the phase is done, and what the next phase depends on from it. Decide what is in the MVP and what is not (e.g. is attendance in? is the exam bank?). Output: `docs/roadmap.md`.

## Comments

- Round 1 (owner), all as recommended: phases 0 Foundation, 1 MVP Lower/Upper Secondary, 2 Primary, 3 Online tests (question bank, 15/30-minute quizzes, shared subject-node schema with KaTeX + mhchem), 4 Lessons (reuses that schema, adds JSXGraph/Ketcher/3Dmol), 5 Extracurricular + Zalo/SMS notices, 6 Preschool. MVP includes manual timetable with clash checks (needed for per-period attendance), notices in-app + email, manual onboarding and billing outside the system. A phase is done when at least one pilot School runs it for a full term with no paper or Excel in parallel and no lost or wrong scores. Two research tickets opened (digital report card, national education database); round 2 waits on them.
- Round 2 (owner), all as recommended: a scoped digital report card slice in the MVP; one signing provider (the pilot School's, remote signing preferred); Ministry reporting by Excel export; a task ticket to obtain Ministry specs; Ministry IDs, national ID, status history and per-year records from Phase 0; the principal board applies the School's organisational signature; Phase 1 ships as 1a (start of term) and 1b (end of term).

## Answer

`docs/roadmap.md`. Phase 0 Foundation (tenancy, accounts, setup, expensive-later data fields, import, audit, observability, component set); Phase 1 MVP Lower/Upper Secondary in two releases (1a: records, timetable, attendance, leave requests, gradebook workflow, Guardian portal, notices; 1b: averages and ratings, conduct, digital report card slice with signing chain and XML/PDF, Ministry Excel reports); Phase 2 Primary; Phase 3 online tests and question bank; Phase 4 lessons; Phase 5 extracurricular + Zalo/SMS; Phase 6 Preschool. A phase is done after a pilot School runs it for a full term without paper and with no lost or wrong scores. API sync with the Ministry waits on the specs (ticket 12). Signing rows added to `docs/roles.md`.
- Amendment (owner, after resolution): phases overlap. Development of the next phase does not wait for the previous phase's acceptance; during each pilot, feedback from several sources keeps adding features, upgrades and fixes. Recorded in `docs/roadmap.md` (Phases overlap, Feedback during every pilot).
