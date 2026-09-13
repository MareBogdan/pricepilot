# Phase 2 gate sample — read this before labelling `phase2-gate-sample.csv`

Frozen **2026-09-13**, seed **20260913**. This file used to be a comment block at the top of the
CSV itself — moved out because a "#" preamble containing commas is invalid CSV: line 1 had a
comma in it, so Excel, Google Sheets and pandas all read that line as the header and scrambled
every column. The CSV now starts directly with its real header row. Same 100 rows, same order,
same ids, still empty — nothing about the sample itself changed, only where this text lives.

**Do not edit the CSV's rows.** Fill in the attribute columns and the final `ambiguous` column
only, per the five conventions below. If you're unsure a row's answer follows from these
conventions unambiguously, flag it in `ambiguous` rather than guessing — a hand-check of every
flagged row (plus a random 10 of the rest) is part of the plan.

CLAUDE.md §7's Phase 2 gate: **>=85% attribute accuracy on these 100 listings, with weight
parsing measured separately.**

## The five conventions (decided, ADR-0026)

Apply these exactly, so the labeller and the extractor cannot diverge on definitions:

1. **Multipack** `"12x85 g"`: `net_weight_g = 85` (the single unit), `pack_count = 12`. Total mass
   is derived, never the stored net weight — a 12-pouch box and a single pouch are different
   purchasable units, and `pack_count` is what distinguishes them.
2. **Bonus pack** `"12+2 kg"`: `net_weight_g = 12000` (base), `bonus_weight_g = 2000`, recorded
   separately. Reuses `OverlapKey.bonus_g`'s existing semantics exactly — not a second,
   conflicting convention.
3. `"1 x 85 g"`: `pack_count = 1`, `net_weight_g = 85`.
4. **Dosage bands** (`"10-25 kg"`) are the **ANIMAL's** weight, never the product's. These must
   NEVER populate `net_weight_g` — the highest-risk confusion in this field.
5. **`brand` is the manufacturer, lowercased, in its simplest form** — added same-day, before
   labelling started, once it became clear brand form was otherwise undefined and a mismatch
   there would fail the gate on a definition disagreement rather than on a real extraction error:
   - `"brit"` (not `"Brit Premium"`)
   - `"hill's"` (not `"HILL'S Science Plan"`)
   - `"royal canin"`, `"calibra"`
   - The sub-line ("Premium by Nature", "Science Plan", "Life", "Care") belongs in
     `product_line`, never in `brand`. STEP 3's brand canonicalization targets exactly this
     shape — every variant a source writes maps onto it.

A quantity is mass-based XOR volume-based: fill **at most one** of `net_weight_g` /
`net_volume_ml` per row, never both (ADR-0026's DB-enforced invariant). Leave **both** empty when
the title states no quantity at all — that is a real, expected answer, not a gap.

Leave every attribute column empty until you are labelling for real — if you pre-fill any column,
the gate measures the extractor against itself.
