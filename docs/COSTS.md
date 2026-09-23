# COSTS

Every paid action in this project: date, what, estimated, actual, running total.
Updated in the same commit as the work that spent the money (CLAUDE.md §11).

**Running total: $0.00** (verified 2026-09-23: no paid action since the ledger began; Phase 3 annotation, the checker, the scoring-harness build, and this session's cross-encoder baseline run all cost nothing; `llm_calls` untouched)
**Budget available: $20.00 · project ceiling: $100.00 · realistic landing point: ~$30–50**

The machine-checkable half of this ledger is `make cost`, which reads the `llm_calls` table.
This file also records spend that never touches an LLM — GPU hours and hosting.

| Date | Phase | What | Estimated | Actual | Running total | Approved |
|---|---|---|---|---|---|---|
| 2026-09-12 | 0 | Foundation: scaffold, schema, mock store, tracking | $0.00 | **$0.00** | $0.00 | n/a |
| 2026-09-23 | 3 | Item 5 baseline: cross-encoder run (zero-shot + 8-epoch fine-tune) on Kaggle's free-tier hosted notebook, CPU | $0.00 | **$0.00** | $0.00 | n/a — Kaggle's free tier, no paid API/GPU rental used |

## Planned spend — reserved in priority order (CLAUDE.md §5, DECISIONS.md ADR-0011)

Money is reserved by priority, not by phase order. The deliverable is a publicly reachable demo, so
hosting is reserved first; a fine-tuned model on a dead URL is worth nothing.

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
