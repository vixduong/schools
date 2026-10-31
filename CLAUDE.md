# School Platform

Multi-tenant school management SaaS for Vietnamese schools. Planning stage: no application code yet.

- Read `GLOSSARY.md` and `docs/adr/` before naming domain concepts.
- Planning map: `.scratch/school-platform/map.md` (run `/wayfinder` on it).
- Design: `DESIGN.md` is the locked design system. Any UI or design decision updates `DESIGN.md` in the same change (and the specimen in `docs/design/specimen/` when it shows that pattern). Run `/hallmark` for UI work; it reads `DESIGN.md` first.
- Docs are in English; UI copy is in Vietnamese. Everything in code is English: route paths and names (`/login`, not `/dang-nhap`), API paths, identifiers, file names.
- Commit as soon as a plan is written or a slice is implemented and its checks pass, before review; review fixes land as their own commits.
- Research findings behind decisions are in `docs/research/`; the planning map and its tickets are in `.scratch/school-platform/`.
- Run `make hooks` once per clone (fast lint and typecheck on commit). For a reviewer agent, which cannot run git, hand it `make review-diff BASE=<sha> NAME=<slice>`.
