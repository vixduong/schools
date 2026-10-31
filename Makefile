# Variables come from .env (created from .env.example on first use).
-include .env
export

.PHONY: db-up db-down backend-migrate backend-dev backend-check

.env:
	cp .env.example .env
	@echo "created .env from .env.example"

db-up: .env
	docker compose up -d --wait db

db-down:
	docker compose down

backend-migrate: .env
	cd backend && DB_ROLE=owner uv run python manage.py migrate

backend-dev: backend-migrate
	cd backend && uv run python manage.py runserver

backend-check: .env
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest

.PHONY: frontend-dev frontend-check

frontend-dev:
	pnpm --dir frontend install --frozen-lockfile
	pnpm --dir frontend dev

frontend-check:
	pnpm --dir frontend install --frozen-lockfile
	pnpm --dir frontend lint
	pnpm --dir frontend typecheck
	pnpm --dir frontend test

.PHONY: check
check: backend-check frontend-check
