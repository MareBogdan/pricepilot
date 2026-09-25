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
- **Open questions carried to the Phase 3 audit, not decided here:**
  - Which model is actually served in production (CE fp32/int8, LoRA ONNX fp32, or hosted), given
    the F1 tie and the serving-benchmark numbers above.
  - K=20 vs. K=100 candidate generation — PROPOSED since addendum #7, still not decided: the
    K-sweep shows blocked recall climbing from 74% (K=20) to 96% (K=100), and item 8's headline
    table now prices the choice (K=20: 210,640 scorings; K=100: 1,053,200; VPS wall-clock per
    served model — CE fp32 4.77h/23.85h, CE int8 3.22h/16.09h, LoRA fp32 149.02h/745.08h).
  - The Phase 7 hosting reserve (~$15 assumed a Hetzner CX22, no longer sold; CX23 is EUR 5.49/mo
    and currently listed as unavailable to order — re-check at Phase 7).

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

## ADR-0030 onward: full text (none yet)
