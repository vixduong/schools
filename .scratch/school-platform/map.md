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
- Skills: `/hallmark` for design tickets, `/prototype` for prototype tickets, `/grilling` + `/domain-modeling` for grilling tickets, `/research` for research tickets. Ponytail principles: smallest complete plan, no speculative features.

## Decisions so far

<!-- one line per closed ticket: [title](link): gist -->
- [What do Vietnamese law and public-school buyers require of where student data is stored?](issues/02-data-residency-and-privacy.md): no localization duty under PDPL 91/2025 and Decree 356/2025; Singapore + R2 is fine for private Schools with a transfer-impact filing and parent consent; public Schools need a Vietnam-hosted option.
- [What are the current versions and proven patterns for the chosen stack?](issues/03-stack-versions-and-tenancy-patterns.md): Django 5.2 LTS + DRF 3.18; RLS through a transaction-local `set_config`; same-origin `<school>.app.vn/api` with a session cookie and CSRF; a Postgres-backed task queue only for bulk work.

- [Which Vietnamese assessment regulations must each Assessment Profile encode?](issues/01-assessment-regulations.md): Circular 22/2021 for secondary (weighted semester average, 4-level ratings), Circular 27/2020 for primary (3-level subject ratings plus integer test scores, no averages), free-form preschool; Circular 89/2026 lands 1 Dec 2026, so profiles are versioned by effective date.
- [What are the design conventions of the brand layer, built with /hallmark?](issues/07-design-system.md): approved; pinned tickets on statecharts, pen blue for action, red ink for warnings, a pencil pastel per Level, Hepta Slab + Be Vietnam Pro, plain working surfaces; dark mode, data table, combobox and date pickers specified too.

## Not yet specified

- Lesson authoring: the editor, how subject blocks (formulas, geometry, simulations, molecules) are stored and shared between lessons and the exam bank, and in which phase it lands.
- Exam bank and test generation: question metadata, exam matrix, shuffling, how marks flow into the gradebook. Depends on the roadmap phase it lands in.
- Extracurricular activities: registration, capacity, conduct points, parent consent.
- Preschool module: daily log, meals, health, pick-up; how much it shares with the core.
- Notifications channel to parents (Zalo ZNS, SMS, email, PWA push) and its cost model.
- School onboarding: data import from Excel / VNEdu / SMAS, School setup wizard, subscription billing.
- Reporting obligations to education authorities (Sở/Phòng GD, national education database sync).
- Timetable: manual entry with conflict checks; auto-scheduling stays out unless a phase needs it.

## Out of scope

- Writing application code (this map ends at the planning package).
- Aggregated reporting across a School Chain (each member is its own School).
- Native mobile apps; live/online classes; AI grading or AI question generation.
