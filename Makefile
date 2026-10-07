# PricePilot task runner.
#
# On Windows, `make` is not installed. Use the shim instead: .\make.ps1 <target>
# Both dispatch to the same commands, and the real logic lives in scripts/ so neither
# file is the source of truth. See DECISIONS.md ADR-0003.

.DEFAULT_GOAL := help
.PHONY: help install lint format typecheck test status cost scrape overlap up down logs migrate revision api dev mock-store health check clean annotate

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv and install all dependencies
	uv sync --extra dev

lint: ## ruff check + format check
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-format and auto-fix
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## mypy strict
	uv run mypy

test: ## Run the test suite (offline; never touches a live site)
	uv run pytest
	node --test tests/js/annotate_review_topbar.test.mjs
	node --test tests/js/annotate_review_stale_revision.test.mjs

check: lint typecheck test ## Everything CI runs

status: ## Live project status — the command to run first each session
	uv run python scripts/status.py

cost: ## LLM spend to date by phase and model
	uv run python scripts/cost.py

scrape: ## Run one adapter: make scrape ARGS="--source petmax_ro --limit 5 --dry-run"
	uv run python scripts/scrape.py $(ARGS)

overlap: ## Cross-shop overlap count — the Phase 1 gate metric
	uv run python scripts/overlap_report.py

up: ## Start Postgres + API + mock store
	docker compose up -d --build

down: ## Stop everything (volumes preserved)
	docker compose down

logs: ## Tail all container logs
	docker compose logs -f

migrate: ## Apply database migrations
	uv run alembic upgrade head

revision: ## Autogenerate a migration: make revision m="add foo"
	uv run alembic revision --autogenerate -m "$(m)"

api: ## Run the API locally (no Docker)
	uv run uvicorn pricepilot.api.main:app --reload --port 8000

dev: ## Run the dashboard against the live DB on :8000
	PRICEPILOT_DB_DRIVER=pg8000 uv run python -m uvicorn pricepilot.api.main:app --reload --port 8000

mock-store: ## Run the mock store locally (no Docker)
	uv run uvicorn services.mock_store.app:app --reload --port 8001

health: ## Curl both health endpoints
	curl -s localhost:8000/health; echo; curl -s localhost:8001/health; echo

annotate: ## Serve the repo root for the Phase 3 annotation tool (tools/annotate.html needs http://, not file://)
	@echo "Open: http://localhost:8010/tools/annotate.html"
	uv run python -m http.server 8010 --bind 127.0.0.1

clean: ## Remove caches
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
