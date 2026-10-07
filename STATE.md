# STATE

Phase: 7 IN PROGRESS -- 7a + 7a.2 done 2026-10-07 (CI green, dashboard polished, `.\make.ps1 dev`); next 7b (deploy, needs host decision). Phases 0-3, 5, 6 CLOSED; Phase 4 POSTPONED.
Updated: 2026-10-07 (Phase 7a.2)

**Where we are:** **Phase 7a.2 DONE (ADR-0050).** Start the dashboard with `.\make.ps1 dev` (or `.\start.ps1`; sets
`PRICEPILOT_DB_DRIVER=pg8000`, runs `.venv\Scripts\python -m uvicorn`, never the blocked `uvicorn.exe`), open
http://localhost:8000. Home page = four hero tiles (matching F1 0.87 vs 0.50 zero-shot; RAG hit@1 0.85; 50
recommendations / 0 violations re-checked from SQL; 26 days / 266,200 price rows) + guard-verdict and
margin-headroom charts; product page = price-comparison bars + score pills + decision card + history chart.
Model numbers are read from the committed result files, the rest from SQL. The listings figure is reconciled:
the Phase 1 "18,585" was price ROWS after two days (10,525 distinct listings then; 11,097 distinct today).
Previous: **Phase 7a DONE (ADR-0048/0049).** CI is green again (run 37639406362; root cause: a frozen-file
hash taken on a CRLF checkout, ADR-0048). The read-only API (`/api/products`, `/api/products/{id}`,
`/api/products/{id}/history`, `/api/status`) and the dashboard (`/`, `/products/{id}`, `/status`) run locally
against Neon: `PRICEPILOT_DB_DRIVER=pg8000 uv run uvicorn pricepilot.api.main:app --reload`, open
http://localhost:8000. Screenshots: `docs/learned/results/phase7a/`. Nothing is deployed. 7b (VPS, Caddy, domain,
backups, demo GIF) waits for Bogdan's review of the dashboard and the hosting decision. $0 spent.
Previous: **Phase 6 CLOSED, gate MET (ADR-0046/0047).** The action layer turns a guard-decided
recommendation into a human-approved, logged, reversible store write. One complete cycle on real row #9
(product 2, 389.00 -> 369.90): prompt -> apply -> verified in the store price, the store `/audit-log` and
`action_log` -> second apply refused (no double write) -> rollback -> price restored and logged. Trail:
`docs/learned/results/phase6/gate-cycle.txt` (the approval was `--confirm` on Bogdan's written
instruction, not a keystroke). 991 passed / 5 skipped, 31 new tests, 8 of 8 safety mutants killed
(`scripts/mutation_check_actions.py`). Cost $0 (`llm_calls` unchanged). Phase 5's charm-within-cap question is DECIDED (ADR-0046): guard unchanged, FLAGs routed to
review; honest note: only 3 of the 12 FLAGs are the sub-20-RON case. Phase 4 stays POSTPONE.

## Gate progress

**Phase 0 — Foundation: CLOSED** (2026-09-12), all 8 gate boxes met. Full detail:
`docs/archive/phases-0-2.md`, `docs/archive/STATE-history.md`.

**Phase 1 — Collection: CLOSED** (2026-09-22). >=3,000 in-scope listings MET (18,585/18,703, 3
sources); >=7 consecutive days MET (9 days); >=400 cross-shop overlap MET (hand-verified sample,
ADR-0023/ADR-0028 #7). Full detail: `docs/archive/phases-0-2.md`.

**Phase 2 — Normalization: CLOSED** (2026-09-14). 85% attribute-accuracy gate MET at 93.2%
(261/280 symmetric); weight parsing 100% (82/82). Full detail: `docs/archive/phases-0-2.md`,
DECISIONS.md ADR-0027.

**Phase 3 — Matching: CLOSED** (2026-09-25, ADR-0030). TIE on F1 (LoRA 0.8796 vs CE 0.8737,
McNemar p=1.0000); served CE ONNX fp32 CPU, threshold 0.89, incremental batch, K=100. Full detail:
`docs/archive/phases-3.md`, `docs/audits/phase3-audit.md`.

**Phase 4 — Demand: POSTPONE** (v1 2026-09-26, v2 2026-09-27). v1 and v2 rules both FAIL R1-R3;
re-measure both times `NEEDS ARCHITECT: movement too rare` (15-16 days too short for the 28-day
history rule). `docs/learned/phase4-data-sufficiency.md`, ADR-0031/ADR-0032.

**Phase 5 — Decision engine: CLOSED** (2026-10-07). Gate: 50 generated recommendations, zero margin
violations -> **MET: 50 rows, 0 violations** (ADR-0044/0045, caveats in "Where we are"). Full detail:
`docs/archive/phases-5.md`. **Matcher precision** (`gate-s3b.md`): pre-guard 0.786 (22/28, blind, independent);
post-guard **0.92 (23/25)**, 0 wrong-gramaj -- NOT independent of the errors the guard was built from, the 2
newly surfaced links were labelled non-blind, labels Claude-written (`claude_pending_bogdan_review`); one
low-confidence label (18:animax_ro) puts it at 0.88 if wrong. Matcher gate (>=0.90) NOT claimed cleanly met.
**Phase 6 — Tool calling / action layer: CLOSED** (2026-10-07). Gate (one complete cycle end to end,
visible in logs) MET: `docs/learned/results/phase6/gate-cycle.txt`. Full detail: `docs/archive/phases-6.md`,
ADR-0047.
**Phase 4 price history:** 23 distinct collection days as of 2026-10-04 (petmax 23, animax 22,
pentruanimale 22), per the architect audit. R1 (28 days) is reachable ~2026-10-10 but R2/R3 still
fail on the pre-registered measurement -- Phase 4 stays POSTPONE, elasticity stays a labelled
placeholder.

**Dataset FROZEN 2026-09-22.** SHA-256 (`docs/learned/phase3-labels.json`, LF-normalised):
`540a4fd6ccfc52525014ac770caadbf544243dccc5a85d3fcb279fd7d052eed4` -- pinned identically in
`tests/test_labels_frozen.py`. No label may change without a reason recorded here first.

## Last done

00000000. **Phase 7a.2: dashboard polish (2026-10-07, ADR-0050):** `make.ps1 dev` + `start.ps1` + `make dev`;
   hero tiles, verdict and margin charts, price-comparison bars, shop-colour/status-colour palette validated
   with the dataviz script; `/api/overview`; listings reconciliation on the status page; 24 dashboard-API tests; reviewer findings fixed (a duplicate CSS token had turned FLAG badges and the caveat banner near-unreadable in light mode; the zero-shot baseline now also shows the all-'match' F1 0.51; Chart.js pinned with SRI). Light mode and a true 390px phone width were NOT screenshot-verified (headless Chrome here forces dark and a 500px minimum).

0000000. **Phase 7a: CI green + API + dashboard (2026-10-07, ADR-0048/0049):** frozen-queue hash tests now
   LF-normalised; `src/pricepilot/api/` (queries, schemas, routes, Jinja2 templates, CSS); 15 API tests
   (SQLite fixtures, offline-degrade path); jinja2 added to dependencies; ADR-0047 condensed to make room.

000000. **Phase 6: action layer + one-cycle gate (2026-10-07, ADR-0046/0047):** migration 0015 `action_log`;
   `actions/{selector,store,apply,rollback}.py`; CLI `scripts/apply_recommendation.py`; gate script
   `scripts/phase6_gate_cycle.py` (trail committed); 31 tests + a mutation script; stress, mock, superseded and scenario rows refused.
00000. **Phase 5 s5b: gate made meaningful, Phase 5 closed (2026-10-07, ADR-0045):** 20 scenarios re-framed as
   GUARD STRESS-TESTS (prompt no longer announces them), 4 truncated baselines + 20 stress re-run at
   `max_tokens=1500`, old rows relabelled `s5-superseded` (nothing deleted), $0.164186; report gains the
   proposals-before-the-guard table; post-guard links labelled; ADR-0034/0036 full text archived.
0000. **Phase 5 s5: first gate run (2026-10-07, ADR-0043/0044):** guard keeps the move's direction through
   charm rounding; scenario builder; gate report with an independent floor re-check; migration 0014
   `llm_stop_reason`; 50 real rows $0.240276 -- found weak (42/45 no-change, scenarios neutralised, 4
   truncated), fixed in s5b.

00. **Phase 5 s3b: serve-time matcher + `product_matches` (2026-10-04, ADR-0039):** migration 0012
   (`UNIQUE(product_id, source)`, `CHECK score >= threshold`); `matching/serve.py` +
   `scripts/match_catalogue.py` (faithfulness gate first, brand-block candidates, >0.89 kept, one
   per (product, shop), Decimal prices from latest `raw_listings`); blind worksheet
   `docs/learned/results/phase5/match-verification-queue.csv` (28 rows, no score/label).
   **DB-shape finding (Task 0):** `content_hash` is title-only and shared across shops (11,152
   hashes in 1 shop, 18 in 2), so shop + price come from `raw_listings`; 6 of 11,074 current
   (shop, hash) pairs have several SKUs under one title. Blocks: 6 of our brand keys exceed 300
   (royalcanin 776, brit 745, hills 387, purina 371, calibra 332); `smolke` has no block (0).
0. **Phase 5 session 3: catalogue synced into `products` (2026-10-04, ADR-0038):** migration 0011
   adds nullable `products.net_weight_g` (applied to Neon); `scripts/sync_catalogue.py` upserts the
   30 mock-store products (`get_catalogue()` public accessor) keyed on `id`, Decimal money, no
   float. Verified on the real DB: 30 rows, 0 duplicate SKUs, unchanged after a second run, 0
   rows disagreeing with `_CATALOGUE`. psycopg's libpq DLL is blocked by Application Control again
   today, so all DB work ran on the new opt-in `PRICEPILOT_DB_DRIVER=pg8000` fallback
   (`src/pricepilot/db.py::resolve_database_target`, also used by `alembic/env.py`; `.env`
   untouched). Note: `docs/learned/psycopg-application-control-block.md`.
1. **Neon test-guard hole fixed (2026-09-28, ADR-0037, `reviewer` catch):** `pytest_configure`
   popped `DATABASE_URL` when `TEST_DATABASE_URL` was absent, expecting "fully offline" --
   `Settings(env_file=".env")` actually fell back to `.env`'s real Neon credential, so a plain
   `pytest` run silently hit Neon (session 2's new DB test was the first to expose it; no data
   lost, only idempotent `policy_chunks` upserts). Fixed: an explicit unreachable sentinel
   (`offline.invalid`, fails DNS in <1s) instead of popping, with an end-to-end regression test.
   Verified the guard now also refuses an explicit attempt to point `TEST_DATABASE_URL` at Neon.
2. **Phase 5 session 2: policy RAG index + retrieval eval (2026-09-28, ADR-0036):** migration 0010
   `policy_chunks` applied to the real database; `scripts/build_policy_index.py` chunks the 7-section
   policy, embeds with the shared local model, upserts idempotently (verified: 7 rows, still 7 after
   a second run); `retrieve_policy()` ranks by pgvector cosine, text only. Eval (20 pre-registered
   questions): hit@1 0.850 (17/20), hit@3 0.950 (19/20), MRR 0.912 -- one miss (section 5, a
   single-sentence claim in a mixed section), not chased further to avoid tuning to the eval.
   **Process note:** the eval CSV's commit landed after an exploratory run of the eval script, not
   strictly before as the session brief specified -- content was authored blind (before any query
   ran) and unedited since, disclosed in the commit message rather than reordered to look clean.
3. **Phase 5 session 1b: guard leaves a genuine no-change unrounded (2026-09-28, ADR-0034
   addendum):** architect audit found no mock-store catalogue price is itself a charm value, so
   `enforce`'s round-first order turned an unchanged (`proposed_price == current_price`)
   recommendation into a small, unintended move -- e.g. 179.00 -> 178.90 on zero stock, an
   unchecked discount (policy §7: "doing nothing is always acceptable"). Fixed: a no-change now
   short-circuits before `charm_round` and is APPROVEd unrounded, or FLAGs if the kept price is
   already below the category floor. 3 new tests; guard suite 55, full suite 838 green.
4. **Phase 5 session 1: policy thresholds config + margin/price guard (2026-09-28, ADR-0034):**
   `config/pricing-policy.toml` + validated Pydantic loader (`policy/thresholds.py`) + deterministic
   guard (`policy/guard.py::enforce`) composing charm-round-first, then floor/eligibility/speed on
   the final price. `reviewer` caught a real bug pre-push (checks ran against the unrounded
   proposal, letting rounding slip an APPROVE past eligibility or speed); fixed the same session --
   round first, FLAG (not REJECT) a speed breach, raise on non-positive money. 52 guard tests with
   computed expected values incl. two rounding-induced regressions; full suite 835 green.
5. **Pricing-policy APPROVED v0.2 + margin basis decided (2026-09-27, ADR-0033):** Bogdan approved
   the Phase 5 RAG corpus; margin defined on the gross shelf price to match `Product.margin_pct`
   and the VAT-less mock-store data; §1 wording and the number-source line corrected; trimmed to
   the §7 300-500 word budget (500).

Older items (stale note corrected, storage fix, Phase 4 rule v2, Phase 3 closed):
`docs/archive/STATE-history.md`.

## Open issues

- **Phase 7a loose ends (the listings-number item is RESOLVED, ADR-0050):** `scripts/ingest_labels.py` / `split_annotation_queue.py` still hash the raw queue
  (false tamper alarm off Windows, ADR-0048). Chart.js loads from a CDN (needs internet in the browser). The Docker
  CI job took ~10 min this run (image build installs torch); the `check` job takes ~1.5 min.

- **Charm rounding overshoots the daily cap (ADR-0045; DECIDED in ADR-0046: accepted, FLAG -> review):** all 12 FLAGs in the refreshed
  gate are cap refusals: 11 are exact -5% cuts that nearest-charm rounding overshot (879.00 -> 834.90,
  11.00 -> 9.99) and 1 is a +5% rise (p18, 5.20 -> 5.46) rounded UP to 5.99 by the direction rule. Below
  ~20 RON the 1-RON charm step exceeds the 5% cap. Fix = a within-cap rule handling both directions (guard
  change, ADR-0034/0043). Cannot cause a margin violation.
- **Live gate evidence for the floor is thin by construction (ADR-0045):** zero proposals over the cap or
  below a floor; the 5% cap keeps one step far from every floor (margins 28-56% vs floors 12-30%). The floor
  is demonstrated by the guard's unit tests, the 400k reviewer sweep and the mock below-floor sweep.
- **Stress rows deceive the model under test by design** (prompt shows scaled prices as real); disclosed in the
  row (`stress_*`), the competitor JSON (`observed_price`) and the report. Never present them as market data.
- **Prose/TOML drift is now tested** (`test_policy_prose_drift.py`); day counts (14 / 2 / 7+ days)
  have no TOML key yet (guard scope gaps) and sit in an explicit allowlist. `retrieve_policy` still
  does not check `policy_chunks.source_sha256` against the live prose.
- **`price_7d_ago` is synthetic and includes the mock store's promo windows (review, ADR-0042):** if
  day -7 sat in a 78-90% promo, today's price is 11-28% above it and almost any move breaches the
  15% weekly cap -> FLAG for reasons unrelated to the LLM. It is labelled per row; s5's report must
  say so when it gives the APPROVE/FLAG mix. Also drifts from `products.current_price` after Phase 6.
- **LLM cache hits become non-mock rows at $0 (review):** re-running an identical prompt in s5 yields
  an `is_mock = false` row with cost 0; decide before the run whether those count toward the 50.
- **Mock `recommendations` rows (run_label `s4-mock`, `is_mock = true`) stay in the table** as wiring
  evidence; the gate report counts `is_mock = false` rows only (it refuses mock rows).
- **`mypy` reports 1 pre-existing error** (`scripts/score_match_labels.py:33`, from the ADR-0041
  commits, not s4); `ruff` clean, 919 tests green.
- **Guard scope gaps, all deferred because the mock store has no field for them yet (ADR-0034)**
  -- not stubbed or faked: MAP-restricted brands (policy §2, no MAP field on `Product`); new-product
  age < 14 days (§3, no `listed_at`); manual price lock (§3, no lock field); promotion
  duration/competitor-hold/match-score filters (§4-5, need the decision engine + SQL, sessions 3-4).
- **After a real apply, `products.current_price` (Postgres) is stale (ADR-0047):** `apply_recommendation`
  writes the store only. A store -> DB sync is needed before the next decision run (not built), and
  `sync_catalogue.py` must NOT be re-run (it would revert the DB copy to the seed). The mock store itself
  keeps prices and its `/audit-log` in process memory, so a restart resets both; rollback then refuses as
  drift, correctly.
- **Phase 6 gate approval was `--confirm`, not a keystroke:** the human-approval prompt is real
  (`Proceed? [y/N]`) and `apply` has no way to run without an approver, but the gate cycle was run
  non-interactively on Bogdan's written instruction. Run it yourself without `--confirm` if you want the
  interactive trail.
- **Charm FLAGs split 3 / 9 (ADR-0046):** 3 are sub-20-RON items, 9 are 134-879 RON items overshooting the
  cap by 0.02-0.30 pp. A within-cap rounding rule (future work) would clear most of the 9.
- **RAG model pinning (session 2 review, judgement call):** `pricepilot.embeddings.SentenceTransformer
  (MODEL_NAME)` has no `revision=` pin, and `policy_chunks` stores no model name/revision. A
  future HF revision bump or `sentence-transformers` major version change would silently rank
  against a different vector space. Not fixed this session -- low likelihood before Phase 7,
  revisit if the VPS/Kaggle environment ever diverges from the dev box's installed version.
- **`test_policy_retrieval.py` has zero executing coverage in this environment (ADR-0037 review,
  finding accepted as-is):** tried reading `TEST_DATABASE_URL` from `.env` as a fallback (safe --
  it always names the local docker Postgres, still passes `assert_safe_for_tests`) so the tests
  would actually run when docker is up; reverted after measuring it: on this machine, checking an
  unreachable `localhost:5433` takes ~30s per attempt (not an instant refusal) and
  `connect_with_wakeup_retry`'s one retry doubles that to ~60s added to every plain `pytest` run
  whenever docker is down -- worse than the coverage gap it would have closed. `docker compose up`
  + a real `TEST_DATABASE_URL` env var remains the only way to exercise these tests locally; same
  class of gap as the pre-existing `get_payload()` note below.
- **ADR-0037 review, lower-priority items not acted on:** a Linux host could set a lowercase
  `database_url` env var that `assert_safe_for_tests` (checks only the uppercase key) would miss --
  unlikely on this Windows dev box or Neon, worth a look before the Phase 7 VPS. The guard is
  enforced once, in `pytest_configure`, with no second check at `get_engine()` itself -- judged
  sufficient for now (a single, well-tested enforcement point, not defense-in-depth); revisit if
  a future test ever needs to delete/re-set `DATABASE_URL` mid-session the way the regression test
  above briefly does.
- **Neon Free storage (0.5 GB) projected to fill ~2026-12-03** (ESTIMATE, ADR-0032) -- re-run
  `scripts/measure_storage_backfill.py` for a fresh estimate; needs a decision before then. A
  one-off backfill (21.4 MB potential) is identified but not run -- destructive, needs a local
  export first.
- **LLM prompt caching (§5.3) not implemented** -- `client.py` has a disk response cache but no
  provider-side prompt caching on the system prompt. Optional for 50 recommendations; revisit if
  the decision-engine token cost warrants it.
- **Rule v2's decorative-promo suppression cannot reveal a real masked price change by
  construction** -- documented, a v3 decision if Phase 4 reopens.
- **`get_payload()`-routed callers have no end-to-end test against a real Postgres** (only pure
  logic + in-memory SQLite). Low priority.
- **Matcher top-100 cap accepted (ADR-0040):** 5 listings >= 0.89 beyond the cut across 13 products;
  revisit on GitHub Actions after deployment if they matter.
- **Matcher is CPU-slow locally (~10 pairs/s)**; fine for 30 products, Phase 7 ONNX covers serving.
- **`psycopg` import is intermittently blocked (Application Control) -- recurred 2026-10-04.**
  Detect with `.venv\Scripts\python -c "import psycopg"`; fall back to
  `PRICEPILOT_DB_DRIVER=pg8000` for any DB command (ADR-0038). The pg8000 path is untested by the
  test suite (tests are offline) -- verified only by the live sync/migration runs.
- **Catalogue sync reviewer notes (ADR-0038):** `sync_catalogue.py` always writes the SEEDED
  price/stock, so re-running it after Phase 6 applies a price change would revert it -- guard or
  sync from the live store first. `pg8000` is a hard runtime dep (ships in the Docker image) --
  make it an optional extra before Phase 7 if image size matters.
- **`products.id` sequence is not advanced by the sync** (explicit ids 1-30 are inserted); a future
  insert relying on the serial default would collide. Nothing inserts into `products` besides the
  sync today.
- **`pytest`'s console-script `.exe` is blocked** by Windows Application Control -- use
  `.venv\Scripts\python -m pytest`.
- **`select_threshold.py` and `score_predictions.py` duplicate `_load_eval_view`** -- extract into
  `src/pricepilot/matching/` before a third caller. ADR-0028 #19.
- **`species` field disagrees with its title on 53/10,532 rows (0.50%)** -- Phase 2 closed, not
  fixed. ADR-0028 #13.
- **Brand extraction has no title-only fallback** -- 3/10,503 rows (petmax), low priority.
- **pentruanimale.ro's regulated-product exposure is "not measured", not "clean".**
- **`make` not installed** on this machine; use `.\make.ps1 <target>` (ADR-0003).
- **Precision at K=100 on real candidates unmeasured** (ADR-0030) -- hand-verified sample at Phase 7.

## Blocked on Bogdan

Nothing blocks Phase 7. Optional: review the Claude-written match labels (`gate-s3b.md`, ADR-0040) and the low-confidence 18:animax_ro; run `scripts/phase6_gate_cycle.py` without `--confirm` for the interactive trail; decide when to build the store -> DB price sync (ADR-0047).
Phase 4/storage: the one-off payload backfill decision (21.4 MB potential, ADR-0032) -- not urgent.
Phase 7: hosting shortfall ~$4-6 (ADR-0030) -- decide then (host 2 months, or raise "available" by ~$5).
