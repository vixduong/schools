# Backend

Django 5.2 LTS + DRF, Postgres 16 with row-level security (ADR 0001). Run from the repo root:

```
make db-up          # Postgres in Docker; creates .env from .env.example on first use
make backend-dev    # migrate as the owner role, then runserver as the app role
make backend-check  # ruff + pytest (real Postgres, so db-up first)
```

- Schools resolve from the host: `a.localhost:8000/api/probes/` (`BASE_DOMAIN` in `.env`). Create one with
  `DB_ROLE=owner uv run python manage.py shell` (`School.objects.create(name="A", subdomain="a")`).
- Two DB roles: `DB_ROLE=owner` (migrations, tests' database setup) and the default `app` (`NOBYPASSRLS`, requests).
  The init script `db/init-roles.sh` runs only on a fresh volume; after changing roles run
  `docker compose down -v` then `make db-up`.
- New tenant table: give it a `school` foreign key and add `enable_tenant_rls("<table>")`
  (`tenancy/rls.py`) to its migration. `test_every_table_with_school_id_has_forced_rls_and_policy` fails otherwise.
- OpenAPI: `uv run python manage.py spectacular --file schema.yml` (from `backend/`, with `.env` exported).
