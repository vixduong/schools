# School Platform

Multi-tenant school management SaaS for Vietnamese schools. Phase 0 (`docs/phase-0.md`) is built, Phase 1a is in progress: Django API in `backend/`, React SPA in `frontend/`, one plan per slice in `docs/slices/`.

- Read `GLOSSARY.md` and `docs/adr/` before naming domain concepts.
- Build plan: `docs/phase-1a.md` (current phase); slice plans in `docs/slices/`, written per `docs/slices/README.md`. The planning map (`.scratch/school-platform/map.md`) is closed.
- Design: `DESIGN.md` is the locked design system. Any UI or design decision updates `DESIGN.md` in the same change (and the specimen in `docs/design/specimen/` when it shows that pattern). Run `/hallmark` for UI work; it reads `DESIGN.md` first.
- Docs are in English; UI copy is in Vietnamese. Everything in code is English: route paths and names (`/login`, not `/dang-nhap`), API paths, identifiers, file names.
- Commit as soon as a plan is written or a slice is implemented and its checks pass, before review; review fixes land as their own commits.
- Research findings behind decisions are in `docs/research/`; the planning tickets are in `.scratch/school-platform/issues/`.
- Run `make hooks` once per clone (fast lint and typecheck on commit; `make check`, which includes `make smoke`, on push). For a reviewer agent, which cannot run git, hand it `make review-diff BASE=<sha> NAME=<slice>` and point it at `backend/CODING_STANDARDS.md` (and `frontend/CODING_STANDARDS.md` for frontend changes).
