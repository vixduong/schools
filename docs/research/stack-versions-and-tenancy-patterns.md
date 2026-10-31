# Stack versions and tenancy patterns

Research for ticket `.scratch/school-platform/issues/03-stack-versions-and-tenancy-patterns.md`. Date of research: 2026-10-31. Context: ADR 0001 (one tenant per School, shared Postgres, `school_id` on every row, RLS isolation).

Confidence tags: **[doc]** = stated on the cited primary page; **[pypi/npm]** = read from the package registry JSON; **[inferred]** = my conclusion from sources; **[unverified]** = known practice not confirmed on a primary page and not tested here (no Postgres/Docker available in this environment).

## 1. Current stable versions and compatibility

| Component | Latest stable (2026-10-31) | Source |
|---|---|---|
| Django | 6.1.2 (6.1 released 2026-08-05); 5.2 LTS at 5.2.18; 6.2 LTS due April 2027 | [download page](https://www.djangoproject.com/download/), [PyPI](https://pypi.org/project/Django/) |
| djangorestframework | 3.18.3 (2026-10-06); classifiers: Django 5.2, 6.0, 6.1; Python 3.10-3.15 | [PyPI](https://pypi.org/project/djangorestframework/) |
| drf-spectacular | 0.30.0 (2026-07-06); classifiers and CI matrix stop at **Django 6.0 / DRF 3.17 / Python 3.14** | [PyPI](https://pypi.org/project/drf-spectacular/), [tox.ini](https://github.com/tfranzel/drf-spectacular/blob/master/tox.ini) |
| psycopg | 3.3.6 | [PyPI](https://pypi.org/project/psycopg/) |
| PostgreSQL | 16 chosen. Django 6.1 requires PG 15+ (dropped 14). | [6.1 release notes](https://docs.djangoproject.com/en/6.1/releases/6.1/), [Django databases](https://docs.djangoproject.com/en/6.1/ref/databases/) |
| Python | Django 6.1 needs 3.12+ (3.12-3.15) | [6.1 release notes](https://docs.djangoproject.com/en/6.1/releases/6.1/) |
| django-filter / django-cors-headers / django-storages | 26.2 (Django 6.1 listed) / 4.9.0 (Django up to 6.0) / 1.14.6 | PyPI |
| openpyxl / XlsxWriter / WeasyPrint | 3.1.5 / 3.3.1 / 70.0 | PyPI |
| React / Vite / Tailwind | 19.3.1 / 8.3.5 / 4.3.3 (`@tailwindcss/vite` 4.3.3 supports Vite 5-8) | npm |
| @tanstack/react-router / react-query / react-table | 1.170.46 / 5.105.0 / **9.3.1** (v9 became `latest`; 9.0.0 published 2026-08-04, last v8 is 8.21.3) | npm |
| shadcn CLI | 4.23.0; Vite path = `tailwindcss` + `@tailwindcss/vite`, `@import "tailwindcss"` | [shadcn Vite install](https://ui.shadcn.com/docs/installation/vite) |
| wrangler | 4.156.0 | npm |

Compatibility findings:

- **Django 6.1 + drf-spectacular 0.30.0 is not officially tested.** spectacular's CI matrix tops out at Django 6.0 + DRF 3.17 [tox.ini]. DRF 3.18.3 does declare Django 6.1. It will probably work, since spectacular only reads DRF/Django serializer and view introspection, but that is [inferred].
- Django 6.1 mainstream support ends April 2027, extended December 2027. 6.2 LTS lands April 2027 [download page]. 5.2 LTS is extended-support only until April 2028 [download page].
- The Django 6.1 notes list no CSRF change and no psycopg/DRF items. One thing relevant to file upload endpoints: invalid base64 in multipart now raises `MultiPartParserError` [6.1 notes].
- TanStack Router's peer deps are React 18 or 19, Query 5's are React 18 or 19, Table 9's is React >= 18 [npm]. Table v9 is a new major; v8 code does not carry over unchanged. I could not load a migration guide page (404), so the size of the v8 to v9 breakage is unverified. Check it before building data-grid-heavy screens.

**Recommendation.** Start on **Django 5.2 LTS** if you want a toolchain every library has CI-tested (DRF 3.18 supports it, spectacular tests 5.2 with DRF 3.15/3.16), then move to **6.2 LTS** in April 2027 when spectacular has had time to add 6.1/6.2. If you prefer to be current, **Django 6.0/6.1 + DRF 3.18 + spectacular 0.30** is the practical choice, with a CI job that generates the OpenAPI schema and diffs it, since the schema is the contract with the SPA. Pin psycopg 3 (not psycopg2; Django says psycopg2 support is likely to be removed [Django databases]). Run Postgres 16 (Django 6.1 needs 15+).

## 2. Postgres RLS per request in Django

### What Postgres guarantees

- Superusers and roles with `BYPASSRLS` always bypass RLS. Table owners bypass it too unless the table has `FORCE ROW LEVEL SECURITY`. Only the owner can enable RLS and add policies. With RLS on and no policy, default-deny applies. A policy without explicit `WITH CHECK` reuses `USING` for writes, so cross-tenant INSERT/UPDATE is rejected [[PG16 ddl-rowsecurity](https://www.postgresql.org/docs/16/ddl-rowsecurity.html)].
- Unique and foreign-key checks bypass RLS, which can leak existence of rows across tenants (a "covert channel") [same page]. Consequence for this project: make unique constraints composite with `school_id` (e.g. `(school_id, student_code)`), otherwise a School can probe whether another School already uses a code.
- `set_config(name, value, is_local)`: with `is_local = true` the value lasts only for the current transaction; `current_setting(name, true)` returns NULL instead of erroring when unset [[PG16 functions-admin](https://www.postgresql.org/docs/16/functions-admin.html)].
- Any session can `SET app.school_id = ...` itself, so the GUC is only trustworthy because the application role cannot be reached by end users, not because of the GUC [inferred from PG docs]. SQL injection is therefore the main residual risk to this design. That is acceptable: RLS here defends against missed filters, not against a fully compromised app.

### Recommended pattern

1. Three roles: `schools_owner` (owns tables, runs migrations, no one connects to it at runtime), `schools_app` (`NOSUPERUSER NOBYPASSRLS`, only `SELECT/INSERT/UPDATE/DELETE` on tables and sequence usage), and optionally `schools_ops` (`BYPASSRLS`, for platform admin and cross-tenant jobs, never used by request handlers). Because the owner bypasses RLS, migrations run fine as owner. Without `FORCE`, the owner bypasses policies, so schema and data migrations work unchanged; the policy template below uses `FORCE`, so data migrations that touch tenant rows must run as a `BYPASSRLS` role (e.g. `schools_ops`) or set the GUC per School. Pick one deliberately. Use a separate Django `DATABASES` alias (and `--database`) for migrations with the owner credentials. [inferred from the PG semantics above]
2. Policy template, generated by a helper in migrations (`RunSQL`), one per tenant table:

   ```sql
   ALTER TABLE x ENABLE ROW LEVEL SECURITY;
   ALTER TABLE x FORCE ROW LEVEL SECURITY;
   CREATE POLICY tenant ON x
     USING      (school_id = NULLIF(current_setting('app.school_id', true), '')::bigint)
     WITH CHECK (school_id = NULLIF(current_setting('app.school_id', true), '')::bigint);
   ```

   The `NULLIF(..., '')` guard matters: [unverified] after a `set_config(..., true)` transaction ends, PostgreSQL leaves a custom GUC defined with an empty string rather than reverting to "unset", so a bare `::bigint` cast would raise instead of failing closed. NULL (no rows) is the fail-closed outcome you want. Add a test that opens a connection, runs a transaction, then queries outside the transaction and asserts zero rows.
3. Add a Django system check or CI test that every model with a `school_id` field has a policy (query `pg_policies`/`pg_class.relrowsecurity`). This is the real safety net for a 1-2 developer team.
4. Per request: resolve the School from the `Host` header (`<school>.app.vn`), then set the GUC **inside the transaction that runs the queries**.

### The ATOMIC_REQUESTS trap

`ATOMIC_REQUESTS` wraps only the view; "Middleware runs outside of the transaction" [[Django transactions](https://docs.djangoproject.com/en/6.1/topics/db/transactions/)]. A middleware that calls `set_config(..., true)` before the view therefore runs in its own autocommit transaction and the setting is gone by the time the view starts. Two correct options:

- **A. Own the transaction in middleware** (recommended): leave `ATOMIC_REQUESTS = False` and write one middleware that does `with transaction.atomic(): cursor.execute("SELECT set_config('app.school_id', %s, true)", [school_id]); return self.get_response(request)`. The GUC and all queries share one transaction. Cost: session/auth middleware that runs earlier (session lookup) is outside it, so keep `django_session` and the user/membership table the login path touches **without RLS**, or look them up through the Host-resolved School before. Streaming responses run outside the transaction per the Django docs, so do not stream tenant data from the DB (PDF/Excel exports are built in memory or go through the task queue; see section 4).
- **B. Keep `ATOMIC_REQUESTS = True`** and set the GUC in DRF's `APIView.initial()` or a base viewset (executed inside the view, thus inside the transaction). Easier to reason about with DRF auth, but every view must inherit the base class.

Reads outside any transaction would see no GUC (autocommit), which with the policy above returns zero rows rather than leaking. Use `transaction.on_commit` for side effects (queue enqueue, emails) so they only fire after commit [Django transactions].

### PgBouncer / pooling caveats

- In transaction pooling, plain `SET` and `RESET` are "Never" supported, as are session advisory locks, `LISTEN`, and SQL-level `PREPARE` [[PgBouncer features](https://www.pgbouncer.org/features.html)]. `set_config(..., true)` / `SET LOCAL` is scoped to one transaction, so it is safe as long as the set and the queries are in the same transaction. This is why `is_local = true` is the only acceptable form; a session-level `set_config(..., false)` would leak one School's id to the next client reusing that server connection. The PgBouncer page does not list `SET LOCAL` explicitly; the conclusion rests on transaction scoping [inferred].
- `server_reset_query` (default `DISCARD ALL`) is not run in transaction pooling [[PgBouncer config](https://www.pgbouncer.org/config.html)], so nothing cleans up a leaked session GUC. Another reason to use `is_local = true` only.
- Django requires `DISABLE_SERVER_SIDE_CURSORS = True` behind a transaction pooler [Django databases]. This matters for `.iterator()` on big querysets (exports).
- Protocol-level prepared statements work only if `max_prepared_statements` is non-zero in PgBouncer [PgBouncer features/config]. psycopg 3 can auto-prepare; Django's default is client-side binding for psycopg 3, so this mostly does not bite [Django databases]. Keep `prepare_threshold = None` in OPTIONS if you see prepared-statement errors [unverified].
- Django's own pool (`OPTIONS: {"pool": True}`, psycopg_pool) requires `CONN_MAX_AGE = 0` [Django databases]. Do not stack it blindly on top of PgBouncer.

**Recommendation.** At 1-2 developers and hundreds of schools, you probably do not need PgBouncer on day one. Start with Django persistent connections (`CONN_MAX_AGE` ~60, `CONN_HEALTH_CHECKS = True`) or the psycopg pool talking directly to Postgres, with the GUC pattern in option A. Add PgBouncer in transaction mode when connection count (workers x threads) approaches `max_connections`; the GUC pattern needs no change because it already uses `is_local = true`. Managed Postgres often bundles a pooler; check which mode it defaults to.

## 3. SPA authentication on `<school>.app.vn`

### Hosting constraint that shapes the answer

Cloudflare Pages **cannot add a wildcard custom domain** (`*.domain.com`); subdomains are added one at a time [[Pages known issues](https://developers.cloudflare.com/pages/platform/known-issues/)]. Workers with static assets do support a SPA mode (`not_found_handling = "single-page-application"`, with `run_worker_first` for selective routing such as `/api/*`) [[Workers static assets](https://developers.cloudflare.com/workers/static-assets/)] and wildcard routes (`*.example.com/*`), provided the zone is on Cloudflare and each host has a proxied DNS record [[Workers routes](https://developers.cloudflare.com/workers/configuration/routing/routes/)]. Whether a single wildcard DNS record satisfies this was not stated on that page; test it. Cloudflare's migration page says Workers has a broader feature set than Pages [[Pages to Workers](https://developers.cloudflare.com/workers/static-assets/migration-guides/migrate-from-pages/)]. A plan with "a new School appears at `<school>.app.vn` instantly" needs either wildcard routing via Workers, or an API call that registers each new custom domain with Pages at onboarding time (the Pages custom-domain page does not document limits; unverified).

### Session cookie vs tokens

- DRF: session auth fits "AJAX clients that are running in the same session context as your website" and requires a CSRF token on unsafe methods for authenticated requests. DRF's built-in TokenAuthentication is simple, has no expiry and needs HTTPS; JWT via a third party avoids DB lookups [[DRF authentication](https://www.django-rest-framework.org/api-guide/authentication/)].
- Django cookie settings: `CSRF_COOKIE_DOMAIN` can share the CSRF cookie across subdomains but the docs warn this does not make cross-subdomain CSRF safe; `CSRF_TRUSTED_ORIGINS` supports wildcard subdomains such as `https://*.example.com`; `CSRF_COOKIE_HTTPONLY` brings little practical protection and forces reading the token from a form input [[Django settings](https://docs.djangoproject.com/en/6.1/ref/settings/)]. Django checks `Origin` against `Host`, so a SPA on a different origin than the API needs `CSRF_TRUSTED_ORIGINS`.

### Recommendation

**Same-origin, host-only session cookie.** Serve the API from the same host as the SPA, `https://<school>.app.vn/api/...`, routing `/api/*` on every School host to the Django origin (Worker route or Cloudflare origin/rules; see hosting note). Then:

- Django `SessionAuthentication` with `SESSION_COOKIE_SECURE`, `HttpOnly`, `SameSite=Lax`, **no `SESSION_COOKIE_DOMAIN`** (host-only), so a session for school A is never sent to school B; this gives tenant isolation of credentials for free and keeps each tenant's cookie jar separate [inferred].
- No CORS at all (same origin). The SPA reads the `csrftoken` cookie (host-only, `CSRF_COOKIE_HTTPONLY=False`) and sends `X-CSRFToken` on unsafe requests; prime it with a `GET /api/auth/csrf/` endpoint decorated `ensure_csrf_cookie`. Login must be CSRF-protected too (DRF says login views must always enforce CSRF) [DRF authentication].
- Verify at login that the user's membership includes the School resolved from the Host, and set the same RLS GUC from the Host, not from anything in the cookie.
- Cloudflare in front: mark `/api/*` as cache bypass, never cache responses with `Set-Cookie` or tenant data, and make the origin trust only Cloudflare IPs / `CF-Connecting-IP` for `request.META` handling (`SECURE_PROXY_SSL_HEADER`, correct `X-Forwarded-Proto`) [inferred; no primary page fetched on these].

Why not tokens: JWT in `localStorage` is exposed to XSS and needs refresh/revocation logic that a 1-2 developer team has to build; cookie sessions give server-side logout and are what DRF recommends for same-site AJAX clients [DRF authentication]. Why not `api.app.vn` + `Domain=.app.vn`: one cookie for every School's host, wider CSRF surface (Django's own warning), and CORS plus `CSRF_TRUSTED_ORIGINS` wildcards to maintain. Tokens become the right answer only for a future native mobile client or third-party API access; add `django-rest-knox`-style per-client tokens or OAuth then (DRF lists both).

## 4. Excel import/export and bulk PDF report cards

### Excel

- openpyxl 3.1.5 has read-only mode (lazy, near-constant memory, must `close()`, relies on correct sheet dimensions) and write-only mode (append-only, can export "unlimited" data under ~10 MB, `lxml` recommended, workbook saved once) [[openpyxl optimised modes](https://openpyxl.readthedocs.io/en/stable/optimized.html)]. XlsxWriter 3.3.1 is write-only with a constant-memory option [PyPI; its `constant_memory` option not fetched here].
- django-import-export 4.4.4 (Django 5.2 listed on PyPI) gives Resource classes, dry-run/preview of imports, and admin UI, built on tablib [PyPI]. It is useful as a validation/diff engine but its UI is Django admin, not the SPA.

**Recommendation.** Roster/grade **import**: SPA uploads the `.xlsx` to the API (or R2 via presigned URL), the API parses with openpyxl `read_only=True`, validates every row into a structured error list (row, column, message), and returns a **preview** before an explicit "commit" call. Do the whole commit in one transaction under the School's RLS GUC. A class roster (tens to a few thousand rows) fits comfortably synchronously. Use django-import-export's Resource only if you want its row-level diff/dry-run for free; otherwise a ~100-line parser with DRF serializers for row validation is enough. **Export**: write with openpyxl write-only mode or XlsxWriter into a `BytesIO`/temp file and return a normal `FileResponse`; avoid `StreamingHttpResponse` that reads from the DB, since it escapes `ATOMIC_REQUESTS` and the RLS-transaction (section 2). Ship downloadable templates with locked header rows so Vietnamese-language column names stay stable.

### Bulk PDF report cards

- WeasyPrint 70.0 needs Python 3.10+ and Pango 1.44+; on Debian it needs `libpango-1.0-0`, `libpangoft2-1.0-0`, `libharfbuzz-subset0`; it renders HTML/CSS; Django-Weasyprint is a third-party helper [[WeasyPrint first steps](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)]. ReportLab 5.1.0 is the programmatic alternative; pypdf 6.21.4 merges PDFs [PyPI].

**Recommendation.** Render each report card from a Django HTML template with **WeasyPrint** (templates are plain HTML/CSS a developer can tweak; embed a Vietnamese-capable font such as Noto Sans/Be Vietnam Pro via `@font-face` so diacritics render and PDFs are reproducible) in the Docker image with Pango installed. A single card: synchronous endpoint. A whole class or school (hundreds of PDFs): generate per-student PDFs, write them to R2, and serve a zip or a pypdf-merged file via presigned URL; this is a background job (below). Content-address results (hash of inputs) so re-downloads are free.

## 5. When a task queue becomes necessary

- Django 6.0+ ships a tasks framework, but its built-in backends are `ImmediateBackend` (runs inline) and `DummyBackend` (never runs), "unsuitable for production"; Django "does not provide a worker mechanism" [[Django tasks](https://docs.djangoproject.com/en/6.1/topics/tasks/)]. You need a third-party backend for real workers. Enqueue inside `transaction.on_commit` because workers use different DB connections [same page].
- Options: `django-tasks-db` 0.13.0 (DB-backed, `manage.py db_worker`, classified Beta, needs `prune_db_task_results`, classifiers list Django 5.2/6.0) [[PyPI](https://pypi.org/project/django-tasks-db/)]; Celery 5.6.3 (needs a broker such as Redis/RabbitMQ), django-rq 4.2.0 (Redis), procrastinate 3.10.0 (Postgres-native), django-q2 1.11.1 [all PyPI]. I read versions only, not each project's guarantees.

**When it becomes necessary** (rule of thumb [inferred]): any work that can exceed the HTTP/Cloudflare request timeout (about 100 s on the Cloudflare proxy; confirm current limit on your plan), anything that must survive a deploy or retry on failure, or anything needing fan-out. Concretely here: (1) bulk PDF generation for a class/school, (2) very large Excel imports/exports (several thousand rows with heavy validation), (3) end-of-term grade recalculation across a School, (4) email/SMS/Zalo notifications to parents. Roster import of one class and single report cards do not need it. Since the stack is one Postgres and no Redis is planned, a queue also changes the RLS design: every job must set `app.school_id` itself (job carries `school_id`, worker opens a transaction and calls `set_config(..., true)`), and must never run as `BYPASSRLS` unless it is a deliberate cross-tenant job.

**Recommendation.** Do not add a queue for the first release if the above heavy cases are not in scope. When they are, use the Django 6 `tasks` API with a **Postgres-backed** backend (`django-tasks-db` or procrastinate) to avoid adding Redis, write tasks against the Django `@task` interface so the backend can be swapped for Celery later, and store outputs in R2. R2 pricing is low: 10 GB-month free, $0.015/GB-month, free egress [[R2 pricing](https://developers.cloudflare.com/r2/pricing/)].

## Open items to verify before committing

1. Does a wildcard DNS record plus a Workers wildcard route serve unlimited `<school>.app.vn` hosts with automatic certificates (Universal SSL covers only one level of subdomain)? Test on a scratch zone.
2. Run the NULLIF/empty-GUC behavior test against real Postgres 16 and with PgBouncer in transaction mode.
3. drf-spectacular on Django 6.1: run the schema generation in a spike; watch for a release that adds 6.1 to its tox matrix.
4. TanStack Table v9 migration scope versus v8.
5. Cloudflare request timeout for proxied origin requests on the chosen plan.
