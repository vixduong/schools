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

## Not yet specified

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
