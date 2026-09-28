# DECISIONS

Append-only architecture decision records. Context → decision → alternatives rejected → date.
Read this when you cannot remember why something is the way it is, and before an interview.

---

## Index (archived ADRs)

Full text of every entry below: `docs/archive/DECISIONS-0001-0027.md`.

| ADR | Title | Date |
|---|---|---|
| 0001 | uv as the package and Python-version manager | 2026-09-12 |
| 0002 | The mock store holds state in memory, not in Postgres | 2026-09-12 |
| 0003 | A Makefile plus a PowerShell shim, with the logic in `scripts/` | 2026-09-12 |
| 0004 | Only Phase 0–2 tables exist in migration 0001 | 2026-09-12 |
| 0005 | `raw_listings` is append-only; one row per (listing, observation) | 2026-09-12 |
| 0006 | The LLM transport is not implemented in Phase 0 | 2026-09-12 |
| 0007 | Money is `Numeric`, never `float`, everywhere | 2026-09-12 |
| 0008 | Postgres is published on host port 5433, not 5432 | 2026-09-12 |
| 0009 | Cross-shop overlap is a Phase 1 gate condition, measured by a proxy key | 2026-09-12 |
| 0010 | One scraper on a schedule before the other two are written | 2026-09-12 |
| 0011 | Hosting is reserved first; GPU fine-tuning is a week-5 decision, and starts with a smoke run | 2026-09-12 |
| 0012 | The demand model is graded against a naive baseline on real prices, never against the planted elasticity | 2026-09-12 |
| 0013 | Every `.ps1` in this repo is ASCII-only, enforced by a test | 2026-09-12 |
| 0014 | Two databases, explicit split, enforced mechanically | 2026-09-12 |
| 0015 | Neon cold-start: a 15s connect timeout, one retry, applied at both call sites | 2026-09-12 |
| 0016 | `raw_listings` ingest is idempotent within a day, amending ADR-0005 | 2026-09-12 |
| 0017 | petmax category coverage expanded from 6 to 13, chosen from the real sitemap | 2026-09-12 |
| 0018 | Collection moves from Windows Task Scheduler to a GitHub Actions cron | 2026-09-12 |
| 0019 | Collected data moves to Neon, a managed Postgres, at $0 | 2026-09-12 |
| 0020 | `robots.txt` is fetched through our own honest client, not `RobotFileParser.read()` | 2026-09-12 |
| 0021 | The overlap proxy key is a floor estimate; it was tuned for precision, not recall | 2026-09-12 |
| 0022 | pentruanimale.ro's search pagination has a hard ~600-product-per-category ceiling | 2026-09-12 |
| 0023 | Cross-shop overlap is measured by a hand-verified random sample, not by the proxy key | 2026-09-13 |
| 0024 | animax.ro adapter: Shopify (not Magento), read via `products.json` | 2026-09-13 |
| 0025 | Regulated-product detection: line-code tokens only; quarantine, never delete | 2026-09-14 |
| 0026 | Phase 2 normalized layer: `norm_listings` schema, content_hash as a global title-only cache key, weight/volume as a checked invariant, dosage bands stay text, deterministic extraction first | 2026-09-13 |
| 0027 | product_line extraction design; breed_size/life_stage gap report stays diagnostic-only; flavour/food_form tables extended from a checked sample | 2026-09-13/14 |

---

## ADR-0028 — Phase 3 (condensed)

**Context.** Phase 3 (Matching) ran 2026-09-15 through 2026-09-24 across many sessions: retrieval,
annotation tooling, labelling, the baseline, the fine-tune, and the serving benchmark. The full,
uncondensed record — every addendum (#1 through #25), every intermediate figure, every retracted
or superseded finding — is preserved at `docs/archive/DECISIONS-0028-phase3-full.md`. Below are
only the decisions that are still currently valid, i.e. the ones the Phase 3 audit and Phase 4
onward actually need.

- **Frozen dataset + SHA-256.** 997 decisions / 959 distinct pair_ids, M354/N634/S9, frozen
  2026-09-22. SHA-256 (`docs/learned/phase3-labels.json`, LF-normalised):
  `540a4fd6ccfc52525014ac770caadbf544243dccc5a85d3fcb279fd7d052eed4`, pinned in
  `tests/test_labels_frozen.py`. No label may change without a reason recorded in STATE.md first.
  (addendum #18)
- **Product-level split + counts.** TEST/TRAIN_VAL split via connected components over listing
  `content_hash`, not a pair-level random split: TEST 287 distinct pairs (300 rows, 97 M / 187 N /
  3 S, 284 scored), TRAIN_VAL 672 distinct pairs (697 rows, 222 M / 444 N / 6 S, 666 scored), 0
  listing overlap between splits, TEST blind (no rules-engine suggestion ever shown, enforced three
  independent ways). (addendum #10, #16)
- **S dropped from every trainable/scored count.** TRAIN_VAL's 672 distinct pairs -> 666 trainable
  after dropping 6 S; TEST's 287 -> 284 scored after dropping 3 S. S is never a positive or a
  negative — it is excluded, not miscounted as either. (addendum #16, #19)
- **Threshold only via `select_threshold.py`, on validation only.** That script is the one place a
  threshold may be chosen, swept against TRAIN_VAL's 134-pair validation split only (never TEST).
  `score_predictions.py` takes `--threshold` as a required argument with no default and no
  selection code path, so which script ran answers "did this see TEST while choosing anything".
  (addendum #19)
- **TEST-touch ledger: once per model id, `--rescore` only with a reason — 7 entries.**
  `docs/learned/results/test-touch-ledger.json` is an append-only, code-enforced gate:
  `score_predictions.py` refuses a second TEST run for a `model_id` unless `--rescore` is passed
  with `--reason`, both recorded. Entries: `mmarco-mMiniLMv2-zeroshot`,
  `mmarco-mMiniLMv2-finetuned-ep6`, `qwen2.5-0.5b-lora-ep8`, `hosted-claude-sonnet-5-zeroshot`,
  `mmarco-mMiniLMv2-finetuned-ep6-int8`, `qwen2.5-0.5b-lora-ep8-onnxfp32-cpu`,
  `hosted-claude-sonnet-5-zeroshot-v2`. No TEST touch for any LLM int8 variant. (addendum #19, #25)
- **The tie verdict.** Against the pre-registered rule: cross-encoder TEST F1 0.8737 vs. LoRA TEST
  F1 0.8796 — every metric's CI overlaps, McNemar exact p = 1.0000 (8 vs. 9 discordant of 284
  scored pairs). **Verdict: a TIE on F1.** Per CLAUDE.md §7's tie rule, the item 8 serving
  benchmark is the result and F1 is the parity claim; the cross-encoder baseline was never re-run,
  retuned or weakened. (addendum #22)
- **CE retrain REPRODUCED.** The fine-tuned cross-encoder's epoch-6 weights were lost (only
  prediction files were saved from the original run); a reproduction rule
  (`docs/phase3-ce-reproduction-rule.md`) was written before the retrain ran. Verdict:
  **REPRODUCED** — 0 decision flips at threshold 0.89 across all 959 fine-tuned pairs, max and mean
  score diff exactly 0. No new ledger entry, no TEST touch. (addendum #23)
- **Serving protocol + gates.** `docs/phase3-serving-benchmark-protocol.md` was pre-registered
  before any benchmark code existed. G1 (exported model vs. in-notebook fp32 reference) PASSES for
  both models (CE max|diff| ~4e-06, LLM max|diff| ~1e-05, 0 decision flips) — every serving number
  below is therefore trustworthy per protocol 5.9. G1b/G2 are reported, not gating. (addendum
  #23, #24)
- **CE int8 drop (p=0.0042).** Cross-encoder int8 (default ORT dynamic quantization): TEST F1
  0.8235 vs. fp32's ledgered 0.8737 — McNemar exact p=0.0042, driven entirely by the true-N side
  (default int8 adds false positives). One new TEST touch
  (`mmarco-mMiniLMv2-finetuned-ep6-int8`). (addendum #24)
- **LoRA int8: no eligible config, on two different CPUs.** The default int8 config is
  non-discriminating on Kaggle's AMD EPYC CPU (validation median P(Yes) not separated by class) —
  no TEST touch taken. Protocol 5.11 pre-registered two candidate fixes (V2, V3) before any
  variants code existed; both were run and **both NON-ELIGIBLE**, this time on a different (Intel)
  CPU — refuting "AMD-specific" and weakening "per-tensor/saturation only". No TEST prediction file
  for any of V1/V2/V3 was ever read. (addendum #24, #25)
- **LoRA served as ONNX fp32 CPU.** Per protocol 5.11's pre-registered fallback: TEST F1 0.8750,
  one new ledger entry, McNemar vs. the ledgered fp16-GPU fine-tune p=1.0000 on both label subsets
  — a parity result, exactly what re-exporting the same weights at a different precision on
  different hardware should look like. (addendum #25)
- **Hosted v1/v2, including the retracted diagnosis.** Hosted zero-shot `claude-sonnet-5`
  (`llm-prompt-v1`, fixed threshold 0.5, not a fair accuracy comparison with the fine-tuned models):
  v1 F1 0.9082, but 40/287 replies came back empty (`max_tokens=5`). A session-2 diagnosis ("no
  request-config defect reproduced", from one diagnostic call that happened to land on an easy
  validation pair) was **WRONG and RETRACTED**. Protocol 5.12 (pre-registered before any v2 code
  existed) corrected it: a v2 run (`max_tokens=64`, $0.416178 spent after an explicit
  `SPEND:`/"yes") cut unparseable replies to 11/287 and showed 40 calls had used a `thinking`
  content block — exactly matching v1's empty-reply count, confirming truncation, not a settled
  "no". v2 TEST F1 0.9036. (addendum #23, #25)
- **Open questions carried to the Phase 3 audit:** decided in ADR-0030.

Full text, every addendum, every retracted or superseded number:
`docs/archive/DECISIONS-0028-phase3-full.md`.

## ADR-0029 — Context diet: live files vs `docs/archive/`

**Context.** CLAUDE.md (~9,500 tok), STATE.md (~27,600 tok) and DECISIONS.md (~79,700 tok) load
on every turn/session; most of that was closed-phase history, and it was only going to keep
growing every phase.
**Decision.** Move closed-phase history to `docs/archive/` verbatim (nothing deleted); condense
the live files to a hard line budget (CLAUDE.md <=400, STATE.md <=400, DECISIONS.md <=600),
enforced by `tests/test_context_budget.py`; verify nothing was lost with
`scripts/check_archive_integrity.py` (`tests/test_archive_integrity.py`).
**Alternatives rejected.** Deleting old ADRs/history outright — CLAUDE.md section 11 keeps them
for interview prep. A token-count-only budget with no test — a soft limit erodes one session at a
time; a failing test is a limit that holds.
**Date.** 2026-09-25

## ADR-0030 — Phase 3 closed: served model, K, hosting reserve

**Context.** Phase 3 audit (`docs/audits/phase3-audit.md`, 2026-09-25) recomputed all 7 ledger F1s,
the frozen hash and every serving-table cell: all reproduce. Fine-tuned LoRA 0.5B and fine-tuned
cross-encoder TIE on F1 (0.8796 vs 0.8737, McNemar p=1.0000); the tie rule says cost and latency decide.
**Decision.**
- **D1 Served model:** cross-encoder mMiniLMv2 ep6, ONNX fp32, CPU, threshold 0.89 (TEST F1 0.8737,
  p50 79 ms, 963 MB peak RSS). CE int8 is reported, not served (F1 drop, McNemar p=0.0042). LoRA is a
  result, not a production component (tie on F1, 26x slower p50, 2347 MB peak RSS). Hosted is not used
  for bulk matching. Mode: incremental batch after each daily collection run, only new/changed
  `content_hash` pairs; not real-time per request.
- **D2 Candidates:** K=100. The full re-match (first deployment, model change) runs off the VPS on
  Kaggle's free CPU with the same ONNX file; the VPS scores only new/re-titled listings daily. At most
  one match per (our product, competitor shop), highest score wins. Precision at K=100 on real
  candidates is UNMEASURED; hand-verified sample of produced links at Phase 7 (as ADR-0023).
- **D3 Hosting reserve:** ~$15 no longer covers 3 months. ESTIMATE: CX23 3 x EUR 5.49 x 1.21 VAT x
  1.1411 = ~$22.7 (2 months ~$15.2), IPv4 UNVERIFIED and excluded; available $19.18. Reserve becomes
  ~$23 (ESTIMATE); Phase 5 reserve ~$2 (ESTIMATE, re-estimated from real token counts). Shortfall
  (~$4-6) is a Phase 7 decision for Bogdan: host 2 months, or raise "available" by ~$5.
- **D4 Archive:** CLAUDE.md section 7 Phase 3 text moved verbatim to `docs/archive/phases-3.md`;
  superseded CLAUDE.md lines in `docs/archive/claude-md-superseded-2026-09-25.md`.
**Alternatives rejected.** CE int8 (13 extra false positives for 24 ms nobody waits for); LoRA ONNX
fp32 (same accuracy, 26x slower, 2.3 GB on a 4 GB box shared with Postgres + API + Caddy); hosted
zero-shot (F1 0.9036, not significant vs CE p=0.36 post-hoc; ~6,400x the CE cost per 1k, data leaves
the box); K=20 (blocked recall 74% vs 96% at K=100); full re-match on the VPS (23.85 h at K=100 on
the 2-thread proxy).
**Date.** 2026-09-25

## ADR-0031 — Phase 4 data-sufficiency measurement: POSTPONE

**Context.** Before any demand model, the pre-registered rule (`docs/phase4-data-sufficiency-rule.md`,
committed before any number) asks whether real price history is long and movement frequent enough.
**Decision.** Measured 2026-09-26 (`scripts/measure_price_movement.py`, read-only, `docs/learned/phase4-data-sufficiency.md`):
14/14/15 collection days (need >=28 in 2 of 3 sources), 1 strict evaluable holdout event (need 200),
0 training events (need 200): R1-R3 FAIL, **POSTPONE**. Projection (ESTIMATE, per-cell strict
rate per eligible day) returned `NEEDS ARCHITECT: movement too rare`; Claude Code does not reframe the
phase. Lenient holdout count (reported, not used): 164. D2 (ADR-0030): median new `content_hash` per
day 3 / 10 / 0 (animax / pentruanimale / petmax), p90 38 / 67 / 11, max 53 / 81 / 13; x100 = daily
scorings at K=100. Storage: 182.4 MB after 15 days; Neon Free limit 0.5 GB (neon.com docs) reached
about 2026-10-25 (all tables) to 2026-11-15 (`raw_listings` only), ESTIMATE.
**Alternatives rejected.** Loosening thresholds after seeing data; building the model on the mock
store's planted elasticity (circularity trap, CLAUDE.md section 7).
**Date.** 2026-09-26

## ADR-0032 — Storage dedup (raw_payload by hash) and Phase 4 rule v2

**Context.** Neon Free (0.5 GB) projected to fill 2026-10-25/11-15 (ADR-0031); collection stops if
it does. `raw_payload` (static per-listing metadata) was the dominant recurring cost, re-stored
unchanged on every day. Separately, ADR-0031's projection was a structural artefact: 14-15 days
gives at most one strict-evaluable event, and food/litter gave only ~2 moving cells.
**Decision.** Migration 0009: `raw_payload_sha256` (nullable); ingest nulls `raw_payload` when its
hash matches that listing's most recent prior-day row, keeps the hash always; `get_payload()`
resolves it back. Applied to the collection DB and pushed (`b211a1c`); projected growth ~5.2
MB/day (was ~12.2), new fill estimate ~2026-12-03 (ESTIMATE). Rule v2
(`docs/phase4-data-sufficiency-rule-v2.md`, pre-registered before any v2 number): all categories,
decorative-strike-through suppression, raw-rate x lenient-fraction projection; R1-R3 unchanged.
**Verdict: POSTPONE again**, `NEEDS ARCHITECT: movement too rare` (`price-movement-v2.json`) --
15-16 days leaves too little runway inside the fixed 14-day holdout for the fraction to clear 30
events in 3+ cells even at the 60-day cap. Known limitation for a v3 decision: a real promo_depth
move disqualifies decorative status by construction, so suppression cannot reveal a masked base
price change; not patched into the pre-registered rule after seeing this.
**Alternatives rejected.** A one-off backfill nulling existing duplicate payloads (21.4 MB
potential, `docs/learned/storage-dedup.md`) -- deferred, destructive, needs a local export first.
**Date.** 2026-09-27

## ADR-0033 — Pricing policy approved (v0.2); margin on gross shelf price; LLM transport already exists

**Context.** Phase 5 needs the pricing-policy RAG corpus approved and the margin basis pinned (it
defines the "zero margin violations" gate). Architect audit of the v0.1 draft against the code found
two mismatches: the draft defined margin ex-VAT, but `services/mock_store` models no VAT and
`Product.margin_pct` already computes `(current_price - purchase_cost) / current_price` (gross); and
STATE/ADR-0006's "LLM transport not implemented" was stale -- `src/pricepilot/llm/client.py`
implements the transport, budget cap, `llm_calls` logging and disk cache, and was used for the
Phase 3 hosted baseline.
**Decision.** (1) Margin is the gross shelf basis `(current_price - purchase_cost) / current_price`;
no VAT is introduced. Policy §1 and the number-source line corrected; policy APPROVED as v0.2
(Bogdan, 2026-09-27); trimmed to the §7 300-500 word budget (500). (2) Phase 5 does NOT rebuild the
LLM transport. It starts at the policy-thresholds structured config read by the Python margin guard,
then RAG indexing + retrieval eval, then the decision engine, then the 50-recommendation run.
**Alternatives rejected.** Adding a VAT rate to the mock store to keep an ex-VAT margin -- a
data-model change (§4-1) with more surface to get wrong and no portfolio payoff; the mock store is
gross throughout. Re-implementing the transport -- it exists and is tested; rewriting it risks a
regression for no gain (only §5.3 prompt caching on the system prompt is an optional gap).
**Date.** 2026-09-27

## ADR-0034 — Pricing-policy thresholds as one config; the guard is the final authority

**Context.** Phase 5 session 1: the margin/price guard needs the policy's numbers (margin floors,
speed limits, discount eligibility, charm rounding) without ever parsing
`docs/policy/pricing-policy.md` at runtime (CLAUDE.md section 6, hard rule 2 -- guardrails live in
code, not prompts/prose).
**Decision.** `config/pricing-policy.toml` is the single structured source; `src/pricepilot/policy/
thresholds.py` loads and validates it (Pydantic v2: all six categories present, every floor in
(0,1), all limits positive) via stdlib `tomllib`. `src/pricepilot/policy/guard.py` reads only this
config (never the markdown doc) and exposes one composed entry point, `enforce()`: eligibility ->
margin floor -> speed limit -> charm round -> re-check floor after rounding, returning
APPROVE(price) / REJECT(reason) / FLAG(reason). All money is `Decimal` (ADR-0007). An unknown
category raises (fail closed) instead of ever being approved; a missing 7-day reference price
raises inside `within_speed_limits` and `enforce` turns that into FLAG, never a silent pass. This
guard, not the LLM that will later propose a price (session 3), is the final authority -- the LLM's
proposal is only ever a suggestion `enforce()` can override.
**Alternatives rejected.** Threshold literals inline in the guard code -- one config keeps the
guard, a future admin UI, and tests all reading the same numbers. Enforcing the margin inside the
LLM prompt -- a prompt is a suggestion; CLAUDE.md requires the rule to be code. MAP-brand,
new-product-age, manual-lock and promotion/competitor-hold checks (policy §2-5) are OUT of scope
this session -- the mock store's `Product` model has no fields for them yet (see STATE.md Open
issues); stubbing or faking them was explicitly avoided rather than inventing a number.
**Date.** 2026-09-28

**Correction, same session (`reviewer` catch before push).** The first cut checked eligibility and
the speed limit against the *unrounded* proposal, then rounded last -- charm rounding (which can
move a price by up to ~1 RON) could invalidate a check that had already passed, letting APPROVE
through with a price that violated eligibility or the speed limit (e.g. an unchanged 179.00
proposal on a zero-stock product rounds down to 178.90, an unchecked discount). Fixed (Bogdan's
choice, of 3 named options) by rounding FIRST and running every remaining check -- floor,
eligibility, speed -- against the final price. Also, per Bogdan's choice: a speed-limit breach is
FLAG, not REJECT (matches policy §4's "requires human approval" wording, and covers the case where
rounding itself introduces the breach). Also added: non-positive `cost`/`price` now raises instead
of silently producing a trivially-passing margin. Never pushed in the broken form.

**Addendum, session 1b (2026-09-28).** Architect audit: no mock-store catalogue price is itself a
charm value, so the round-first order (above) turned every genuine "keep the price"
recommendation into a small unintended move (e.g. 179.00 -> 178.90 on zero stock -- an unchecked
discount policy §7 says should never be manufactured: "doing nothing is always acceptable"). Fixed:
`enforce` now short-circuits BEFORE `charm_round` when `proposed_price == current_price` --
APPROVE `current_price` exactly (no rounding), or FLAG if that kept price is already below the
category floor (the core invariant -- never APPROVE below the floor -- holds on this path too). A
real change (`proposed_price != current_price`) is untouched: still round-first-then-check.
**Alternative rejected.** Rounding every proposal uniformly, no-change or not -- manufactures a
move out of every no-op, which is exactly what policy §7 forbids.

## ADR-0036 — RAG over the pricing policy: section chunks, shared model, numbers stay out

**Context.** Phase 5 session 2: the decision engine (session 3) needs relevant policy prose as LLM
context without sending the whole document every call. CLAUDE.md section 6, hard rule 1: RAG is
only for policy TEXT -- every number stays in SQL/`config/pricing-policy.toml`.
**Decision.** `policy_chunks` (migration 0010) co-located with `norm_listings.embedding` in the
same database -- ADR-0014's split is Neon vs. local-test-docker, not two production databases.
Chunked by the document's 7 numbered sections (a rule and its exceptions stay together), embedded
with the SAME model `norm_listings` uses (`paraphrase-multilingual-MiniLM-L12-v2`, 384-dim, local,
free) via a new shared `src/pricepilot/embeddings.py` (used by the two new Phase 5 call sites only
-- `scripts/build_embeddings.py` is untouched). `retrieve_policy()` embeds the query with the same
model and ranks by pgvector cosine distance; returns text only, never a number. No ANN index at ~7
rows. Verified against the real database this session: migration applied (`alembic current`: 0010
head), 7 rows after indexing, still 7 after a second run (idempotent, no dupes). Retrieval eval, 20
pre-registered questions: hit@1 0.850, hit@3 0.950, MRR 0.912 -- one miss not chased further
(editing the question set after seeing a metric is exactly the thing pre-registration exists to
prevent). **Process note:** the eval CSV's commit landed after an exploratory run of the eval
script rather than strictly before it as intended -- content was authored blind and unedited since,
disclosed in that commit's own message rather than silently reordered.
**Also this session:** the psycopg/Application-Control DB block that blocked earlier sessions
proved transient -- `DATABASE_URL` (Neon) connects directly again; the `pg8000` workaround
(ADR-0028) was probed once but not needed for the actual work.
**Alternatives rejected.** Sentence- or fixed-token-window chunking -- breaks rule coherence at
this document's size. A second embedding model for policy text -- a query/index mismatch is a
silent RAG bug; reusing the one model already in the stack avoids it by construction. Storing a
threshold value in `policy_chunks` for convenience -- exactly the "number retrieved by similarity"
bug CLAUDE.md names as what an interviewer looks for.
**Date.** 2026-09-28

## ADR-0037 — ADR-0014's Neon test guard had a hole: popping DATABASE_URL doesn't isolate .env

**Context.** `reviewer` review of the retrieval commit (576ea77) found: `tests/conftest.py::
pytest_configure` popped `DATABASE_URL` from `os.environ` when `TEST_DATABASE_URL` was absent,
intending "fully offline". `Settings(env_file=".env")` (pydantic-settings) falls back to `.env`'s
own `DATABASE_URL` whenever the OS environment variable is absent -- precedence is init >
env var > `.env` file, so a POPPED variable is not the same as an OVERRIDDEN one. `TEST_DATABASE_URL`
is not a real OS env var on this machine (only present inside `.env`), so `uv run pytest` /
`.venv\Scripts\python -m pytest` / `make.ps1 test` all resolved `DATABASE_URL` to the real Neon
credential. Session 2's new `tests/test_policy_retrieval.py` was the first test in the repo to
touch a database, and the first to hit this hole -- its idempotency test ran
`scripts/build_policy_index.py` as a subprocess against Neon on every plain `pytest` invocation
this session, before the fix. No data was lost (the writes are idempotent upserts of
`policy_chunks`, a table this same session created and populated on purpose, never touching
`raw_listings`/collected history) but the guard's actual behavior did not match its documented
contract.
**Decision.** `pytest_configure` now sets `DATABASE_URL` to an explicit, unreachable
`OFFLINE_SENTINEL_DATABASE_URL` (`offline.invalid` -- an RFC 2606 hostname guaranteed to fail DNS
resolution in <1s) instead of popping it, so an OS-level value always wins over `.env`'s fallback.
Verified end-to-end (not just the pure-function unit tests that missed this): a new regression
test calls the real `pytest_configure` hook against a clean environment, then builds a real
`Settings()` reading the real `.env` on disk, and asserts it never resolves to Neon --
`test_missing_test_database_url_cannot_fall_back_to_envs_neon_url`. Confirmed the guard also now
correctly REFUSES an explicit attempt to point `TEST_DATABASE_URL` at Neon (tested live this
session: `assert_safe_for_tests` raised `NeonGuardError` as designed).
**Alternatives rejected.** A sentinel on an unbound loopback port -- tried first, rejected: this
machine's environment lets the SYN sit until psycopg's ~15s connect_timeout fires, twice
(`connect_with_wakeup_retry`'s one retry), adding ~32s to every test run that calls
`check_database()`. `.invalid` fails in the DNS-resolution step, before any socket connect,
independent of local network/firewall behavior.
**Date.** 2026-09-28
