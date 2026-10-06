# STATE

Phase: 5 — Decision engine (RAG + recommendation). Phases 0-4 CLOSED / POSTPONED as below.
Updated: 2026-10-07 (s3b guard)

**Where we are:** Phase 5 sessions 1/1b/2/3/3b DONE. **s3b (2026-10-04, ADR-0039):** serve-time
matcher built (torch fp32 CPU from `models/ce-ft-best`, NOT ONNX -- the zip is HF safetensors;
ONNX is a Phase-7 concern). It reproduced the committed PyTorch-fp32 predictions (max |diff|
1.8e-6, 0 flips) only after fixing a tokenizer mismatch (transformers 5.17 `</s></s>` vs
`tokenizer.json` `</s>`). `product_matches` (migration 0012): 28 links pre-guard (blind labels, Claude-written: precision
0.786 = 22/28, wrong-gramaj 0%). **2026-10-07, ADR-0040/0041:** coverage is reported, not gated;
a deterministic attribute-consistency guard (category / life-stage / flavour) now runs after the
cross-encoder: **28 -> 25 links, 13 of 30 products** (animax 8, pentruanimale 7, petmax 10); it
removed 5 of the 6 known FPs (the generic-Mousse vs "cu Pui" one survives by design). **2 links
newly surfaced** (the guard frees a slot for the next >= 0.89 candidate) and are NOT in the 28
labels. **Gate PENDING the architect's post-guard precision** (needs those 2 labelled). Phase 4
stays POSTPONE. Dataset FROZEN 2026-09-22, SHA-256 below.

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

**Phase 5 — Decision engine: IN PROGRESS** (started 2026-09-27). Gate: 50 generated
recommendations, zero margin violations. **Revised sub-sequence (2026-10-04, ADR-0038; replaces
the old "session 3 = decision engine")**: (1) policy thresholds config + guard [DONE, ADR-0034];
(2) policy RAG index + retrieval eval [DONE, ADR-0036]; (s3) sync our 30-product catalogue into
`products` [DONE 2026-10-04, ADR-0038]; (s3b) serve-time cross-encoder matcher -> `product_matches`
(our products vs `norm_listings`, >=0.89) [BUILT 2026-10-04, ADR-0039; guard ADR-0041 2026-10-07:
28 -> 25 links, 13/30 products; gate PENDING architect's post-guard precision, ADR-0040]; (s4) decision
engine (SQL prices + matched competitor prices + labelled elasticity placeholder + RAG policy ->
LLM[mocked] -> guard -> full trace), $0; (s5) the 50 recommendations on the real LLM (SPEND ~$2),
zero-violation report. LLM transport done (`client.py`); §5.3 prompt caching is an optional gap.
**Phase 4 price history:** 23 distinct collection days as of 2026-10-04 (petmax 23, animax 22,
pentruanimale 22), per the architect audit. R1 (28 days) is reachable ~2026-10-10 but R2/R3 still
fail on the pre-registered measurement -- Phase 4 stays POSTPONE, elasticity stays a labelled
placeholder.

**Dataset FROZEN 2026-09-22.** SHA-256 (`docs/learned/phase3-labels.json`, LF-normalised):
`540a4fd6ccfc52525014ac770caadbf544243dccc5a85d3fcb279fd7d052eed4` -- pinned identically in
`tests/test_labels_frozen.py`. No label may change without a reason recorded here first.

## Last done

000. **Phase 5 s3b close: consistency guard (2026-10-07, ADR-0040/0041):** `matching/consistency.py`
   rejects category / life-stage / flavour conflicts after the >= 0.89 cut, before one-per-shop
   selection; computed unit tests; `reviewer` findings fixed (a36ad6a). Re-run twice, identical
   output (only timing differs). `guard-effect.csv` lists 5 removed + 2 newly surfaced links.
   Pre-guard baseline kept in `gate-s3b.md`. Cost $0.
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

- **Guard scope gaps, all deferred because the mock store has no field for them yet (ADR-0034)**
  -- not stubbed or faked: MAP-restricted brands (policy §2, no MAP field on `Product`); new-product
  age < 14 days (§3, no `listed_at`); manual price lock (§3, no lock field); promotion
  duration/competitor-hold/match-score filters (§4-5, need the decision engine + SQL, sessions 3-4).
- **Phase 6 note (session 1b review):** an `enforce()` APPROVE with `price == current_price` (the
  no-change path) is a real price, but not necessarily a charm value -- tool calling must treat it
  as a no-op, never a write to the mock-store `update_price` endpoint.
- **RAG model pinning (session 2 review, judgement call):** `pricepilot.embeddings.SentenceTransformer
  (MODEL_NAME)` has no `revision=` pin, and `policy_chunks` stores no model name/revision. A
  future HF revision bump or `sentence-transformers` major version change would silently rank
  against a different vector space. Not fixed this session -- low likelihood before Phase 7,
  revisit if the VPS/Kaggle environment ever diverges from the dev box's installed version.
- **Prose/TOML drift (session 2 review):** `retrieve_policy` never checks `policy_chunks.
  source_sha256`/`doc_version` against the live `docs/policy/pricing-policy.md`, and nothing
  checks the prose's stated numbers (e.g. "12%") against `config/pricing-policy.toml`'s actual
  values. The guard, not the LLM, is still the final authority on price, so this cannot cause a
  margin violation -- but a stale or drifted citation in an LLM's rationale is a real risk for
  session 3 to design around (e.g. treat retrieved text as illustrative, never authoritative, in
  the prompt).
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
- **Matcher truncation loses real candidates (ADR-0039):** the audit found 5 listings >= 0.89
  beyond the top-100 cosine cut across 13 products with blocks > 300. Scoring whole blocks costs
  ~12 min of CPU. Decision for the architect before the labelled gate is scored.
- **ADR-0038 coverage criterion unreachable:** needs >= 15 of 30 products with a correct match;
  only 14 have any link. Do not edit ADR-0038 -- a new ADR if the criterion changes.
- **Matcher is CPU-slow locally (~10 pairs/s)**; fine for 30 products, Phase 7 ONNX covers serving.
- **`psycopg` import is intermittently blocked (Application Control) -- recurred 2026-10-04.**
  Detect with `.venv\Scripts\python -c "import psycopg"`; fall back to
  `PRICEPILOT_DB_DRIVER=pg8000` for any DB command (ADR-0038). The pg8000 path is untested by the
  test suite (tests are offline) -- verified only by the live sync/migration runs.
- **50 recommendations vs 30 products (s4/s5 must decide):** the gate needs 50 recommendations
  but our catalogue has 30 products, and only matched products get competitor prices. s4 must
  define how 50 arise (e.g. several price scenarios per product) before s5 spends money.
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

Phase 5: review the Claude-written labels (`match-verification-labels.csv`, `claude_pending_bogdan_review`), label the 2 newly surfaced links (`guard-effect.csv`), then the architect computes post-guard precision into `gate-s3b.md`. SPEND approval before the 50-recommendation run (est. ~$2, ADR-0030) -- at s5.
Phase 4/storage: the one-off payload backfill decision (21.4 MB potential, ADR-0032) -- not urgent.
Phase 7: hosting shortfall ~$4-6 (ADR-0030) -- decide then (host 2 months, or raise "available" by ~$5).
