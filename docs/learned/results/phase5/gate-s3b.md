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

## Post-guard result (2026-10-07, computed by `scripts/score_match_labels.py --links match-verification-queue.csv`)

The post-guard worksheet has 25 links. 23 of them match a labelled (link_key, title) pair; 2 are
`newly_surfaced` by the guard (a lower-scoring listing took the slot, `guard-effect.csv`) and have
NO label.

| Metric | Value |
|---|---|
| Links in the post-guard worksheet | 25 |
| Labelled | 23 |
| Precision on the labelled links | **0.9565 (22/23)** |
| Wrong-gramaj false positives | 0% (0/23) |
| Remaining false positive | 19:petmax_ro (generic Mousse vs "cu Pui", which the guard does not try to remove) |
| Unlabelled (newly surfaced) | 18:animax_ro, 22:petmax_ro |
| Precision if both unlabelled are wrong / both right | 22/25 = 0.88 / 24/25 = 0.96 |

**How to read it.** This is a CAVEATED figure, not a gate verdict. (1) The guard was motivated by the
6 errors above, so 22/23 on the same labels is not an independent estimate (ADR-0041). (2) The
interval 0.88-0.96 straddles the 0.90 threshold: the gate is not claimed as met until the 2
unlabelled links are labelled and, ideally, a fresh sample is drawn. (3) The labels are
Claude-written, `claude_pending_bogdan_review`. The "~0.88-0.92" quoted in the session 4/5 briefs
was an ESTIMATE; the script's bounds above replace it.
