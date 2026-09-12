---
description: Propose a paid action in the required format
argument-hint: <what you want to spend on>
---

Before spending anything on: $ARGUMENTS

1. Estimate the cost from real unit prices — token prices, GPU hourly rate, VPS monthly rate.
   Show the arithmetic. If you cannot source a unit price, say so and do not guess.
2. State what it buys and what the cheaper or free alternative is (free Colab/Kaggle T4,
   a smaller model, a cached run).
3. Check current spend with `make cost` and against the ceiling in `docs/COSTS.md`.
4. Ask in exactly this format: `SPEND: <action> — est. $X.XX — proceed?`
5. Stop. Do not proceed without a yes.

After the action: record actual vs estimated in `docs/COSTS.md`, in the same commit as the work.
