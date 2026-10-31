# Phase 0: build plan

Phase 0 of `docs/roadmap.md`, cut into slices that each end green (tests pass, `make check` clean) and committed. Order follows dependencies. Stack per `docs/tech-stack.md`; terms per `GLOSSARY.md`; permissions per `docs/roles.md`; UI per `DESIGN.md`.

| # | Slice | Done when |
|---|---|---|
| 1 | **Skeleton**: `backend/` (uv, Python 3.13, Django 5.2 LTS, DRF, drf-spectacular, psycopg 3), `frontend/` (Vite, React, TypeScript, Tailwind v4, shadcn/ui, TanStack Router/Query/Form), `compose.yaml` with Postgres 16, root `Makefile` (`make dev`, `make check`) | both apps start with one command each; `make check` runs lint, types and tests for both |
| 2 | **Tenancy**: `School` (global), host → School resolution, a middleware that opens the transaction and runs `set_config('app.school_id', …, true)`, an app DB role `NOBYPASSRLS`, a migration helper that enables and forces RLS with a `NULLIF` fail-closed policy, a test that every table with `school_id` has a policy, the isolation checks from `docs/spikes/` as tests | a request on `a.localhost` can never read or write `b.localhost` rows, proven by tests |
| 3 | **Accounts**: `Account` (custom user, global, ADR 0002), `Membership`, `RoleAssignment` (role × scope × school year); session login, logout, `me` per School host with CSRF (ADR 0003) | sign-in works per School; a Membership of School A cannot sign in on School B |
| 4 | **School setup**: school years, terms, Levels, Grades, classes, subjects, subject groups, rooms; Ministry IDs, national personal ID, status history instead of deletes; Assessment Profile versions (ADR 0006) as data | the School admin can set up a year through the API |
| 5 | **Permissions**: one permission check fed by Role Assignments in force; `docs/roles.md` encoded as a table-driven test, one case per cell | every matrix cell has a passing test |
| 6 | **Import**: Excel import of staff, students and Guardians with a row-error preview and one-transaction commit; Guardian invite codes | a sample roster imports; a bad row is reported, nothing half-written |
| 7 | **Audit and support access**: append-only audit log; time-limited operator support grants, logged | score-like edits and grants appear in the School's log |
| 8 | **Frontend shell**: tokens and components from `DESIGN.md` (both modes), login per School, top bar, routes for later screens, generated OpenAPI client | the login screen of the prototype works against the API |
| 9 | **Operations**: OpenTelemetry + Alloy config, backups and restore drill script, operator command to create a School, its subdomain and first admin; login rate limiting and `SECURE_PROXY_SSL_HEADER` for the Cloudflare topology (both required before production) | a new School can be created end to end on a fresh environment |

Slices 1 and 2 carry the most risk (tenancy is ADR 0001's promise), so they go first and get an independent review before slice 3.

## Constraints from the slice 1–2 review (apply from slice 3 on)

- **Sessions belong to a School.** Store `school_id` in the session at login and reject a mismatch with `request.school` in authentication; the default DRF permission is "has a Membership in `request.school`", never just "is authenticated". `SessionMiddleware`, `AuthenticationMiddleware` and `CsrfViewMiddleware` come after `TenantMiddleware`. School roles never use Django's global groups or permissions tables.
- **Cookies**: `__Host-sessionid` and `__Host-csrftoken` (School subdomains are same-site with each other, so `SameSite=Lax` does not separate Schools); never `CSRF_TRUSTED_ORIGINS=["https://*.app.vn"]`; set `SECURE_PROXY_SSL_HEADER` behind Cloudflare.
- **Grants**: global tables the app role writes (Account, sessions) get explicit grants in our own migrations and go on the `GLOBAL_TABLES` allowlist in `tenancy/tests/test_rls.py`; every other reachable table must have forced RLS and exactly the `tenant_isolation` policy (the test enforces it).
- **Many-to-many on tenant models** uses an explicit `through=` model with a `school` FK.
- **Tenant foreign keys and uniques** include `school_id` (composite FKs, `(school_id, …)` unique constraints), so a row cannot point at another School's row and uniqueness never reveals another School's data (national ID).
- **Data migrations** run per School inside `school_scope` (the owner is bound by FORCE RLS and otherwise sees nothing); tasks carry `school_id` and enter `school_scope` themselves; responses never stream DB data.
- **Before production**: refuse to start if the DB role is superuser or `BYPASSRLS`; `idle_in_transaction_session_timeout` on the app role; RLS is a guard against a missed filter, not against SQL injection, so no raw SQL from user input.

## Decisions during slice 3 (owner, 2026-10-31)

- Phone logins accept Vietnamese 10-digit mobile numbers only (`0XXXXXXXXX`, `+84`/`84` normalised); landlines and foreign numbers are refused, and those Guardians sign in by email.
- Login rate limiting and `SECURE_PROXY_SSL_HEADER` are built in slice 9, with the deploy topology, and must exist before production.

## Constraints from the slice 3 review (apply from slice 4 on)

- **A School never writes an existing Account's credentials or identifiers.** Account is global (ADR 0002): editing a person's email, phone or password from School A would change their sign-in at School B, so School admins only link people through invites, and views reach `Account` only through `Membership`, never `Account.objects.get(pk=…)` from a request.
- **RoleAssignment scope is redesigned in slice 4, before slice 5 builds on it**: typed nullable composite FKs (grade, class, subject, subject group, student) instead of `(scope_kind, scope_id)`, a per-role check constraint saying which scope each role needs, `school_year` as a composite FK to the school-year table, the subject teacher's subject × classes expressed as teaching rows, and uniqueness only over assignments in force so a role can end and resume in the same year with its history kept.
- **Every tenant-to-tenant FK includes `school_id`**, via `composite_fk` in `tenancy/rls.py`; a schema test fails on any single-column FK between two tables that both carry `school_id`.
- **Rotate the session key last.** Any view that calls `login()`, `update_session_auth_hash()` or `cycle_key()` does all validation first; a 4xx after rotation rolls back the new session row and the client gets `SessionInterrupted`.
- **Only DRF's `request.user` and `request.membership` are trusted** for identity; a middleware also resets Django's `request.user` when the session belongs to another School, so audit and telemetry never record the wrong person.
- **No view is open by accident**: a test walks the URLconf and fails on any view without School-bound authentication and a real permission, except an explicit allowlist (login, logout, csrf, schema).
