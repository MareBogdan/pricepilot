# s3b matcher gate -- measured results (ADR-0038 gate, ADR-0040 wording)

Gate (ADR-0040): **precision >= 0.90 AND wrong-gramaj false positives <= 5%** on the verified
links. Coverage is REPORTED, not gated. Recall is not claimed.

## Baseline: PRE-GUARD (28 links, top-100 candidate cap, ADR-0039) -- kept as the honest record

Source: `match-verification-labels.csv` (all 28 links of `match-verification-queue.csv`, same
`link_key` set, checked by script). Computed from the file: 22 YES / 28.

| Metric | Value |
|---|---|
| Links verified | 28 of 28 |
| Precision | **0.786 (22/28)** |
| Wrong-gramaj false positives | **0% (0/28)** |
| Products with >= 1 link | 14 of 30 (reported) |

The 6 false positives, all semantic (none is a gramaj error):

| Row | link_key | Our product | Competitor listing | Error class |
|---|---|---|---|---|
| 20 | 18:animax_ro | Royal Canin Instinctive Cat 85 g | Royal Canin **Kitten** Instinctive 85 g | life-stage |
| 21 | 18:pentruanimale_ro | Royal Canin Instinctive Cat 85 g | ROYAL CANIN **Kitten** (in aspic) 85 g | life-stage |
| 22 | 19:petmax_ro | Purina Gourmet Gold Mousse 85 g | Gourmet GOLD Mousse **cu Pui** 85 g | flavour (generic vs chicken) |
| 26 | 22:petmax_ro | Calibra Joy Dog Classic **Chicken Strips** 80 g | Calibra Joy Dog Classic **Beef Sticks** 80 g | flavour + form |
| 27 | 25:animax_ro | Advance Cat **Litter** Clumping 10 kg | Advance Cat **Kitten** (food) 10 kg | category |
| 28 | 25:petmax_ro | Advance Cat **Litter** Clumping 10 kg | Advance Cat **Kitten** (food) 10 kg | category |

## Caveats on how the labels were produced

- The labels were written by Claude, blind to the model score (the worksheet has no score column),
  and are marked `claude_pending_bogdan_review`. ADR-0038 specified a human labeller; Bogdan's
  review of the file is still owed. Until then the numbers above are Claude-labelled.
- The candidate set is the top-100 cap, not whole blocks: the ADR-0039 audit found exactly 5
  listings >= 0.89 beyond the cut across 13 products (bounded, documented; ADR-0040).

## Post-guard run (ADR-0041, 2026-10-07) -- facts only, precision NOT computed here

Same matcher, same 0.89 threshold, guard applied after the cross-encoder cut. Re-run twice:
identical output (only timing differs). Source: `match-run.json`, `guard-effect.csv`.

| Item | Value |
|---|---|
| Links | 28 -> **25** |
| Products with >= 1 link (reported) | 14 -> **13** of 30 |
| Per shop | animax_ro 8, pentruanimale_ro 7, petmax_ro 10 |
| Listings >= 0.89 rejected by the guard | 17 |
| Pre-guard FPs removed | **5 of 6** (rows 20, 21, 26, 27, 28) |
| Pre-guard FP surviving | 1 of 6: 19:petmax_ro, generic Mousse vs "cu Pui" (one-sided flavour passes, Rule 5) |
| Newly surfaced links, NOT in the 28 labels | **2**: 18:animax_ro (Instinctive in Gravy, 0.9636), 22:petmax_ro (Chicken Bits, 0.9992) |

The 25 surviving links are NOT a strict subset of the 28 labelled ones: 23 are, 2 are new.
Post-guard precision needs those 2 labelled first.

## Post-guard precision

PENDING. The guard was motivated by the error analysis above, so a post-guard precision computed
on the same labels is not an independent estimate; a fresh-catalogue re-verification would
confirm it. The architect computes and records it here. No pass/fail is declared in this file.
