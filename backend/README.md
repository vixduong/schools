# Backend

Django 5.2 LTS + DRF, Postgres 16 with row-level security (ADR 0001). Run from the repo root:

```
make db-up          # Postgres in Docker; creates .env from .env.example on first use
make backend-dev    # migrate as the owner role, then runserver as the app role
make backend-check  # ruff + pytest (real Postgres, so db-up first)
```

- Schools resolve from the host: `a.localhost:8000/api/auth/csrf/` (`BASE_DOMAIN` in `.env`).
- Dev School + Account + Membership (DEV ONLY, refuses unless `DJANGO_DEBUG=1`, runs as the owner role):
  `DB_ROLE=owner uv run python manage.py create_dev_school a admin@a.test [--password dev-password]`,
  then `POST a.localhost:8000/api/auth/login/` with `{"identifier": "admin@a.test", "password": "..."}`.
  It is idempotent and gives the Account an active Membership with a School-wide `school_admin` assignment.
- Dev accounts for every role (DEV ONLY, same guard, owner role): `DB_ROLE=owner uv run python manage.py seed_dev_roles a`.
  It runs `create_dev_school` first, then creates one sign-in per role, all with password `dev-password`, and prints the list:

  | Role | Sign in with | Scope it gets |
  |---|---|---|
  | `school_admin` | `admin@a.test` | whole School |
  | `principal_board` | `board@a.test` | whole School; named as principal, may reopen gradebooks, signs for the principal |
  | `group_leader` | `group@a.test` | subject group Toán |
  | `homeroom_teacher` | `homeroom@a.test` | class 7A |
  | `subject_teacher` | `subject@a.test` | Toán × class 7A |
  | `student` | `student@a.test` | enrolled in 7A (own record only) |
  | `guardian` | `0912000001` (phone) | linked to the student above |

  The fixtures are school year (current), Grade 7 (lower secondary), class 7A, subject group and subject Toán (`MATH`),
  one student and one guardian link. Idempotent; the guardian's phone is fixed, so it is the same Account on every run.
  Operator staff have no dev account: they see no School data.
- Auth (ADR 0003), all under `/api/auth/` on a School host: `GET csrf/` (sets the CSRF cookie), `POST login/`,
  `POST logout/`, `GET me/`. Send the CSRF cookie's value as `X-CSRFToken` on every POST. A session is bound to
  the School it was created on, and the default permission is an active Membership in the host's School.
  Rate limiting on login is not built yet.
- Cookies are `__Host-sessionid` / `__Host-csrftoken` with `Secure`, which browsers only accept over https.
  `SECURE_COOKIES` accepts only `1`, `true`, `0`, `false` (any case; unset means true) and anything else
  fails at startup. `false` turns the prefix and `Secure` off for plain-http local dev and is refused
  unless `DJANGO_DEBUG=1`; `.env.example` sets it to `false`.
- The app role cannot create, delete or edit Accounts (only `SELECT` and `UPDATE (password, last_login)`);
  create them as the owner role.
- Two DB roles: `DB_ROLE=owner` (migrations, tests' database setup) and the default `app` (`NOBYPASSRLS`, requests).
  The init script `db/init-roles.sh` runs only on a fresh volume; after changing roles run
  `docker compose down -v` then `make db-up`.
- New tenant table: give it a `school` foreign key and add `enable_tenant_rls("<table>")`
  (`tenancy/rls.py`) to its migration. `test_every_table_with_school_id_has_forced_rls_and_policy` fails otherwise.
- OpenAPI: `uv run python manage.py spectacular --file schema.yml` (from `backend/`, with `.env` exported).
