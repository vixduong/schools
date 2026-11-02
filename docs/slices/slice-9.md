# Slice 9: Operations

Slice 9 of `docs/phase-0.md`. Standing rules: `backend/CODING_STANDARDS.md`, the Constraints sections of `docs/phase-0.md` ("Before production"), `docs/tech-stack.md` § Operations, ADR 0002 (a School never creates an Account).

Done when a new School can be created end to end on a fresh environment: a fresh database, migrated, then one operator command, and the first School admin activates on `<school>.<BASE_DOMAIN>` and is signed in with the School admin role.

## Owner decision (2026-11-02)

- **Observability is app-side in this slice**: JSON request logs and the OpenTelemetry SDK, both tested locally. The Alloy collector config (PII scrubbing, forwarding to Grafana Cloud Singapore) and the alert rules wait for the first infrastructure spike, when a stack exists to send to.

## The first School and its admin

- `manage.py create_school <subdomain> --name <School name> --admin <email or VN mobile> --admin-name <name> --operator <name>` (run with `DB_ROLE=owner`: the app role cannot create a School). It creates the School and a **staff invitation** for a School admin role from today, prints the code and `https://<subdomain>.<BASE_DOMAIN>/activate`, and creates no Account (ADR 0002). The invitation's `created_by` is empty: the operator is no member (`Invitation.created_by` becomes nullable).
- The subdomain is one lower-case DNS label (letters, digits, hyphens, at most 63), not a reserved name (`www`, `api`, `app`, `admin`, `mail`, `static`, `status`).
- Run again for an existing School: refused once the School has a School admin in force; until then it revokes the operator's pending invitations and issues a fresh code (a lost or expired code).
- Logged as `operator:<name>` in the School's audit log (slice 7).

## Sign-in protection

- **Rate limits** on login and activation, counted in a global Postgres table (`accounts_attempt`, no Redis per `docs/tech-stack.md`) with an atomic upsert per fixed 15-minute window: 10 attempts per identifier and 50 per client address. Keys are HMACs, so the table holds no phone, email or address. Over the limit: 429 with `Retry-After`, before any password is checked; the SPA says to wait. Old windows are deleted as new ones are written.
- **Client address**: `REMOTE_ADDR`, or the header named by `CLIENT_IP_HEADER` (`HTTP_CF_CONNECTING_IP` behind Cloudflare). Only set it where the proxy strips a client-sent copy.
- **Behind Cloudflare**: `TRUST_PROXY_HTTPS=true` sets `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`.
- **The app role must not bypass RLS**: each new connection as the app role checks `rolsuper` and `rolbypassrls` and refuses to run if either is set. App-role connections also set `idle_in_transaction_session_timeout` (30 s), so a stuck request cannot hold locks.

## Observability (app side)

- One JSON log line per request: time, method, route name (no query string), status, duration, `school_id`, whether a member was signed in, `trace_id`. Never identifiers, names or bodies.
- OpenTelemetry SDK with Django and psycopg instrumentation, exporting OTLP only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; off otherwise.

## Backups and the restore drill

- `scripts/backup.sh` writes a `pg_dump -Fc` of the database plus a manifest (row count per table). It runs as a role that bypasses RLS (the table owner is under FORCE RLS and would dump empty tables): the superuser locally, the provider's admin role in production.
- `scripts/restore-drill.sh <dump>` restores into a scratch database and checks: the latest migration of each app, forced RLS and the `tenant_isolation` policy on every tenant table, the app role's grants, and the row counts against the manifest. It drops the scratch database and prints one line to record in `docs/ops/restore-drills.md`.
- `make backup`, `make restore-drill DUMP=...` drive them against the compose database.
- Not in this slice: scheduling, point-in-time recovery and off-site copies, which depend on the host (managed Postgres gives PITR); decided in the infrastructure spike.
