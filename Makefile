# Variables come from .env (created from .env.example on first use).
-include .env
export

.PHONY: db-up db-down backend-migrate backend-dev backend-check

.env:
	cp .env.example .env
	@echo "created .env from .env.example"

db-up: .env
	@docker info >/dev/null 2>&1 || { echo "Docker is not running: start Docker Desktop (open -a Docker) and retry."; exit 1; }
	docker compose up -d --wait db

db-down:
	docker compose down

backend-migrate: .env
	cd backend && DB_ROLE=owner uv run python manage.py migrate

backend-dev: backend-migrate
	cd backend && uv run python manage.py runserver

backend-check: .env
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest

.PHONY: frontend-dev frontend-check api-client

# The SPA's API contract: the schema and its TypeScript types, both committed (review the diff).
# openapi-typescript drives the TypeScript 5 compiler API (TypeScript 7 ships none), so it runs
# with its own pinned TypeScript, apart from the app's.
OPENAPI_TS = cd frontend && pnpm dlx --package openapi-typescript@7.13.0 --package typescript@5.9.3 openapi-typescript src/api/openapi.json

api-client: .env
	cd backend && uv run python manage.py spectacular --format openapi-json --file ../frontend/src/api/openapi.json
	$(OPENAPI_TS) -o src/api/schema.d.ts

frontend-dev:
	pnpm --dir frontend install --frozen-lockfile
	pnpm --dir frontend dev

frontend-check:
	pnpm --dir frontend install --frozen-lockfile
	pnpm --dir frontend lint
	pnpm --dir frontend typecheck
	$(OPENAPI_TS) -o src/api/.schema.check.d.ts >/dev/null
	diff -q frontend/src/api/schema.d.ts frontend/src/api/.schema.check.d.ts >/dev/null || { rm frontend/src/api/.schema.check.d.ts; echo "frontend/src/api/schema.d.ts is stale: run make api-client"; exit 1; }
	rm frontend/src/api/.schema.check.d.ts
	pnpm --dir frontend test

.PHONY: check
check: backend-check frontend-check

.PHONY: hooks review-diff red
# Once per clone: use the versioned git hooks in .githooks/.
hooks:
	git config core.hooksPath .githooks

# Diff for a reviewer agent (it cannot run git): make review-diff BASE=<sha> NAME=<slice>
review-diff:
	@mkdir -p .scratch/review
	git diff $(BASE)..HEAD > .scratch/review/$(NAME).diff
	@echo ".scratch/review/$(NAME).diff"

# Prove a test goes red without a guard (CODING_STANDARDS.md "Tests"): replace OLD with NEW in
# FILE once, run the tests matching K, restore FILE from git (commit or stage FILE first).
# make red FILE=backend/audit/views.py OLD='if grant is None:' NEW='if False:' K=needs_a_grant
red:
	@git diff --quiet -- $(FILE) || { echo "$(FILE) has unstaged changes: stage them first"; exit 1; }
	@python3 -c "import sys; p, a, b = sys.argv[1:]; s = open(p).read(); assert a in s, 'OLD not found'; open(p, 'w').write(s.replace(a, b, 1))" "$(FILE)" "$(OLD)" "$(NEW)"
	-cd backend && uv run pytest -q -k "$(K)" 2>&1 | tail -1
	@git checkout -- $(FILE)
