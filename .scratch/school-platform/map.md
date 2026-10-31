# Map: School Platform — planning

Label: wayfinder:map

## Destination

An English planning package, ready to hand off to implementation: (a) a phased roadmap where each phase is a list of features, (b) a tech-stack analysis recorded as ADRs, (c) a design system built with /hallmark from the statechart-art reference, and (d) a clickable UI prototype. No application code.

## Notes

- Domain: multi-tenant SaaS for Vietnamese schools, one codebase; read `GLOSSARY.md` and `docs/adr/` first.
- Docs in English; UI copy in Vietnamese.
- Settled during charting: tenant = School (ADR 0001); Assessment Profile per Level; level order Lower/Upper Secondary (MVP) → Primary → Preschool; first customers are private and multi-level schools on subscription; team of 1–2 devs, phases ordered by dependency, no time estimates.
- Stack chosen by the user before charting: backend Django + DRF; frontend TanStack (Router/Query/Table) + Tailwind + shadcn/ui; Postgres 16 with RLS; Cloudflare in front (DNS/CDN/WAF/Pages), files in S3-compatible storage (R2 by default).
- Style direction: the statechart-art look (warm paper, typewriter serif, italic labels, pinned ticket cards, pastel pencil regions, red ink) is a **brand layer**: ticket cards for states, pastel regions per Level/role, red ink for warnings only; data tables stay clean sans with tabular numbers; illustrations only in empty states, onboarding, parent portal, Preschool. Reference images: `docs/design/reference/` (order, day, counter, bug).
- Prototype: static clickable HTML, 5 screens — login by School, teacher dashboard, gradebook, student profile, parent view.
- Any design decision made while resolving a ticket updates `DESIGN.md` in the same change.
- Skills: `/hallmark` for design tickets, `/prototype` for prototype tickets, `/grilling` + `/domain-modeling` for grilling tickets, `/research` for research tickets. Ponytail principles: smallest complete plan, no speculative features.

## Decisions so far

<!-- one line per closed ticket: [title](link): gist -->
- [What do Vietnamese law and public-school buyers require of where student data is stored?](issues/02-data-residency-and-privacy.md): no localization duty under PDPL 91/2025 and Decree 356/2025; Singapore + R2 is fine for private Schools with a transfer-impact filing and parent consent; public Schools need a Vietnam-hosted option.
- [What are the current versions and proven patterns for the chosen stack?](issues/03-stack-versions-and-tenancy-patterns.md): Django 5.2 LTS + DRF 3.18; RLS through a transaction-local `set_config`; same-origin `<school>.app.vn/api` with a session cookie and CSRF; a Postgres-backed task queue only for bulk work.

- [Which Vietnamese assessment regulations must each Assessment Profile encode?](issues/01-assessment-regulations.md): Circular 22/2021 for secondary (weighted semester average, 4-level ratings), Circular 27/2020 for primary (3-level subject ratings plus integer test scores, no averages), free-form preschool; Circular 89/2026 lands 1 Dec 2026, so profiles are versioned by effective date.
- [What are the design conventions of the brand layer, built with /hallmark?](issues/07-design-system.md): approved; pinned tickets on statecharts, pen blue for action, red ink for warnings, a pencil pastel per Level, Hepta Slab + Be Vietnam Pro, plain working surfaces; dark mode, data table, combobox and date pickers specified too.
- [Which libraries can teachers use to build lesson content for maths, geometry, physics, chemistry and biology?](issues/09-lesson-authoring-libraries.md): Tiptap JSON in jsonb with subject nodes (KaTeX + mhchem, JSXGraph, Ketcher, 3Dmol.js), each with source + SVG snapshot; GeoGebra, Desmos, ChemDoodle and live PhET left out on licence.
- [Who are the users, and what may each role see and change?](issues/04-roles-and-permissions.md): one global Account, a Membership per School, permissions from scoped Role Assignments; eight MVP roles; students of Lower/Upper Secondary take teacher-published tests (15/30-minute quizzes need no approval, periodic tests do); matrix in `docs/roles.md`.
- [What does the final tech-stack analysis record, and which choices become ADRs?](issues/06-tech-stack-analysis.md): Django 5.2 LTS + DRF, RLS fail-closed (verified on PG16), Postgres-backed tasks; React + TanStack (incl. Form) + shadcn; same-origin session auth; Singapore + R2; OpenTelemetry → Grafana Cloud Singapore; `docs/tech-stack.md`, ADRs 0003–0006.
- [What does the digital report card (học bạ số) require of a school system from 2027?](issues/10-digital-report-card.md): mandatory from 8 Oct 2026 under Circular 70/2026; personal signatures (subject teacher, homeroom, principal) plus the School's; sync to the national database; MVP takes a scoped slice, while live submission waits for the official spec.
- [Must the platform sync with the national education database, and how?](issues/11-national-education-database.md): reporting is mandatory (Circular 42/2021, contents from Circular 25/2024); the MVP exports Ministry-shaped Excel and carries national IDs and status history; API sync needs the Ministry spec (Decision 4998) and a connection, which digital report cards will also need.
- [Which features belong to each phase of the roadmap?](issues/05-phased-roadmap.md): Phase 0 Foundation, 1 MVP secondary (1a start of term, 1b end of term incl. digital report card slice and Ministry Excel), 2 Primary, 3 online tests, 4 lessons, 5 extracurricular + Zalo/SMS, 6 Preschool; done = a pilot School runs it a full term; `docs/roadmap.md`.

## Not yet specified

<!-- empty: the roadmap placed every remaining patch in a phase; detail beyond this map is listed under Out of scope -->

## Out of scope

- Writing application code (this map ends at the planning package).
- Aggregated reporting across a School Chain (each member is its own School).
- Native mobile apps; live/online classes; AI grading or AI question generation.
- Detailed specs for phases 3 to 6 (question bank metadata and exam matrix, the JSXGraph board JSON spec, extracurricular rules, Zalo/SMS cost model, Preschool module): each is specified when its phase starts, as its own effort; placement is in `docs/roadmap.md`.
- Importing from other school systems (VNEdu, SMAS), a setup wizard, self-serve billing: after the MVP per `docs/roadmap.md`.
