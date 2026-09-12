# COSTS

Every paid action in this project: date, what, estimated, actual, running total.
Updated in the same commit as the work that spent the money (CLAUDE.md §11).

**Running total: $0.00**
**Budget available: $20.00 · project ceiling: $100.00 · realistic landing point: ~$30–50**

The machine-checkable half of this ledger is `make cost`, which reads the `llm_calls` table.
This file also records spend that never touches an LLM — GPU hours and hosting.

| Date | Phase | What | Estimated | Actual | Running total | Approved |
|---|---|---|---|---|---|---|
| 2026-09-12 | 0 | Foundation: scaffold, schema, mock store, tracking | $0.00 | **$0.00** | $0.00 | n/a |

## Planned spend, per CLAUDE.md §5

| Phase | What | Expected | Approval |
|---|---|---|---|
| 1 | Self-hosted scraping | $0 | — |
| 2 | LLM attribute extraction, cached by title hash | $2–3 | required before first batch |
| 3 | Optional pre-labelling assist | $2–4 | required |
| 3 | GPU rental for LoRA fine-tuning | $15–25 | required, per run |
| 4 | Local PyTorch | $0 | — |
| 5 | Recommendation generation | $5–8 | required |
| 6–7 | Hetzner CX22, ~€4/month | €12–16 | required, once |

## Open note from the audit

`docs/AUDIT.md` concern 5: **$20 available against a $15–25 GPU line is not viable** — one failed
run leaves nothing for the deployed demo. The audit recommends attempting the LoRA run on a free
Colab/Kaggle T4 first and paying for hosting before GPU. No decision taken yet; the table above
still reflects the plan as written in CLAUDE.md.

## Rules

- Announce before spending: `SPEND: <action> — est. $X.XX — proceed?`
- After spending, record actual vs estimated in the table above, in the same commit.
- The hard cap lives in `LLM_BUDGET_USD` and is enforced in `src/pricepilot/llm/client.py`.
  Exceeding it raises `BudgetExceeded`. It never degrades to a cheaper model silently.
