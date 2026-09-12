# STATE

Phase: 0 — Foundation (complete except the Docker check, which is blocked on install)
Updated: 2026-09-12

## Gate progress
[x] repo scaffolded: src/, services/, scripts/, alembic/, tests/, docs/, .claude/
[x] docker-compose.yml (Postgres 16 + pgvector, api, mock-store) written
[x] initial schema + migration 0001 (products, scrape_runs, raw_listings, llm_calls; vector ext)
[x] .env.example committed, .env gitignored, no secrets in repo
[x] ruff + mypy strict + pre-commit + pytest configured
[x] make targets (Makefile + make.ps1 shim for Windows)
[x] mock-store serves a seeded catalogue and accepts a price update (10 tests)
[x] /health responds and degrades correctly when Postgres is absent
[x] make status works and queries live numbers
[x] make test passes — 23 passed
[x] make lint passes — ruff check + format clean, mypy strict clean
[x] docs/AUDIT.md written
[x] zero dollars spent
[ ] `docker compose up` verified end to end — BLOCKED: Docker is not installed on this machine

## Last done
- Verified the full local toolchain: `uv sync --extra dev`, 23 tests green, ruff clean, mypy strict clean
- Built `scripts/status.py` and `scripts/cost.py`; every number is queried, none hand-written
- Built `services/mock_store` — 30 products, 180 days of price/sales history, PATCH price endpoint
- Wrote migration 0001 and enabled the pgvector extension at Phase 0 rather than Phase 3
- Wrote `docs/AUDIT.md`: six concerns, five ranked changes to the plan

## Open issues
- **Docker not installed.** The Phase 0 gate's `docker compose up` cannot be executed here. The
  compose file and Dockerfile are written but unverified. Everything else runs without Docker
  (the mock store is in-memory; the API degrades gracefully without Postgres).
- **`make` not installed.** `.\make.ps1 <target>` is the Windows path; the Makefile is kept for CI
  and the Phase 7 VPS. See DECISIONS.md ADR-0003.
- **LLM transport not implemented.** `src/pricepilot/llm/client.py` ships the budget cap, cache key
  and call log; `complete()` raises. Per-token prices are deliberately not hardcoded until the
  first paid call in Phase 2 (CLAUDE.md §0.4 — no invented numbers).
- **Phase 1 overlap risk is unmeasured.** See AUDIT concern 2. Nothing to do yet, but the Phase 1
  gate should grow a cross-shop overlap count before scraping starts in earnest.

## Blocked on Bogdan
1. **Install Docker Desktop** (and optionally `make` via `winget install GnuWin32.Make`) so the
   Phase 0 gate can be closed literally. Until then Phase 1 can still proceed — fixtures and
   adapters need no database — but nothing can be persisted.
2. **Decide on the five AUDIT changes** (docs/AUDIT.md, final table). The two that change what I do
   next are: (a) add a cross-shop overlap count to the Phase 1 gate, (b) build one scraper and put
   it on a daily schedule before building the other two.
3. **Confirm the scraper contact email** for `SCRAPER_USER_AGENT` in `.env` — CLAUDE.md §5.4
   requires an honest User-Agent with a contact, and I will not put your address in a committed
   file without you saying so.
