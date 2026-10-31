# What does the final tech-stack analysis record, and which choices become ADRs?

Type: grilling
Status: resolved
Blocked by: 02, 03

## Question

Using the research on data residency and on stack versions/patterns, write the tech-stack analysis: frontend/backend split, hosting topology, storage choice (R2 vs in-country), auth approach, async work, observability, backups. Decide which choices are hard to reverse enough to deserve ADRs. Output: `docs/tech-stack.md` plus ADRs.

## Answer

Approved by the owner with two changes: TanStack Form instead of React Hook Form, and a full observability system (collect, aggregate, monitor). Recorded in `docs/tech-stack.md` and ADRs 0003 to 0006.

- Backend Django 5.2 LTS + DRF 3.18 + drf-spectacular; RLS via a transaction-local `set_config` with `NULLIF` fail-closed policies; Postgres-backed tasks via `django-tasks` + `django-tasks-db`; openpyxl, WeasyPrint.
- Frontend React + Vite, TanStack Router/Query/Table/Form, Zod, Tailwind v4 + shadcn/ui, generated OpenAPI client; Tiptap for content in phases 3 and 4.
- Same-origin session auth per School (ADR 0003); Singapore + R2, portable, Vietnam hosting on demand (ADR 0004); content as Tiptap JSON with source + SVG per block (ADR 0005); Assessment Profiles versioned by effective date (ADR 0006).
- Observability: OpenTelemetry + Faro → Grafana Alloy (PII scrubbing) → Grafana Cloud Singapore (Loki, Prometheus/Mimir, Tempo, alerting, synthetic checks), with a defined alert set.
- Verified the same day: RLS fail-closed on Postgres 16.15 (NULLIF required), wildcard subdomains on Cloudflare without Enterprise, the 125 s origin timeout, TanStack Form + Zod.
