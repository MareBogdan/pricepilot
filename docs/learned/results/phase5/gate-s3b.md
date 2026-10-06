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

## Post-guard result

PENDING. The attribute-consistency guard (ADR-0041) was motivated by the error analysis above, so
a post-guard precision computed on these same 28 labels is not an independent estimate; a
fresh-catalogue re-verification would confirm it. The architect computes and records it here.
