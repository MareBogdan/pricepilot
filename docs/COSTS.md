# COSTS

Every paid action in this project: date, what, estimated, actual, running total.
Updated in the same commit as the work that spent the money (CLAUDE.md §11).

**Running total: $0.82** (read from `llm_calls`: 575 rows, $0.818442, 2026-09-24)
**Budget available: $20.00 · project ceiling: $100.00 · realistic landing point: ~$30–50**

The machine-checkable half of this ledger is `make cost`, which reads the `llm_calls` table.
This file also records spend that never touches an LLM — GPU hours and hosting.

| Date | Phase | What | Estimated | Actual | Running total | Approved |
|---|---|---|---|---|---|---|
| 2026-09-12 | 0 | Foundation: scaffold, schema, mock store, tracking | $0.00 | **$0.00** | $0.00 | n/a |
| 2026-09-23 | 3 | Item 5 baseline: cross-encoder run (zero-shot + 8-epoch fine-tune) on Kaggle's free-tier hosted notebook, CPU | $0.00 | **$0.00** | $0.00 | n/a — Kaggle's free tier, no paid API/GPU rental used |
| 2026-09-23 | 3 | Item 6 run: LoRA Qwen2.5-0.5B fine-tune on Kaggle's free-tier T4 (smoke + 15.0 min real run) | $0.00 | **$0.00** | $0.00 | n/a — Kaggle free tier, no paid API/GPU rental used |
| 2026-09-23 | 3 | Item 6 prep: prompt template, Kaggle notebook, runbook (no training run yet) | $0.00 | **$0.00** | $0.00 | n/a — nothing executed; the Kaggle run itself will be free tier |
| 2026-09-23 | 3 | Item 8 hosted zero-shot baseline: `claude-sonnet-5`, 287 TEST pairs, `llm-prompt-v1`, max_tokens 5 (194,734 in / 1,139 out tokens; the first paid call in the project) | $0.35 | **$0.40** (`llm_calls` sum $0.400858) | $0.40 | yes — 2026-09-23, cap $5.00 (estimate was 1 token/3 chars, ~17% low) |
| 2026-09-24 | 3 | Item 8 session 2 task 4: ONE diagnostic call (`claude-sonnet-5`, `llm-prompt-v1` on one VALIDATION pair, max_tokens 5) diagnosing the hosted baseline's 40 empty TEST replies — normal reply (`stop_reason=end_turn`, text `"No"`), no request-config defect reproduced | $0.00123 | **$0.001406** (`llm_calls` id 288) | $0.402264 | yes — task instructions authorized this one diagnostic call, cap < $0.01 |
| 2026-09-24 | 3 | Item 8 session 3 task 3: hosted v2 corrective run — `claude-sonnet-5`, 287 TEST pairs, `llm-prompt-v1`, max_tokens 64 (194,734 in / 2,671 out tokens), correcting session 2's wrong "no request-config defect" conclusion (commit eb72250, retracted). Result: only 11/287 unparseable (vs v1's 40) — 40 calls used a `thinking` block, matching v1's exact empty-reply count, confirming the truncation hypothesis | $0.52 | **$0.416178** (`llm_calls`, purpose `hosted-zeroshot-v2-item8`) | $0.818442 | yes — 2026-09-24, explicit "yes" after the SPEND line |
| 2026-09-27 | 4 | Data-sufficiency v2 measurement + storage dedup fix (ADR-0032): read-only SQL only, no LLM calls, no GPU rental, no paid hosting yet | $0.00 | **$0.00** | $0.818442 | n/a — no paid API/GPU/hosting action taken |
| 2026-09-28 | 5 | Session 1: pricing-policy thresholds config + deterministic margin/price guard (ADR-0034). Pure Python + config, no LLM calls, no GPU, no hosting | $0.00 | **$0.00** | $0.818442 | n/a — no paid API/GPU/hosting action taken |
| 2026-09-28 | 5 | Session 2: policy RAG index (migration 0010, `build_policy_index.py`) + `retrieve_policy` + retrieval eval (ADR-0036). Local sentence-transformers embeddings only, no LLM API calls, no GPU rental, no paid hosting | $0.00 | **$0.00** | $0.818442 | n/a — no paid API/GPU/hosting action taken |
| 2026-10-04 | 5 | Session 3: catalogue sync into `products` (migration 0011, `sync_catalogue.py`, ADR-0038). DB writes to the existing free-tier Neon only; no LLM calls, no GPU, no paid hosting | $0.00 | **$0.00** | $0.818442 | n/a — no paid API/GPU/hosting action taken |
| 2026-10-04 | 5 | Session 3b: serve-time matcher on local CPU (torch fp32), migration 0012 `product_matches`, ~7,500 CE pairs scored (ADR-0039). No LLM calls, no GPU rental, no paid hosting | $0.00 | **$0.00** | $0.818442 | n/a — no paid API/GPU/hosting action taken |
| 2026-10-07 | 5 | Session 4: decision engine with a MOCKED LLM, migration 0013 `recommendations`, 7 mock trace rows (ADR-0042). `llm_calls` 575 -> 575 rows, spend unchanged. No LLM calls, no GPU rental, no paid hosting | $0.00 | **$0.00** | $0.818442 | n/a -- no paid API/GPU/hosting action taken |
| 2026-10-07 | 5 | Session 5: the 50 recommendations on `claude-sonnet-5` via `LlmProposer` (30 baseline + 20 hypothetical scenarios, ADR-0042/0044), `max_tokens=400`, 50 `llm_calls` rows | $0.17 (ceiling $0.32) | **$0.240276** | $1.058718 | actual above the estimate: the model emits a thinking block, so output tokens exceeded the ~100 assumed; under the ceiling |
| 2026-10-07 | 5 | Session 5b: re-run 4 truncated baselines + 20 guard stress-tests on `claude-sonnet-5` (`--refresh --max-tokens 1500`, ADR-0045); 24 `llm_calls` rows | $0.11 (ceiling $0.42) | **$0.164186** | $1.222904 | above the estimate again (est. used the s5 mean output of 204 tokens; replies with thinking ran longer); under the ceiling. Superseded s5 rows keep their spend ($0.240276 above) |

## Planned spend — reserved in priority order (CLAUDE.md §5, DECISIONS.md ADR-0011)

Money is reserved by priority, not by phase order. The deliverable is a publicly reachable demo, so
hosting is reserved first; a fine-tuned model on a dead URL is worth nothing.

| Priority | What | Reserve | Approval |
|---|---|---|---|
| **1 — reserved first** | Hetzner CX23, three months | **~$23 (ESTIMATE, ADR-0030)** | required, once, at Phase 7 |
| **2** | Recommendation generation, Phase 5 | **~$2 (ESTIMATE; re-estimated from real token counts at Phase 5)** | required |
| — | LLM attribute extraction, Phase 2 | not used — phase closed at $0 | — |
| — | Optional pre-labelling assist, Phase 3 | not used — phase closed at $0 | — |
| — | GPU rental for LoRA fine-tuning | resolved: Kaggle free tier (Phase 3 items 5-6, 8) | — |

Hosting arithmetic (ESTIMATE): CX23 3 x EUR 5.49 x 1.21 VAT x 1.1411 EUR/USD = ~$22.7 for three
months (2 months ~$15.2); primary IPv4 cost UNVERIFIED and excluded. Available $20.00 - $0.82 =
$19.18, so the shortfall is ~$4-6: a Phase 7 decision for Bogdan (host 2 months, or raise
"available" by ~$5). CX23 availability re-checked at Phase 7.

Phases 0, 1, 3 and 4 cost nothing beyond the ledger above (Phase 3's only spend is the hosted baseline).

### Superseded 2026-09-25 (kept verbatim)

| Priority | What | Reserve | Approval |
|---|---|---|---|
| **1 — reserved first** | Hetzner CX22, three months (~€4/mo) | **~$15** | required, once, at Phase 7 |
| **2** | LLM attribute extraction, Phase 2, cached by title hash | $2–3 | required before first batch |
| **3** | Recommendation generation, Phase 5 | $5–8 | required |
| **4** | Optional pre-labelling assist, Phase 3 | $2–4 | required |
| **not committed** | GPU rental for LoRA fine-tuning | — | **separate decision at week 5** |

Phases 0, 1 and 4 cost nothing and do not appear above.

### GPU fine-tuning is not a committed line

Decided at week 5, on the evidence available then: does the annotated dataset exist, is the
cross-encoder baseline recorded, can a free tier (Colab / Kaggle T4) carry the run. Treating it as
committed now is what made the $20-available arithmetic fail.

**When it is approved, the first run is a smoke run.** Smallest model, ~200 examples, minutes of
wall clock, **~$1–2**, purely to prove the pipeline end to end — dataset loads, LoRA attaches,
training steps, checkpoint saves, eval harness scores it. Its metric is discarded. The real run is a
second, separate `SPEND:` approval. Never the other way round.

## Resolved: audit concern 5

`docs/AUDIT.md` concern 5 flagged that $20 available against a committed $15–25 GPU line leaves
nothing for the deployed demo. **Accepted and applied** on 2026-09-12: hosting reserved first, GPU
decoupled into a week-5 decision with a smoke run in front of it. See ADR-0011.

## Rules

- Announce before spending: `SPEND: <action> — est. $X.XX — proceed?`
- After spending, record actual vs estimated in the table above, in the same commit.
- The hard cap lives in `LLM_BUDGET_USD` and is enforced in `src/pricepilot/llm/client.py`.
  Exceeding it raises `BudgetExceeded`. It never degrades to a cheaper model silently.
