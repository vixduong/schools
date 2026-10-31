# What are the current versions and proven patterns for the chosen stack?

Type: research
Status: open
Blocked by:

## Question

For the chosen stack (Django + DRF, drf-spectacular, Postgres 16 RLS; TanStack Router/Query/Table, Tailwind, shadcn/ui; Cloudflare Pages/R2), what are the current stable versions and their compatibility as of late 2026? How do production Django apps enforce Postgres row-level security per request (`SET LOCAL` per transaction, connection pooling caveats with PgBouncer), and how should a SPA on `<school>.app.vn` authenticate against a Django API (session cookie + CSRF across subdomains vs tokens)? What do teams use for Excel import/export and bulk PDF report cards in Django, and when is a task queue required?
