# STATE

Phase: 1 — Collection (petmax.ro only, on a daily schedule)
Updated: 2026-09-12

## Gate progress

Phase 0 — Foundation: **CLOSED**, verified end to end in Docker on 2026-09-12.

[x] `docker compose up -d` brings up Postgres 16 + pgvector, api, mock-store — all three healthy
[x] `make migrate` applied migration 0001; `\dt` shows products, scrape_runs, raw_listings, llm_calls
[x] pgvector extension live in the container: `vector 0.8.6`, `<=>` operator answers
[x] `/health` responds `{"status":"ok","database":true}` from inside the compose network
[x] mock-store serves 30 products / 180 days and accepted a live `PATCH /products/1/price`
[x] `make test` passes — 86 passed
[x] `make lint` passes — ruff check + format clean, mypy strict clean on 20 source files
[x] zero dollars spent

Phase 1 — Collection: in progress. Gate per CLAUDE.md §7 as amended 2026-09-12.

[x] `docs/SOURCES.md` row filled in for petmax.ro from a real fetch, not from the plan
[x] fixtures saved: `robots.txt` verbatim, one trimmed category page, provenance README
[x] petmax.ro adapter implemented behind the `Scraper` protocol, tested offline
[x] every run logs to `scrape_runs`; >40% volume drop alerts and ingests nothing — verified
[x] cross-shop overlap reported by `make status` from day one (ADR-0009)
[x] daily schedule registered — `PricePilot-scrape-petmax_ro`, 06:10 local, next run 2026-09-13
[ ] **collection actually running** — BLOCKED on `SCRAPER_USER_AGENT` in `.env` (see below)
[ ] ≥3,000 in-scope listings from ≥3 sources — 0 so far
[ ] ≥7 consecutive days of history — 0 days
[ ] **≥400 products on two or more shops** — 0, and 0 by definition until a second adapter lands
[ ] adapters for pentruanimale.ro and animax.ro
[ ] all adapters tested offline against fixtures — petmax done, two to go

## Last done

- Closed the Phase 0 Docker gate: fixed two real blockers found doing it — `.dockerignore`
  excluded `README.md` which `pyproject.toml` requires (build failed), and a pre-existing native
  Windows Postgres holds port 5432 and won the bind, so host auth failed with a misleading
  "password authentication failed". Container now publishes 5433 (ADR-0008).
- Built the petmax.ro adapter: parses `data-Gomag` for current **and** pre-discount price, and
  rejects any card whose displayed price disagrees by more than 1 leu rather than ingesting it.
- Built the cross-shop overlap proxy and wired it into `make status` (ADR-0009). Pinned it with
  tests against all four real title grammars CLAUDE.md documents for one product.
- Registered the daily Task Scheduler job and triggered it once: the full chain
  (task -> cmd -> uv -> `scripts/scrape.py` -> log) works and exits 2 on the placeholder UA.
- Applied all eight of Bogdan's decisions to CLAUDE.md, DECISIONS.md (ADR-0008..0013) and
  docs/COSTS.md: overlap gate, one-scraper-first, contact email out of the repo, spend reordered
  with GPU decoupled, demand-model circularity fixed, fine-tune reporting rule written down
  before the numbers exist.
- Found and fixed two latent bugs: `make status` crashed on Windows cp1252 when printing a box
  character, and PowerShell 5.1 mis-parsed `schedule_daily.ps1` because of five em dashes.
  The second is now guarded by a test, not a note (ADR-0013).

## Open issues

- **Collection is not yet running.** The scheduled task is installed and correct, but
  `scripts/scrape.py` refuses to start while `SCRAPER_USER_AGENT` holds the `.env.example`
  placeholder. This is deliberate (CLAUDE.md §5.4 — an honest contact, never committed), and it
  is one line in `.env` away from collecting. Every day it stays unset is a day of price history
  that cannot be recovered (ADR-0010).
- **Overlap is unmeasurable with one source.** Expected, not a problem yet. It becomes a real
  risk if the second adapter lands and the count is still far from 400 — that is the point at
  which CLAUDE.md §7 requires adding a source rather than continuing.
- **LLM transport not implemented.** `src/pricepilot/llm/client.py` ships the budget cap, cache
  key and call log; `complete()` raises. Per-token prices stay unhardcoded until the first paid
  call in Phase 2 (CLAUDE.md §0.4 — no invented numbers). ADR-0006.
- **`make` not installed.** `.\make.ps1 <target>` is the Windows path; the Makefile is kept for
  CI and the Phase 7 VPS. ADR-0003. New targets mirrored in both: `scrape`, `overlap`, and
  `schedule` (shim only — it wraps a Windows-specific script).
- **Only 6 of petmax's 134 categories are on the schedule** — food and treats for dogs and cats,
  where the overlap lives. `hrana-uscata-caini` alone is ~900 listings across 38 pages, so the
  3,000-listing gate looks reachable from these six. Breadth is added only if it is not.
- **The daily task does not run while Bogdan is logged off.** `-StartWhenAvailable` catches up a
  run missed to sleep or power-off, but a day the machine never wakes is a day lost. Continuous
  collection is a Phase 7 cron entry on the VPS, not this task.
- **Bonus-weight titles are a trap the plan did not list.** `"8 kg + 1 kg gratuit"` and
  `"15 + 3 Kg Gratis"` — same line, same base pack, different purchasable unit and price; on the
  second form the unit sits only on the bonus number. Seeded into the fixture deliberately; needs
  to reach the Phase 3 annotation set.

## Blocked on Bogdan

1. **Put your contact address in `.env`** — one line, `SCRAPER_USER_AGENT`, replacing
   `you@example.com`. Nothing else gates collection; the task fires again at 06:10 tomorrow and
   will start collecting on its own once this is set. `.env` is gitignored; `.env.example` keeps
   the placeholder (CLAUDE.md §9 — no personal detail in a committed file).
2. **Switch the session to Sonnet** for implementation work from here (`/model sonnet`).
   CLAUDE.md §4 now states Sonnet is the default and that an Opus session doing ordinary
   implementation should say so and ask. This session did the Phase 0 audit close-out and the
   adapter on Opus; the next two adapters do not need it.
