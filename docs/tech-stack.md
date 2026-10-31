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
| RLS per request | middleware opens a durable transaction and runs `set_config('app.school_id', …, true)`; `ATOMIC_REQUESTS` on, so the view runs in a savepoint inside it | the GUC lives in the middleware's transaction; the savepoint rolls back a failed view's writes (DRF only marks rollback when `ATOMIC_REQUESTS` is on) |
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
| Forms | TanStack Form + Zod (Standard Schema validators; Zod 3.24 or later) |
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

### Observability: collect, aggregate, monitor

```
Django API, task worker ── OpenTelemetry SDK ──┐
SPA (browser) ─────────── Grafana Faro SDK ────┤
Postgres, VPS host ────── exporters ───────────┼─► Grafana Alloy (collector on the VPS, scrubs PII)
                                               │        └─► Grafana Cloud stack, Singapore (AWS ap-southeast-1)
External uptime checks ── Synthetic Monitoring ┘              Loki (logs) · Prometheus/Mimir (metrics) · Tempo (traces) · alerting
```

- **Instrumentation is OpenTelemetry**, so the backend is vendor-neutral: the same signals go to a self-hosted Grafana, Loki, Prometheus and Tempo when a Vietnam-hosted deployment needs it.
- **Logs**: structured JSON, one line per request and per task, carrying `trace_id`, `school_id` (as structured metadata, not a Loki label), role and outcome. Never names, phone numbers, scores or free text; the collector drops known PII fields as a second line of defence. Retention 30 days.
- **Metrics**: request rate, error rate and p95 latency per endpoint group; task queue depth, oldest job age and failures; Postgres connections and slow queries; disk, CPU, memory; backup job result; certificate expiry.
- **Traces**: every request and task, linked to its logs, so a slow gradebook save can be followed from the browser to the SQL.
- **Frontend**: Faro for JavaScript errors and Web Vitals, with the same scrubbing.
- **Alerts** (email plus a chat channel for the on-call developer): API 5xx above 1% for 5 minutes; p95 above 1.5 s for 10 minutes; any task failing three times; oldest queued job older than 10 minutes; nightly backup missing; uptime check failing from two locations; certificate expiring within 14 days; disk above 80%.
- **Exceptions** appear as error logs with their trace; a separate error tracker is added only if triage in Grafana proves too slow.

### Backups, audit, CI

- **Backups**: daily Postgres backups with point-in-time recovery, 30-day retention; object storage versioning on report cards and uploads; a restore drill once per term, recorded.
- **Audit log**: append-only table per School for score edits, gradebook reopenings, role changes and operator support sessions (`docs/roles.md`). It is product data, kept in Postgres under RLS, not in the log pipeline.
- **CI**: tests, the RLS checks (`docs/spikes/rls-checks.sql` turned into a test), the policy-coverage check, the OpenAPI diff, and the permission matrix in `docs/roles.md` as tests (one test per cell).

## Verified (2026-10-31)

- **RLS fails closed on Postgres 16.15** (spike in `docs/spikes/`): as a `NOBYPASSRLS` role with `FORCE ROW LEVEL SECURITY`, no School set returns 0 rows; a School set with `set_config(..., true)` sees only its rows; inserting another School's row is refused; after `COMMIT` or `ROLLBACK` the same connection sees 0 rows again; a cross-School `UPDATE` touches 0 rows. **`NULLIF` is required**: once a connection has been scoped, the setting reads back as `''`, and a policy that casts it without `NULLIF` raises `invalid input syntax for type integer` on every later query.
- **Wildcard School subdomains work on Cloudflare without Enterprise**: proxied wildcard DNS records are allowed on all plans; Universal SSL covers first-level subdomains (`<school>.app.vn`, never `x.<school>.app.vn`); a Worker route `*.app.vn/*` matches every School host. School hostnames therefore stay one level deep.
- **Cloudflare waits 125 s for the origin** (HTTP 524 after that), configurable only on Enterprise. Any request that can approach it (large Excel import, School-wide export) runs as a task and the SPA polls its status.
- **TanStack Form** validates with Zod through Standard Schema at form or field level.

## Open items

- Routing `/api/*` past the Worker to the origin on the same hostname (a Worker route exclusion, or the Worker proxying `/api`), settled in the first infrastructure spike.
- PgBouncer transaction mode with the GUC pattern, when pooling is added.
- Grafana Cloud free-tier ingestion limits against expected volume; move to a paid stack or self-host when exceeded.
- Desmos and PhET terms, only if a School asks for them.
