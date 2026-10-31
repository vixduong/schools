# Roadmap

Decided in the ticket *Which features belong to each phase of the roadmap?* (`.scratch/school-platform/issues/05-phased-roadmap.md`). Phases are ordered by dependency, without time estimates; the team is 1–2 developers. Terms follow `GLOSSARY.md`; roles and permissions follow `docs/roles.md`; the stack follows `docs/tech-stack.md`; the UI follows `DESIGN.md`.

**Done means**: at least one pilot School runs the phase's features for a full term with no paper or Excel kept in parallel, and no lost or wrong scores. Phase 0 has no pilot; it is done when phase 1a can be built on it without changing its model.

**Phases overlap.** "Done" is an acceptance gate for a phase, not a start gate for the next one: development of the next phase starts as soon as its build dependencies exist, while the current phase is still in its pilot term. Waiting a full term between phases would leave the team idle. Order still follows dependencies (what a phase reuses must be built first), and a phase is offered to more Schools only after its own acceptance.

**Feedback during every pilot.** While a phase is being accepted, feedback keeps flowing into the plan from several sources:

- the pilot School: teachers, the principal board, Guardians and students, through an in-app feedback form on every screen and a short check-in with the School each fortnight;
- support requests and the operator's own use;
- observability: errors, slow pages and failed tasks from Grafana alerts;
- regulation changes (new circulars) and Ministry specification updates.

Every item is triaged into one queue in this order: **(1)** anything that loses or corrupts scores, records or signatures, fixed at once; **(2)** what blocks the pilot School's daily work; **(3)** regulation changes with a deadline; **(4)** improvements and new features, scheduled into the current or a later phase. Fixes and improvements ship continuously; nothing waits for a phase boundary.

**First customers**: private and multi-level Schools, by subscription, onboarded by hand.

## Phase 0: Foundation

What every later phase stands on.

- Tenancy: one School per tenant, `school_id` + Postgres RLS, fail-closed policies, policy-coverage check in CI (ADR 0001).
- Accounts, Memberships, Role Assignments by scope and school year (ADR 0002); sign-in per School subdomain with session cookies (ADR 0003); Guardian invite codes.
- School setup: school years, terms, Levels, Grades, classes, subjects, subject groups, rooms; Role Assignments for the year.
- Data model rules that are expensive to add later: Ministry IDs for School, students and teachers; national personal ID; status history instead of deletes (a student who leaves or transfers changes status); records kept per school year; Assessment Profiles versioned by effective date (ADR 0006).
- Excel import of staff, students and Guardians with a row-error preview and one-transaction commit.
- Audit log; operator support access granted by the School, time-limited and logged.
- Observability (OpenTelemetry → Grafana Cloud Singapore, alerts), backups with a restore drill.
- Frontend shell and component set from `DESIGN.md` (both modes); permission matrix as tests.
- Operator tools: create a School, its subdomain and its first School admin.

## Phase 1: MVP for Lower and Upper Secondary

Shipped in two releases inside the pilot's first term.

### 1a, ready for the start of term

- Student and Guardian records, linked; Enrollment per year and class.
- Timetable entered by hand, with clash checks on teacher and room.
- Attendance per period by the subject teacher; overview for the homeroom teacher.
- Leave requests from Guardians, approved by the homeroom teacher (a ticket with a lifecycle).
- Gradebook per Circular 22/2021: score columns by periods per year, comment-only subjects, entry with validation, the submit → approve or return → lock workflow, reopen by the named principal board member with a reason, every change logged.
- Guardian portal (PWA): scores once released, attendance, timetable, notices, leave requests.
- Student accounts (read-only in this phase): scores once released, timetable, notices.
- Notices in the app and by email, by the senders allowed in `docs/roles.md`.

### 1b, ready for the end of term

- Semester and year averages, learning ratings and promotion rules from the Assessment Profile version in force.
- Conduct rating by the homeroom teacher.
- Digital report card, scoped slice (Circular 70/2026): per-year record, the signing chain (subject teacher, homeroom teacher, principal, then the School's organisational signature), audit trail, XML + PDF output, transfer to another School with consent. One signing provider, the one the pilot School uses, preferring remote signing.
- Ministry reporting: Excel export in the Ministry import template shape for the start-of-year (30/10) and end-of-year (30/6) reports.
- Report card PDFs per class as background tasks, stored in object storage.

**Depends on Phase 0. Gives Phase 2**: the gradebook workflow, the Assessment Profile machinery and the report card pipeline, which Primary reuses.

## Phase 2: Primary

- Assessment Profile for Circular 27/2020: Achievement Levels per subject at four checkpoints, ratings of qualities and competencies, integer test scores; no averages.
- Primary gradebook and comment entry; the same workflow and signing chain; Primary report card.
- Guardians act for Primary students (no student accounts).

**Why second**: multi-level Schools, the first customers, nearly all teach Primary.

## Phase 3: Online tests and question bank (Lower and Upper Secondary)

- Question bank per subject group: Tiptap content with KaTeX + mhchem (ADR 0005), metadata for subject, Grade, chapter and difficulty.
- Tests: regular (incl. 15 and 30-minute quizzes) published by the subject teacher; periodic tests approved by the group leader first.
- Taking a test: time window, duration, attempt limit, shuffled questions and answers; auto-graded objective items, teacher-graded written items.
- Release of results; answers only if the teacher chooses; push into a chosen gradebook column, then the gradebook workflow.

**Gives Phase 4**: the subject-node schema and the editor.

## Phase 4: Lessons

- Lesson authoring on the Phase 3 editor, adding JSXGraph boards (our own JSON spec), Ketcher structures, 3Dmol.js molecules, labelled images.
- Publishing to classes; a shared library per subject group.
- Print and Word export (Pandoc or `docx`), PDF.

## Phase 5: Extracurricular and paid notification channels

- Activities: registration, capacity, approval, attendance, conduct points, Guardian consent.
- Notices through Zalo ZNS and SMS, with per-School cost control.

## Phase 6: Preschool

- Developmental observation across five domains, daily log, meals, health, pick-up, Guardian portal for Preschool.

## After the phases, when a customer needs it

- API sync with the national education database and live digital report card submission, VNeID lookup, revocation and re-issue. Blocked on obtaining the current Ministry specification (ticket *Obtain the Ministry's current technical specifications for the education database and digital report cards*).
- Vietnam-hosted deployment for public Schools (ADR 0004).
- Self-serve School sign-up and in-app billing, once about ten Schools are live.
- Clerical staff, accountant and nurse roles; finance (tuition); two-way messaging.
