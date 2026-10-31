# Tech stack

Decided in the ticket *What does the final tech-stack analysis record, and which choices become ADRs?* (`.scratch/school-platform/issues/06-tech-stack-analysis.md`). Evidence: the research files on branches `research/stack-versions-and-tenancy-patterns`, `research/data-residency-and-privacy`, `research/lesson-authoring-libraries`. Hard-to-reverse choices are ADRs in `docs/adr/`.

## Shape

```
Browser ── <school>.app.vn ──► Cloudflare (DNS, TLS, WAF, CDN)
                                 ├─ /*      → SPA static assets (Workers static assets, wildcard route)
                                 └─ /api/*  → Django API (VPS, Singapore)
                                                ├─ Postgres 16 (RLS per School)
                                                ├─ task worker (same codebase, Postgres-backed queue)
                                                └─ object storage, S3-compatible (R2, apac hint)
```

One repository, two apps: `backend/` (Django) and `frontend/` (React). The contract between them is the OpenAPI schema the backend generates; the frontend imports nothing from the backend.

## Backend

| Concern | Choice | Why |
|---|---|---|
| Framework | Django **5.2 LTS** + DRF 3.18, psycopg 3 | LTS until Apr 2028 and CI-tested by every library below; move to 6.2 LTS after Apr 2027 |
| API schema | drf-spectacular → OpenAPI | the contract with the SPA; CI fails on an unreviewed schema diff |
| Tenancy | shared DB, `school_id` on every School-owned row, Postgres RLS (ADR 0001) | isolation enforced below the application |
| RLS per request | middleware opens the transaction and runs `set_config('app.school_id', …, true)`; `ATOMIC_REQUESTS` off | `ATOMIC_REQUESTS` wraps only the view, so a GUC set in middleware would be lost |
| DB roles | app role `NOBYPASSRLS`; migrations as table owner | a missed filter cannot leak |
| Fail closed | policies compare against `NULLIF(current_setting('app.school_id', true), '')`; CI test that every table with `school_id` has a policy | no GUC means no rows |
| Accounts | global Account table outside RLS; Membership and Role Assignments tenant-scoped (ADR 0002) | one person, several Schools |
| Async work | Django tasks API via `django-tasks` (backport) + `django-tasks-db` (Postgres) | no Redis; same `@task` code moves to Django 6.2's built-in API |
| Excel | openpyxl read-only import with a row-error preview, then one-transaction commit; write-only export as `FileResponse` | rosters and scores arrive in Excel |
| PDF | WeasyPrint from HTML templates, Be Vietnam Pro embedded | report cards; a class or School batch runs as a task and lands in object storage |
| Pooling | none at first (`CONN_MAX_AGE`, health checks); PgBouncer transaction mode later | the GUC is transaction-local, so pooling needs no change |

## Frontend

| Concern | Choice |
|---|---|
| App | React SPA, Vite, TypeScript |
| Routing, data | TanStack Router (state in the URL), TanStack Query, TanStack Table |
| UI | Tailwind v4 + shadcn/ui, tokens and rules from `DESIGN.md` |
| Forms | React Hook Form + Zod |
| API client | types generated with `openapi-typescript` from the backend schema |
| Dates | shadcn `Calendar` (react-day-picker), `vi` locale, weeks from Monday, `dd/MM/yyyy` |
| Content editor (phases 3 and 4) | Tiptap (MIT) storing JSON in `jsonb`; KaTeX + mhchem, MathLive; later JSXGraph, Ketcher, 3Dmol.js; each subject node keeps its source and an SVG snapshot (ADR 0005) |
| Mobile | responsive PWA; no native app in the plan |

## Auth

Same origin per School: the SPA and the API both answer on `<school>.app.vn` (`/api`). Django session cookie, host-only, `SameSite=Lax`, `Secure`, `HttpOnly`; CSRF through the `X-CSRFToken` header. No CORS, no JWT in the browser (ADR 0003). Sign-in rules and roles: `docs/roles.md`.

## Hosting, storage, data law

- API, worker and Postgres on a VPS or managed Postgres in **Singapore**; files on **Cloudflare R2** with the `apac` hint; storage behind `django-storages` so the provider is configuration (ADR 0004).
- Legal duties under PDPL 91/2025 and Decree 356/2025: file a transfer impact assessment within 60 days of the first cross-border transfer and a processing impact assessment; parent consent at enrollment; a processor contract with each School.
- Public Schools: offer a Vietnam-hosted deployment of the same codebase (in-country Postgres and S3-compatible storage) when the first such customer arrives.
- Wildcard School subdomains need Workers static assets (Pages does not take wildcard custom domains). Verify certificate behaviour on `*.app.vn` in the first infrastructure spike.

## Operations

- **Errors and logs**: structured JSON logs; an error tracker with PII scrubbing on (student names, phone numbers never leave in events). Self-hosted or EU/APAC-region SaaS, decided at setup.
- **Backups**: daily Postgres backups with point-in-time recovery, 30-day retention; object storage versioning on report cards and uploads; a restore drill once per term, recorded.
- **Audit log**: append-only table per School for score edits, gradebook reopenings, role changes and operator support sessions (`docs/roles.md`).
- **CI**: tests, the RLS policy check, the OpenAPI diff, and the permission matrix in `docs/roles.md` as tests (one test per cell).

## Open items

- Wildcard certificates and routing on Workers for `*.app.vn`.
- The fail-closed GUC on a real Postgres 16 (and PgBouncer later).
- Cloudflare request timeout against synchronous Excel imports; large imports move to tasks if they exceed it.
- Desmos and PhET terms, only if a School asks for them.
