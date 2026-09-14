# Phase 2 gate sample — read this before labelling `phase2-gate-sample.csv`

Frozen **2026-09-13**, seed **20260913**. This file used to be a comment block at the top of the
CSV itself — moved out because a "#" preamble containing commas is invalid CSV: line 1 had a
comma in it, so Excel, Google Sheets and pandas all read that line as the header and scrambled
every column. The CSV now starts directly with its real header row. Same 100 rows, same order,
same ids, still empty — nothing about the sample itself changed, only where this text lives.

**Do not edit the CSV's rows.** Fill in the attribute columns and the final `ambiguous` column
only, per the seven conventions below. If you're unsure a row's answer follows from these
conventions unambiguously, flag it in `ambiguous` rather than guessing — a hand-check of every
flagged row (plus a random 10 of the rest) is part of the plan.

CLAUDE.md §7's Phase 2 gate: **>=85% attribute accuracy on these 100 listings, with weight
parsing measured separately.**

## The seven conventions (1-5 decided ADR-0026; 6-7 added 2026-09-14, ADR-0027)

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

6. **`"N x W"` and `"N bucati / W"` look alike and mean opposite things.**
   - `"12x85 g"` -> `net_weight_g = 85` (each unit's own weight), `pack_count = 12` (how many
     separately packaged units) — this is convention 1, restated.
   - `"6 bucati / 90 g"` -> `net_weight_g = 90` (the ONE package's total net weight), `pack_count
     = 6` (how many pieces are inside that one package). Verified on the live petmax page for
     listing_id 1597: `"Greutate neta: 6 bucati / 90g"` — 90 g is the bag, not one piece.
   - The number after "x"/"×" is always a per-unit weight multiplied by a pack count; the number
     after "bucati/buc" separated by "/" from a weight is always the whole package's weight, with
     the piece count along for reference only. Do not swap these.
7. **`breed_size_code` describes the ANIMAL the product is for, never the product's own physical
   dimensions.** A harness `"2XL"`, a transport crate `"L"`, a collar or leash `"M 30-51 cm"` /
   `"S, ... Pana la 15 kg"` all leave `breed_size_code` **empty** — that size names the accessory
   itself, not a breed classification. A dental stick labelled `"Medium"` (for medium dogs) DOES
   fill it, because there `"Medium"` genuinely classifies which animals the product is for. If a
   title is for a harness, leash, collar, or transport crate, `breed_size_code` is empty
   regardless of which size word or letter appears in it.

A quantity is mass-based XOR volume-based: fill **at most one** of `net_weight_g` /
`net_volume_ml` per row, never both (ADR-0026's DB-enforced invariant). Leave **both** empty when
the title states no quantity at all — that is a real, expected answer, not a gap.

Leave every attribute column empty until you are labelling for real — if you pre-fill any column,
the gate measures the extractor against itself.
