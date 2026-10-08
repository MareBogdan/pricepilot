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

**Context.** The guard needs the policy's numbers without parsing `docs/policy/pricing-policy.md`
at runtime (CLAUDE.md section 6, rule 2: guardrails live in code, not prompts).
**Decision.** `config/pricing-policy.toml` is the single structured source, loaded and validated by
`policy/thresholds.py` (Pydantic v2). `policy/guard.py::enforce` is the one entry point: no-change
short-circuit -> charm round (floor-safe) -> floor re-check -> discount eligibility -> speed limit,
APPROVE / REJECT / FLAG, all `Decimal`. Unknown category or non-positive money raises (fail closed);
a speed breach or missing 7-day reference is FLAG (policy section 4: human approval), never a silent
pass. The LLM only proposes; this guard decides. **Review fixes (2026-09-28):** checks run on the
ROUNDED price (rounding had slipped past eligibility/speed); a genuine no-change is approved
unrounded (rounding manufactured a 179.00 -> 178.90 discount). **Later:** ADR-0043 keeps the move's
direction through rounding. **Out of scope** (no mock-store field): MAP brands, new-product age,
manual lock, promotion/competitor-hold rules. **Rejected:** inline threshold literals; enforcing the
margin in the prompt. **Full text (with addenda):** `docs/archive/DECISIONS-ADR-0034-0036-full.md`.
**Date.** 2026-09-28

## ADR-0036 — RAG over the pricing policy: section chunks, shared model, numbers stay out

**Context.** The decision engine needs relevant policy prose without sending the whole document;
CLAUDE.md section 6 rule 1: RAG is only for policy TEXT, every number stays in SQL / the TOML.
**Decision.** `policy_chunks` (migration 0010), one row per numbered policy section, embedded with
the SAME local model as `norm_listings` (`paraphrase-multilingual-MiniLM-L12-v2`, 384-dim) via
`pricepilot.embeddings`; `retrieve_policy()` ranks by pgvector cosine and returns text only. Eval (20
pre-registered questions): hit@1 0.850, hit@3 0.950, MRR 0.912, one miss not chased (tuning to the
eval is what pre-registration prevents); the eval CSV commit landed after an exploratory run,
disclosed in its commit. **Rejected:** sentence/window chunking, a second embedding model (silent
query/index mismatch), storing thresholds in `policy_chunks`. **Full text:**
`docs/archive/DECISIONS-ADR-0034-0036-full.md`. **Date.** 2026-09-28

## ADR-0037 — ADR-0014's Neon test guard had a hole: popping DATABASE_URL doesn't isolate .env

**Context.** `reviewer` (576ea77): `pytest_configure` popped `DATABASE_URL` when `TEST_DATABASE_URL`
was absent, but `Settings(env_file=".env")` then fell back to `.env`'s real Neon credential, so plain
`pytest` runs hit Neon (only idempotent `policy_chunks` upserts; no data lost).
**Decision.** Set `DATABASE_URL` to an unreachable sentinel (`offline.invalid`, fails DNS in <1s)
instead of popping it, so an OS value always beats `.env`; end-to-end regression test added; the guard
also refuses a `TEST_DATABASE_URL` that names Neon. **Rejected:** a loopback-port sentinel (+32s per
run), reading `TEST_DATABASE_URL` from `.env` (+60s when docker is down; accepted coverage gap).
**Full text:** `docs/archive/DECISIONS-ADR-0037-full.md`. **Date.** 2026-09-28

## ADR-0038 — Sync our catalogue first; the matcher is its own session; pg8000 fallback; s3b gate pre-registered

**Context.** Architect audit 2026-10-04: the Phase 5 decision-engine session could not run as
written. Verified read-only against the live DB: `products` had 0 rows (our catalogue was never
synced from the mock store), no `product_matches`/decision tables exist (migrations 0001-0010
create none), and no serve-time matcher exists in `src/` -- Phase 3 closed the model choice
(ADR-0030) but never productionised it. Separately, psycopg's libpq DLL is blocked by Application
Control on this machine again (it had looked transient).
**Decision.** (1) Phase 5 is re-sequenced: s3 sync `products` (this session: migration 0011 adds
nullable `net_weight_g`; `scripts/sync_catalogue.py` idempotent upsert on `id`, Decimal money;
verified 30 rows, 0 duplicate SKUs, stable across two runs); s3b serve-time matcher ->
`product_matches`; s4 decision engine with a mocked LLM, $0; s5 the 50 real recommendations
(SPEND ~$2). (2) `pg8000` is a supported opt-in fallback: `PRICEPILOT_DB_DRIVER=pg8000` swaps the
driver and translates `sslmode`/`connect_timeout` (`db.py::resolve_database_target`, shared by the
app engine and `alembic/env.py`); `.env` is never edited; default behaviour is unchanged.
**Alternatives rejected.** Stuffing the sync into the matcher session (couples a trivial,
verifiable data load to the risky model work); a runtime-fetch of the catalogue over HTTP (needs a
running server for a deterministic fixture); editing `.env` to a pg8000 URL (breaks every
psycopg-working environment, incl. the VPS).

**Pre-registered s3b matcher gate (written before s3b produces any number).**
- *Matcher spec (ADR-0030):* our 30 products x `norm_listings`, K=100 embedding candidates,
  cross-encoder ONNX fp32, threshold 0.89, at most one match per (our product, competitor shop),
  highest score wins; result persisted in `product_matches` with the score.
- *"Correct match" =* the pair is the same purchasable unit under the current revision of
  `docs/learned/phase3-annotation-conventions.md` (same brand, product line, species/life stage,
  flavour, and net weight/pack quantity -- same line at a different gramaj is NOT a match).
- *Verification:* if the matcher returns <= 120 links, verify ALL; otherwise a random sample of 120
  with seed 20261004. A human (Bogdan) labels each link YES/NO from title, brand, weight and
  price, **blind to the score**; labels are committed to `docs/learned/` BEFORE the precision
  number is computed.
- *Gate (all must hold):* precision >= 0.90 on the verified links; at least 15 of our 30
  products have >= 1 correct match; wrong-gramaj false positives <= 5% of verified links.
  Recall is NOT claimed (no full ground truth) -- only coverage is reported, labelled as such.
- *If it fails:* report the number as-is. The threshold is NOT retuned on the verified sample; any
  threshold/model change needs a new ADR and a fresh sample.
**Date.** 2026-10-04

## ADR-0039 — Served matcher: torch/safetensors on CPU (not ONNX), `product_matches` grain, block-and-score

**Context.** `models/ce-ft-best.zip` is HuggingFace format, not ONNX; `norm_listings.content_hash` is
title-only and shared across shops, so shop and price come from `raw_listings`.
**Decision.** Serve the fp32 torch weights on CPU (ONNX is a Phase-7 latency concern). A faithfulness
gate must reproduce the committed PyTorch-fp32 predictions (tolerance 1e-3, zero flips at 0.89) before
anything is scored; the first attempt failed (tokenizer `</s></s>` vs `</s>` under transformers 5.x)
and was fixed by tokenising with `tokenizer.json` (max diff 1.8e-6). `product_matches` = one row per
(our product, shop), `UNIQUE(product_id, source)`, `CHECK score >= threshold`; blocks <= 300 scored in
full, larger blocks cut to the top-100 by cosine. **Result:** 28 links on 14 of 30 products; 5 listings
>= 0.89 lost beyond the cut (accepted, ADR-0040). **Rejected:** ONNX export now, `AutoTokenizer`,
symmetrising. **Full text:** `docs/archive/DECISIONS-ADR-0039-0042-full.md`. **Date.** 2026-10-04

## ADR-0040 -- Coverage is a reported metric, not a gate; the top-100 candidate cap is accepted

**Context.** ADR-0038 gated s3b on ">= 15 of 30 products with a correct match" alongside precision
and wrong-gramaj false positives. ADR-0039 measured 14 of 30 products with any link, which made
the coverage criterion arithmetically unreachable. Blind labelling of the 28 links (2026-10-07,
`docs/learned/results/phase5/gate-s3b.md`): precision 0.786 (22/28), wrong-gramaj 0% (0/28).
**Decision.** (1) Coverage moves from a GATE to a REPORTED metric. This is a correction to
ADR-0038's design on principle, and it would hold at any measured number (14, 20 or 30): coverage
is market overlap -- whether our product is sold at petmax / animax / pentruanimale at all --
not matcher quality, and a product a shop does not stock cannot be matched. It is not a response
to missing 15. The matcher-quality gate is **precision >= 0.90 AND wrong-gramaj false positives
<= 5%** on the blind-labelled links; both thresholds and the blind-labelling protocol are
unchanged from ADR-0038. Recall is still not claimed. (2) The top-100 candidate cap (ADR-0039,
blocks > 300) is ACCEPTED. The `--audit-truncation` diagnostic quantified the loss exactly: 5
listings >= 0.89 beyond the cut across 13 products -- a bounded, documented limitation. Scoring
whole blocks costs ~15 min of CPU on the dev laptop (and an attempt to do so lost its database
connection to an idle timeout), so it is not worth it here; revisit on GitHub Actions after
deployment if the 5 ever matter.
**Alternatives rejected.** Keeping the coverage gate and adding sources until 15 products match
(treats a market fact as a model defect); lowering the precision threshold after seeing 0.786
(threshold changes need a new ADR and a fresh sample, ADR-0038); scoring whole blocks now.
**Honesty note.** The labels were written by Claude, blind to the score, and are marked
`claude_pending_bogdan_review`; ADR-0038 specified a human labeller, whose review is still owed.
**Date.** 2026-10-07

## ADR-0041 -- Deterministic attribute-consistency guard on cross-encoder matches

**Context.** The 6 false positives in the blind labels are all semantic, none a gramaj error: a
litter bag matched to kitten food (2 links), an adult-cat wet food matched to a Kitten SKU (2),
Chicken Strips matched to Beef Sticks (1), a generic Mousse matched to a chicken one (1). A wrong
match feeds a wrong competitor price into the s4 decision engine, so the rule CLAUDE.md §6.2
applies to the margin ("guardrails live in code, not in the model") applies to matching too.
Inspection of both sides of the 28 links (2026-10-07) found: `norm_listings.life_stage` is NULL on
every Kitten listing, because `normalize.attributes._LIFE_STAGE` has no "kitten"; our `products`
rows carry a 6-value mock category, `norm_listings.category` carries food / accessory / litter /
toy; our products carry no extracted `species`.
**Decision.** `src/pricepilot/matching/consistency.py::conflicts` runs in Python after the
cross-encoder's >= 0.89 cut and before the one-per-(product, shop) selection and persistence. It
rejects only conflicts `docs/learned/phase3-annotation-conventions.md` calls unambiguous, and never
rejects on missing information. (1) **Category** (Rule 0 + Scope): dry_food / wet_food / treats ->
food; litter -> litter; grooming -> accessory; accessories -> accessory or toy; a competitor
category outside that set rejects, an unknown competitor category passes. (2) **Life stage** (Rule
3, formula-defining): both sides stated and different -> reject; one side stated, not plain
"adult", the other silent -> reject, since Kitten / Puppy / Junior / Senior / an "Adult 7+" band
each name a distinct SKU; plain "adult" against silence passes (the unmarked default; narrower than
Rule 3 on purpose -- a missed match costs a link, a wrong match costs a price). The stage is read
from the title as well as the extracted column, because the extractor has no "kitten"; the frozen
extraction layer is untouched. (3) **Flavour** (Rule 5): both sides state a flavour and they
differ -> reject; a flavour on one side only is the annotator's "skip", so it passes.
Rejected pairs are removed BEFORE the best-per-shop selection, so a lower-scoring consistent
listing >= 0.89 may take the slot; any such newly surfaced link is reported as unlabelled
(`guard-effect.csv`).
**Not fitted to the 6 rows.** Each rule restates a convention, with computed unit tests that do not
use the known-bad titles. One of the 6 (generic Mousse vs "cu Pui") is NOT removable by a rule that
never rejects on one-sided flavour, and the guard does not try. The guard was nonetheless
motivated by this error analysis, so a post-guard precision computed on the same 28 labels is not
an independent estimate; a fresh-catalogue re-verification would confirm it.
**Alternatives rejected.** Raising the 0.89 threshold (ADR-0038 forbids tuning on the verified
sample); rejecting one-sided flavour (contradicts Rule 5); editing the extractor to emit "kitten"
(re-extraction of a frozen Phase 2/3 layer for a serving-time need); an LLM check (money, and a
prompt is not a guardrail); matching on species (our products carry none).
**Date.** 2026-10-07

## ADR-0042 -- Decision engine: the proposer seam, the trace table, and how session 5 reaches 50

**Context.** The gate (50 recommendations, zero margin violations) must come from the real LLM in s5,
so the s4 engine could not be coupled to a mock.
**Decision.** `decision/engine.py`: gather (SQL) -> RAG -> prompt -> an injected proposer -> strict
`parse_reply` -> `guard.enforce` -> trace (`recommendations`, migration 0013, `is_mock` separates $0 mock
rows). `MockProposer` (s4) and `LlmProposer` (wraps `client.complete`) share the prompt and parser;
an unparseable reply FLAGs with no price; limits shown to the model come from the TOML, retrieved text is
reference-only; elasticity is a value-less placeholder; a prose/TOML drift test guards the policy.
**s5 scheme:** 30 baseline + 20 scenario rows (13 `undercut_15` + 7 `undercut_30`), later re-framed as
guard stress-tests (ADR-0045). **Review fixes:** a guard `ValueError` becomes a FLAG row (no lost trace),
exact-shape CRLF-safe parser, flattened competitor titles. **Rejected:** per-collection-day rows.
**Full text:** `docs/archive/DECISIONS-ADR-0039-0042-full.md`. **Date.** 2026-10-07

## ADR-0043 -- The guard keeps the move's direction (charm rounding may not reverse it)

**Context.** ADR-0042 found that `charm_round` rounds to the NEAREST charm value, so on cheap items
the applied price can land on the wrong side of `current_price`: product 18, current 5.20, proposed
5.36 (+3%), applied 4.99 (-4%). No margin rule broke, but the applied move contradicted the
rationale -- and the same flaw existed at any price (179.00 + 179.05 -> 178.90).
**Decision.** After the nearest charm value is chosen, `enforce` re-anchors it on the intended side
of `current_price` (new `charm_ceil` / `charm_floor`, the regime boundary 99.99 -> 100.90 included).
Intended INCREASE and result below current: use the smallest charm value >= current (floor-safe as is:
it is above the floor-safe nearest value). Intended DECREASE and result above current: use the largest charm value <= current if it
clears the floor, otherwise FLAG ("direction cannot be kept") -- never an upward APPROVE. A genuine
no-change is untouched. Every later check (floor, eligibility, speed) runs on the re-anchored price,
so e.g. the 5.20 case is now a speed-limit FLAG (5.99 is +15%), not a silent -4% cut.
**Two existing tests changed, deliberately:** (1) the 2026-09-28 "rounding-induced discount on zero
stock" regression (179.05 on stock 0 -> REJECT) is rewritten: the invariant it protected -- rounding
cannot induce a discount -- now holds by construction (result APPROVE 179.90, a rise); (2) the
"badly low proposal" test (cut of 95 -> floor-lifted 100.90) still FLAGs but now for "direction
cannot be kept" instead of the speed limit. All other guard tests are unchanged and green. New: unit
tests for the helpers, the product-18 case, up/down re-anchoring, the sub-floor-current case, and a
grid sweep (2 categories x 10 prices x 24 proposals) asserting every APPROVE is on the intended side
of current and clears its floor.
**Alternatives rejected.** Rounding in the proposal's direction always (floor/ceil of the proposal):
an increase could then be floor-ed below current just the same. Declining to round small items:
policy section 6 rounds everything. Treating a direction flip as REJECT: policy section 4 sends
ambiguous moves to a human, i.e. FLAG.
**Review (reviewer, same day): no blocking finding.** 400k random `enforce` calls: no APPROVE below
a floor, none against the intended direction, none cutting on stock < 3, none over the speed cap. The
increase-branch step-up loop was unreachable and is removed (the step-2 floor re-check stays as the
backstop); the sweep now covers stock 0 and 50 and asserts the daily cap; the product-18 style
floor-lift-then-speed case has its own test. **Known and accepted:** when `current_price` is itself a
charm value and a far-below-floor cut is floor-lifted back to exactly `current`, the guard APPROVEs
the unchanged price (a no-op, policy section 7), whereas the same cut from a non-charm current
FLAGs "direction cannot be kept"; both leave the price where it was.
**Date.** 2026-10-07

## ADR-0044 -- Phase 5 gate run: result, and a truncation fault found in the harness

**Context.** Session 5 ran the 50 recommendations (ADR-0042 scheme) on `claude-sonnet-5` via `LlmProposer`
(`max_tokens=400`); gate: 50 recommendations, zero margin violations.
**Result.** 50 rows, **0 margin violations** among 45 APPROVEs (re-checked from stored cost / price /
category against the TOML, independent of the guard); spend $0.240276 (est. $0.1724). Weak evidence for the
floor: 42 of 45 APPROVEs kept the price, and the 20 scenario rows were ignored because the prompt called
them hypothetical (corrected in ADR-0045). The floor is shown by the guard's tests and sweeps.
**Fault found.** Sonnet 5 thinks by default; at `max_tokens=400` four replies were cut off (3 unparseable
FLAGs, 1 mid-sentence reply APPROVEd at the unchanged price). **Decision.** Record `stop_reason`
(`recommendations.llm_stop_reason`, migration 0014); a `max_tokens` reply is FLAGged whatever it parses to;
rows backfilled from the response cache ($0), not re-run or edited. Charm rounding can breach the daily cap
(2 FLAGs): see ADR-0046. Matcher precision recorded honestly in `gate-s3b.md`.
**Alternatives rejected.** Silently re-running the 4 items; editing stored verdicts; dropping truncated rows.
**Full text:** `docs/archive/DECISIONS-ADR-0044-full.md`. **Date.** 2026-10-07

## ADR-0045 -- Make the Phase 5 gate meaningful: scenarios become guard stress-tests

**Context.** ADR-0044 found the 50-row gate weak: 42 of 45 APPROVEs were no-change; all 20 scenario
rows self-neutralised because my prompt announced the competitor prices as hypothetical (20 of 20
rationales cite it); 17 baseline rows had no competitor data; 4 replies were cut off at
`max_tokens=400`. Bogdan authorised an explicit adversarial re-run.
**Decision.** (1) The 20 scenario rows are re-framed as GUARD STRESS-TESTS (scenario names
`stress_undercut_15` / `stress_undercut_30`): the competitor prices (observed x 0.85 / x 0.70) are
presented in the prompt as ordinary pricing input, and the model is not told they are synthetic. The
deception is of the model under test only, and is disclosed wherever a human reads the result: the
row's `scenario` starts with `stress_`, the competitor JSON keeps `observed_price`, the report labels
the rows "GUARD STRESS-TEST -- synthetic competitor prices, not a market recommendation". (2) The 4
truncated baselines (p4, p5, p14, p20) and the 20 stress rows were re-run with `max_tokens=1500`
(`run_recommendations.py --refresh`); old rows are relabelled `s5-superseded` in the same transaction
as each new insert (nothing deleted; the old s5 spend stays in `llm_calls` and COSTS). (3) The report
gains a `MoveSummary` table: per group, the model's proposals BEFORE the guard (moves, over the daily
cap, below the floor) and what the guard let through.
**Result (refreshed 50, `scripts/report_recommendations.py`).** 50 rows, **0 margin violations**, 0
direction contradictions, 0 truncated replies; **38 APPROVE / 0 REJECT / 12 FLAG**. The model proposed
a move on 22 rows (14 of 20 stress-tests, 8 of 13 matched baselines); **10 APPROVEs move the price**
(6 stress-test, 4 matched baseline), 28 keep it (17 of those had no competitor data). The 12 FLAGs
are ALL one cause: the model proposed exactly the daily-cap move (-5%), charm rounding to the nearest
charm value overshot the cap, and the guard FLAGged. Refresh run cost **$0.164186** (est. $0.1073,
ceiling $0.4183); the stress rationales no longer cite "hypothetical" (0 of 20).
**What this does and does not show.** Zero model proposals were over the daily cap and zero were below
a floor: a live model that is told the limits obeys them, and the 5% cap keeps one step far from
every floor here (margins 28-56% vs floors 12-30%). So the margin floor was never the binding
constraint in live data; the guard's real live work was the rounding-over-cap FLAGs. The floor's
protection is shown by the guard's unit tests, the 400k-call reviewer sweep and the catalogue x
strategy sweep with a deliberately below-floor mock proposer -- not by these 50 rows. Gate as written
(50 recommendations, zero margin violations): MET, with this stated plainly.
**Defect surfaced, not fixed here.** Charm rounding can push an in-cap move over the cap; it turned
12 of 22 proposed moves into FLAGs: 11 are -5% cuts that nearest-charm rounding overshot, and 1 (p18,
`stress_undercut_15`) is a +5% rise (5.20 -> 5.46) that the ADR-0043 direction rule rounded UP to 5.99,
+15.2%, because the in-cap nearest value (4.99) is on the wrong side. Below ~20 RON the 1-RON charm step
is bigger than the 5% cap, so many moves cannot be expressed either way; a within-cap rule must handle
both directions (a guard change, ADR-0034/0043, for Bogdan to decide). **Review also found** that 3 of
the 20 stress rationales (p-rows 62/65/78 in the report) decline to react for reasons other than the
label (a single observation; a doubtful match), that 7 of 13 matched products carry a real competitor
price below our own cost, and that the earlier 'every FLAG is a cut' wording was wrong for p18.
**Alternatives rejected.** Telling the model the prices are hypothetical again (it ignores them);
forcing a below-floor proposal by instructing the model to ignore the limits (tests the prompt, not
the guard -- the mock-proposer sweep already does the adversarial version without spend).
**Date.** 2026-10-07

## ADR-0046 -- Charm rounding vs the daily cap: accepted as conservatism, not changed (Phase 6 brief)

**Context.** ADR-0045 left a decision owed: nearest-charm rounding turned 12 of 22 cap-obeying
proposals into FLAGs. Measured from the 12 FLAG rows (`recommendations`, `s5-real`): **3 are items under
20 RON** (p18 5.20 -> 5.99, +15.2%; p21 11.00 -> 9.99, -9.2%, twice) where the 1-RON charm step alone
exceeds the 5% cap; **9 are items of 134-879 RON** (p3, p4, p7, p14, some twice) where the nearest `.90`
price lands 0.02-0.30 percentage points outside the cap.
**Decision (Bogdan, Phase 6 brief).** The guard is NOT changed. A FLAG here is accepted as intended
conservatism: a move the policy cap would not allow is sent to a human, and Phase 6 routes every FLAG
to `flag_for_review` (log, apply nothing). An absolute-RON cap (or a within-cap rounding rule) is
documented FUTURE work, not done.
**Honest note.** The brief's rationale (a 1-RON step on a 5-RON item) covers 3 of the 12. The other 9
are tiny overshoots on expensive items; accepting them costs a human review of a <=0.30 pp overshoot
each. A within-cap rule (round toward current to the nearest charm value inside the cap, else FLAG)
would turn most of those 9 into APPROVEs and is the natural first step of the future work. It
cannot create a margin violation either way.
**Alternatives rejected.** Changing the guard now (instruction; and the gate is already met).
**Date.** 2026-10-07

## ADR-0047 -- Phase 6 action layer: guard-selected tools, human approval, idempotent, reversible

**Context.** Phase 6 turns a guard-decided recommendation into an action on the mock store with a
durable log and rollback; gate = one complete cycle, visible in logs.
**Decision.** The guard verdict selects the tool in code (APPROVE with a move -> `update_price`; APPROVE at
the current price, REJECT -> `do_nothing`; FLAG -> `flag_for_review`), never an LLM. `apply` refuses mock,
superseded and scenario rows, is idempotent (partial unique index: one live `update_price` per
recommendation), refuses a stale recommendation, and needs an explicit human `approve`. Rollback claims the
original with a compare-and-set first and refuses if the store drifted. Every action is a row in `action_log`.
**Limits.** The store is in-memory (a restart resets it); `products.current_price` is not synced after an
apply; check-then-write, not compare-and-set, against the store. 31 tests, 8 of 8 safety mutants killed. $0.
**Alternatives rejected.** LLM-selected tool calls; auto-apply; applying without the stale check.
**Full text:** `docs/archive/DECISIONS-ADR-0047-full.md`. **Date.** 2026-10-07

## ADR-0048 -- CI red since 2026-10-05: frozen-queue hash was taken on a CRLF checkout

**Context.** `main` was red from ~2026-10-05. The failing step was `pytest` (lint, mypy and the Docker job
were green): `test_annotation_split.py::test_frozen_queue_hash_unchanged` and
`test_predict_label_parity.py::..._real_frozen_queue` hashed the raw bytes of the frozen annotation queue
against `696e9833...`, a hash taken on the Windows CRLF working copy. `.gitattributes` stores the file as
LF, so Linux CI hashes `7da125e1...` and can never match.
**Decision.** Hash the LF-normalised bytes and pin the LF hash `7da125e1...` (the convention
`test_labels_frozen.py` and `check_label_rule_consistency.py` already used). The file is untouched; the old
hash stays as `FROZEN_QUEUE_SHA256_RAW_CRLF` for the derived lookup file that recorded it. No test deleted
or weakened: any content edit still fails. CI run 37639406362 green (check and docker).
**Known leftover.** `scripts/ingest_labels.py` and `scripts/split_annotation_queue.py` still compare the raw
hash and would raise a false tamper alarm on a fresh Linux/VPS checkout. Phase 3 one-shots whose exports
record the CRLF hash, so left alone; fix only if they are ever re-run off Windows.
**Alternatives rejected.** Marking the file `-text` in `.gitattributes` (rewrites a frozen file's stored
bytes); skipping the tests on CI.
**Date.** 2026-10-07

## ADR-0049 -- Phase 7a dashboard: read-only JSON API plus server-rendered pages

**Context.** Phase 7 gate wants a public dashboard; Bogdan reviews it locally before any deploy (7b).
**Decision.** `src/pricepilot/api/`: JSON under `/api` (products, product detail, history, status) and Jinja2
pages (`/`, `/products/{id}`, `/status`) in one FastAPI app, GET only. Numbers come from SQL (`queries.py`)
or `config/pricing-policy.toml`; money is `Decimal`. The only static facts (matcher precision, phase list,
real-vs-simulated table) live in `facts.py` and a test checks the precision figures against `gate-s3b.md`.
Product detail shows the newest REAL (`is_mock = FALSE`), unperturbed (`scenario IS NULL`) recommendation;
stress-test rows are listed separately and labelled simulated. Price history = our price from the mock
store, labelled SYNTHETIC, plus the matched competitors' scraped prices, labelled REAL. Database down ->
`/api/*` and product pages return 503; `/api/status` and `/status` degrade to the static facts. One chart
library (Chart.js from jsDelivr); dark mode via CSS variables; no write actions (apply stays a CLI).
**Alternatives rejected.** A Next.js frontend (more moving parts, not the point of the project); reading
the mock store over HTTP (the in-process accessor the decision engine uses needs no second server).
**Date.** 2026-10-07

## ADR-0050 -- The Phase 1 gate's "18,585 listings" was price ROWS, not distinct listings

**Context.** The 7a dashboard showed 11,097 distinct listings; the Phase 1 gate (CLAUDE.md, ADR-0025) says
18,585. Re-derived from `raw_listings`: through the first two collection days (2026-09-12/13) there are
18,703 rows stored, **18,585 rows in scope**, and 10,525 distinct (source, listing id). Today: 266,200 in-scope
rows and 11,097 distinct listings.
**Decision.** The gate figure is a count of price rows (listing x day) after two days, not a count of distinct
listings. No reported figure changes and the gate (>= 3,000) holds under either unit (10,525 distinct). The
status page now shows both units for both windows, from SQL, with one paragraph saying so; the dashboard's
own "listings" label says "distinct (source + id)". The `18,585` quote is a constant in `facts.py`, tested
against CLAUDE.md.
**Alternatives rejected.** Editing the Phase 1 text (history stays as written); showing only one unit.
**Date.** 2026-10-07

## ADR-0051 -- Deploy architecture: Hugging Face Space live, lean serving image, VPS documented only

**Context.** Phase 7 needs a public URL. Bogdan decided (2026-10-07) on Hugging Face Spaces (free) now, with the
Hetzner VPS steps written down but not run (supersedes the "Hetzner first" plan of ADR-0030 for the demo; the
served-matcher decision in ADR-0030 is unchanged). The dashboard is read-only and needs no ML at request time.
**Decision.** (1) The root `Dockerfile` is a lean serving image: core dependencies only (`pyproject`
`[project.dependencies]`; ML, scrapers, migrations, LLM client moved to a `pipeline` extra that `dev` includes, so
CI and local `uv sync --extra dev` are unchanged), 324 MB, no model, copies `src/`, `services/`, `config/` and the
three result JSONs the dashboard reads, listens on 0.0.0.0:7860 as uid 1000. (2) `SUPERSEDED_RUN_LABEL` moved to
`decision/run_labels.py` so the API no longer imports the decision engine; `tests/test_serving_image.py` fails if
the API imports torch & co., if core deps regain them, or if the image drops a file the dashboard reads. (3) The
Space is fed by `scripts/make_space_bundle.ps1`: a fresh 0.47 MB, 73-file, one-commit repo (no history, no model,
size-checked), force-pushed by Bogdan. (4) The Space gets a read-only Neon role as a `DATABASE_URL` secret.
(5) `docs/DEPLOYMENT.md` Part A = the live steps; Part B = the VPS walk-through, marked not executed.
**Alternatives rejected.** Pushing the whole repo to the Space (history, labels and archive published for no
reason); a second `Dockerfile.space` (HF only builds the root `Dockerfile`, two files would drift); keeping the ML
stack in the image (1+ GB, slow cold start, unused). **Cost.** $0.
**Date.** 2026-10-08

## ADR-0052 -- Retarget the live deploy from Hugging Face Spaces to Render (free)

**Context.** Hugging Face made Docker-SDK Spaces paid (2026-10, as reported by the architect/Bogdan; not independently checked). The dashboard is FastAPI + Jinja +
Chart.js, not Gradio, so a Space would need a rewrite or money. ADR-0051's lean image is host-neutral.
**Decision.** Deploy the same lean image to a Render free web service. `Dockerfile` `CMD` is shell form and
listens on `${PORT:-7860}` (Render injects `PORT`); `render.yaml` declares one free Docker web service, health
check `/health`, `autoDeploy: false` (manual deploys only, CLAUDE.md rule 6), and `DATABASE_URL` with `sync: false` (the Neon read-only URL is entered in the
Render dashboard, never in git). `docs/DEPLOYMENT.md` Part A is now Render (Koyeb as the no-card backup); Part B
(VPS) unchanged. `make_space_bundle.ps1` and the README HF front-matter stay as marked legacy. Free-tier cost:
spins down after ~15 min idle, ~1 min cold start (stated in the README).
**Alternatives rejected.** Rewriting as Gradio/static (throwaway work); paying for an HF Space; the VPS now
(money, ops time, ADR-0030 shortfall). **Cost.** $0. Supersedes the HF part of ADR-0051 only.
**Date.** 2026-10-08
