# Q3 verification extension — 2026-09-15 (ADR-0028 TASK 3)

Extends `docs/learned/q3-verification.md` (2026-09-13, 50 draws, seed `20260913`) using the SAME
method, a new random draw, a new seed. Purpose: shrink the Wilson CI on the `q3_browser_verified`
subset of `docs/learned/phase3-retrieval-eval-set.csv`, which recall@20 treats as the headline
number.

**Method.** Population: petmax_ro, `category='food'`, keyable (net_weight_g or net_volume_ml
stated), in-scope — 2,353 distinct listings at draw time (`docs/learned/phase3-q3-extension-
draw.json`, not committed — a scratch draw file, superseded by this document and by the 5 rows
appended to `phase3-retrieval-eval-set.csv`). Random sample of 150 drawn with seed `20260915`,
excluding all 50 titles already checked in `q3-verification.md`. **40 of the 150 were verified
this session** via the `claude-in-chrome` browser tool against `pentruanimale.ro`'s own search
(a VTEX storefront — `https://www.pentruanimale.ro/{query}?_q={query}&map=ft`), reading each
result's structured attributes (species, weight/variant list) rather than title text alone, same
standard as the original Q3 hand-check.

**Result: 5 of 40 (12.5%) confirmed genuine matches** — notably lower than Q3's 54%. Two honest
candidate explanations, not resolved here: (a) genuine sample variation at this n, or (b) this
session's query text (`brand + product_line`, sometimes carrying extra flavour/variant tokens)
is a weaker search query than Q3's manual "brand root + weight" approach, under-finding real
matches that a better-phrased search would surface — which would mean the true rate is higher than
12.5% and this count is a floor, not an estimate. **Only CONFIRMED matches are used as known
positives; the 35 "not found" rows are not claimed as verified true negatives** — same discipline
`q3-verification.md` uses.

**This falls short of the "≥100 browser-verified pairs" target.** At the observed 12.5% hit rate,
reaching 100 confirmed matches from this population would need on the order of 800 draws — not
achievable in one session at the verification cost this site's search requires (typically 2-6
browser tool calls per item: search, and for any plausible candidate a follow-up product-page visit
to confirm the actual weight, since the search result list only shows weight for multi-variant
products). Reported honestly rather than continuing past a reasonable session budget and reporting
a padded number. Recommendation for a future session: either extend this exact draw with more
items (the population and exclusion list make that mechanical), or invest first in a better query
strategy (closer to Q3's manual "brand root + weight" phrasing) to raise the hit rate before
spending more browser calls.

**The 5 confirmed matches are appended to `phase3-retrieval-eval-set.csv`**
(`eval_source=q3_browser_verified`, `verification=human_browser_verified_2026-09-15`) and are
included in `measure_recall_at_20.py`'s headline subset, growing it from n=26 to n=31.

## Table 1 — confirmed genuine matches (5)

| petmax_title | petmax_weight | pentruanimale product | pa_weight_confirmed |
|---|---:|---|---:|
| Royal Canin Giant Junior 15 Kg | 15000 | ROYAL CANIN Giant Junior, hrană uscată câini junior, etapa 2 de creștere | 15000 (h1 name + price/kg cross-check: 303.44/15=20.23 lei/kg) |
| Matisse hrana uscata pentru pisici sterilizate cu somon 10 kg | 10000 | MATISSE Neutered, Somon, hrană uscată pisici sterilizate | 10000 |
| Royal Canin Mother & Babycat, 4 kg | 4000 | ROYAL CANIN Mother & BabyCat, hrană uscată pisici, mama și puiul (variant list: 2kg/4kg/10kg) | 4000 |
| Matisse hrana uscata pentru pisici cu pui si orez 10 kg | 10000 | MATISSE, Pui și Orez, hrană uscată pisici | 10000 |
| Applaws, conservă hrană umedă pisici cu ton si branza, (în supă), 156g | 156 | APPLAWS File, Ton și Brânză, conservă hrană umedă pisici, (în supă) | 156 |

## Table 2 — checked, no confirmed match (35)

| # | petmax_title | petmax_weight | reason |
|---:|---|---:|---|
| 0 | Recompense pentru caini Agility, piele de rata, 450g, marimea M | 450 | not found |
| 1 | Hrana umeda pentru caini, RAW PALEO Puppy, carne de curcan, 400 g | 400 | not found |
| 2 | Nutraline Cat Plic Classic Kitten 100 g | 100 | search surfaced a different brand (Prima Cat) |
| 3 | Hrana umeda pentru caini, RAW PALEO Puppy, carne de Vita, 800 g | 800 | not found |
| 4 | ACANA Dog Grasslands, hrană uscată fără cereale câini, 11.4kg | 11400 | search surfaced the CAT Grasslands variant (4.5/1.8kg), not the dog 11.4kg product — likely a query-construction miss, not confirmed absence |
| 5 | Hrana umeda caini, Fresh Farm Smooth pate with pork 400 gr | 400 | not found |
| 8 | Royal Canin British Shorthair Kitten, 10 Kg | 10000 | same product exists, only 2kg variant sold — weight mismatch, genuine non-match |
| 11 | Vet Life Dental Treat Joint Mini 60 g | 60 | not found |
| 12 | Hrana uscata pentru caini Dog&Dog Traditional cu Rata Miscare Constanta 10kg | 10000 | not found |
| 14 | Nutraline Classic Pisica Pui, 100 g | 100 | search surfaced an unrelated litter product |
| 15 | Brit Care Dog Hypoallergenic Adult Large Breed 3 kg | 3000 | not found |
| 16 | Taste of the Wild Cat - Canyon River Formula, 2 kg | 2000 | not found |
| 17 | Advance Dog Mini Sensitive Somon & Orez, 7 kg | 7000 | not found |
| 18 | Hrana uscata pentru caini Unica Classe mini, puppy development, cu pui, 7,5 kg | 7500 | not found |
| 19 | Recompense delicioase pentru caini Agility, pui si rata cu cod, 500g | 500 | not found |
| 20 | Hrana uscata pentru caini super premium CHICOPEE CNL SENSITIVE Duck&Rice 15 kg | 15000 | not found |
| 21 | Acana Free-Run Duck - Rata si pere, 11,4 kg | 11400 | not found |
| 22 | Pro Plan Optiderma Adult Small & Mini Sensitive Somon, 3 kg | 3000 | not found |
| 23 | Hrana uscata pentru caini Brit Premium by Nature Adult M 8 kg | 8000 | same product exists, only 15kg variant sold — weight mismatch, genuine non-match |
| 24 | PURINA Dentalife Medium, recompense delicioase pentru talie medie, 115 g | 115 | not found |
| 25 | Churu Pops Recompensa Suculenta cu Pui si Ton fara cereale - 4 x 15 g | 15 | not found |
| 26 | Hrana uscata pisici, Calibra Cat Life Adult Herring 1.5 kg | 1500 | search surfaced a different Calibra line (Verve GF, dog food) |
| 27 | Hrana uscata caini, Josera Mother & Puppy with Salmon & Rice 3 kg | 3000 | not found |
| 28 | Primordial Grain-Free Holistic Dog Adult Tuna&Lamb Super Premium 12kg | 12000 | not found |
| 29 | Hrana uscata pentru caini Devora Grain Free cu iepure 7.5 kg | 7500 | same brand+flavour exists as "Monoprotein" line, only 1.5kg — weight mismatch |
| 30 | Piper Adult, Hrana Umeda, Carne de Cod si tomate, 800 g | 800 | not found |
| 31 | Sheba Mini, Selectii de pasare 6x50g | 50 | search surfaced a different brand (Whiskas) — same parent company (Mars), not the same purchasable unit |
| 32 | Pro Plan Large Athletic Adult, pui, 14kg | 14000 | page failed to render content (site glitch) — treated as unconfirmed/no-match, not retried |
| 33 | Royal Canin Instinctive Adult, plic hrană umedă, (în sos), 12x85g | 85 (pack 12) | product exists, single 85g pouch only — no 12-pack variant, pack_count mismatch |
| 34 | Hrana uscata caini, Calibra Dog Life Senior Small Breed Lamb 1,5 kg | 1500 | not found |
| 35 | Recompense pentru pisici Mr. Bandit CAT Creamy Mousse, pui, 60 g | 60 | not found |
| 36 | Hrana umeda pisici, Calibra Cat Life Can Adult Salmon 200 g | 200 | not found |
| 37 | Hrana umeda pisici, Calibra Cat Pouch Premium Line Adult Trout & Salmon 100 g | 100 | not found |
| 38 | Hill's SP Feline Adult Sterilised Salmon 1.5 kg | 1500 | not found |
| 39 | Hill's SP Canine Adult Perfect Digestion Small and Mini 3 kg | 3000 | not found (checked with and without the apostrophe, to rule out an encoding artifact) |

## Status

Stopped at 40 of the planned 150 draws — the target was CI width, not draw count, and the honest
per-item cost at this hit rate made the full 150 impractical within one session. The remaining 110
drawn-but-unchecked candidates are still in `phase3-q3-extension-draw.json` (not committed) if a
future session wants to continue this exact draw rather than start a new one.
