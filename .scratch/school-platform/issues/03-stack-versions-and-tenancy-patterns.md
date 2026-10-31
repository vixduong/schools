# What are the current versions and proven patterns for the chosen stack?

Type: research
Status: resolved
Blocked by:

## Question

For the chosen stack (Django + DRF, drf-spectacular, Postgres 16 RLS; TanStack Router/Query/Table, Tailwind, shadcn/ui; Cloudflare Pages/R2), what are the current stable versions and their compatibility as of late 2026? How do production Django apps enforce Postgres row-level security per request (`SET LOCAL` per transaction, connection pooling caveats with PgBouncer), and how should a SPA on `<school>.app.vn` authenticate against a Django API (session cookie + CSRF across subdomains vs tokens)? What do teams use for Excel import/export and bulk PDF report cards in Django, and when is a task queue required?

## Answer

Findings: branch `research/stack-versions-and-tenancy-patterns`, file `docs/research/stack-versions-and-tenancy-patterns.md`.

- Versions: Django 5.2 LTS now (6.2 LTS due Apr 2027), DRF 3.18, psycopg 3. drf-spectacular is only CI-tested up to Django 6.0, which argues for 5.2 LTS.
- RLS: `set_config('app.school_id', …, true)` inside the same transaction as the queries. `ATOMIC_REQUESTS` wraps only the view, so open the transaction in middleware or the DRF base view. The app role is NOBYPASSRLS; migrations run as the owner. Add a CI check that every `school_id` table has a policy, and make the policy fail closed. PgBouncer is not needed on day one.
- Auth: serve the SPA and the API same-origin at `<school>.app.vn` and `<school>.app.vn/api`. Use a host-only Django session cookie (SameSite=Lax) with `X-CSRFToken`. No CORS, no JWT. Cloudflare Pages cannot take wildcard custom domains, so use Workers static assets on `*.app.vn/*`, or register each School's domain at onboarding.
- Files: openpyxl read-only import with a row-error preview, then commit in one transaction. WeasyPrint for report cards, with an embedded Vietnamese font.
- Queue: not needed for single items; needed for bulk PDFs, large imports, recalculation and notifications. Use a Postgres-backed backend behind Django's `@task` API.
- Open: wildcard DNS and certificates on Workers, the fail-closed GUC tested on a real PG16, the Cloudflare request timeout.
