# STATE

Phase: 1 — Collection (petmax.ro + pentruanimale.ro on a daily GitHub Actions cron)
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
[x] category coverage expanded 6 → 13 (litter, grooming/hygiene, accessories, toys) — ADR-0017
[x] collection moved to a GitHub Actions cron — `.github/workflows/scrape-petmax.yml`, 06:10
    Europe/Bucharest (03:10 UTC) + `workflow_dispatch`, secrets from GitHub Secrets — ADR-0018
[x] ingest is idempotent on (source, external_id, collected_date) — verified against a real
    Postgres, migration 0002 — ADR-0016
[x] **collection actually running** — first full run 2026-09-12: 4,060 listings ingested, verified
    from Neon on a separate connection (was blocked on `SCRAPER_USER_AGENT`; unblocked this session)
[x] ≥3,000 in-scope listings — **4,060**, petmax_ro alone, verified
[ ] ≥3,000 in-scope listings from **≥3 sources** — 4,060 total but from 1 source only; the volume
    is there, the source count is not
[ ] ≥7 consecutive days of history — **1 / 7** (2026-09-12, no gaps so far — too early to tell)
[ ] **≥400 products on two or more shops** — 0, and 0 by definition until a second adapter lands
    (2,495 / 4,060 = 61% of today's listings are keyable — see `make status`)
[ ] adapters for pentruanimale.ro and animax.ro — not started (deliberately out of this session's
    scope; explicitly next)
[ ] all adapters tested offline against fixtures — petmax done, two to go

## Last done

- **Migrated collection to GitHub Actions + Neon** (session 2026-09-12, "infrastructure changed"
  session). Verified the runner is not blocked by petmax.ro's Cloudflare (byte-identical fetch to
  local). Split `DATABASE_URL` (Neon, collected data) from `TEST_DATABASE_URL` (local docker,
  tests) with a mechanical guard (`tests/conftest.py::pytest_configure`, ADR-0014) so a test run
  cannot reach Neon. Ran Alembic against Neon, verified from a separate connection, added Neon
  cold-start tolerance (15s timeout + one retry, ADR-0015).
- **Made ingest idempotent** on `(source, external_id, collected_date)` — migration 0002, upsert
  in `runner.py` — so a manual run and the scheduled run on the same day cannot duplicate a row
  or double-count a day of history (ADR-0016). Verified against a real Postgres.
- **Expanded petmax category coverage 6 → 13** (litter, grooming/hygiene, accessories, toys),
  chosen from the real `sitemap_categories.xml`, not guessed. Recon estimated ~208 requests,
  ~4,990 listings, ~15–20 min wall-clock (ADR-0017).
- **Decommissioned the Windows Task Scheduler job**, replaced with
  `.github/workflows/scrape-petmax.yml` (cron `10 3 * * *` = 06:10 Europe/Bucharest during EEST,
  plus `workflow_dispatch`, GitHub Secrets only — ADR-0018). Removed `scripts/schedule_daily.ps1`
  and the `make.ps1 schedule` target rather than leave them as misleading dead code.
- **Ran the first real collection**, dispatched through the production workflow: 4,060 listings
  ingested from petmax_ro across all 13 categories in 814s / 208 pages, 0 errors, 0 volume alerts.
  `make status` now counts *consecutive* days of history and names gap dates explicitly
  (`src/pricepilot/history.py`), replacing a naive span count that could hide a gap.

## Open issues

- **Single source.** The 3,000-listing gate is cleared, but the ≥3-sources and ≥400-cross-shop-
  overlap parts of the Phase 1 gate are not — both need a second adapter, which is deliberately
  the next session's work (ADR-0010), not this one.
- **7 consecutive days is 1 so far.** The GitHub Actions cron only fires once so far (this
  session's manual `workflow_dispatch`); the first *scheduled* run is tomorrow at 03:10 UTC. A
  missed or late run would show up in `make status` as a named gap date, not a silently inflated
  span — verify this actually happens over the next week.
- **DST drift, accepted.** The cron is a fixed UTC time; after Romania's autumn changeover (last
  Sunday of October) 03:10 UTC becomes 04:10 local until spring. Documented in ADR-0018, not
  engineered around — not worth two cron entries for an hour of drift twice a year.
- **LLM transport not implemented.** `src/pricepilot/llm/client.py` ships the budget cap, cache
  key and call log; `complete()` raises. Per-token prices stay unhardcoded until the first paid
  call in Phase 2 (CLAUDE.md §0.4 — no invented numbers). ADR-0006.
- **`make` not installed.** `.\make.ps1 <target>` is the Windows path; the Makefile is kept for
  CI and the Phase 7 VPS. ADR-0003.
- **Bonus-weight titles are a trap the plan did not list.** `"8 kg + 1 kg gratuit"` and
  `"15 + 3 Kg Gratis"` — same line, same base pack, different purchasable unit and price; on the
  second form the unit sits only on the bonus number. Seeded into the fixture deliberately; needs
  to reach the Phase 3 annotation set.

## Blocked on Bogdan

Nothing right now. `SCRAPER_USER_AGENT` is set and collection is running; the model switch to
Sonnet requested last session is done. Watch items above are informational, not blockers.
