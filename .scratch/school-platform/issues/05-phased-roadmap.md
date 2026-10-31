# Which features belong to each phase of the roadmap?

Type: grilling
Status: claimed
Blocked by: 01, 04, 10, 11

## Question

Turn the feature list into phases ordered by dependency, starting with the MVP for Lower/Upper Secondary at private and multi-level Schools. For each phase: the features, the acceptance bar that says the phase is done, and what the next phase depends on from it. Decide what is in the MVP and what is not (e.g. is attendance in? is the exam bank?). Output: `docs/roadmap.md`.

## Comments

- Round 1 (owner), all as recommended: phases 0 Foundation, 1 MVP Lower/Upper Secondary, 2 Primary, 3 Online tests (question bank, 15/30-minute quizzes, shared subject-node schema with KaTeX + mhchem), 4 Lessons (reuses that schema, adds JSXGraph/Ketcher/3Dmol), 5 Extracurricular + Zalo/SMS notices, 6 Preschool. MVP includes manual timetable with clash checks (needed for per-period attendance), notices in-app + email, manual onboarding and billing outside the system. A phase is done when at least one pilot School runs it for a full term with no paper or Excel in parallel and no lost or wrong scores. Two research tickets opened (digital report card, national education database); round 2 waits on them.
