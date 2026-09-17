# Phase 3 item 1 — candidate retrieval: eval-set growth, hybrid retrieval, K-sweep (2026-09-16)

Context: candidate retrieval recall@20 is the only measured Phase 3 gate currently missed —
57.7% (15/26) on the unbiased `q3_browser_verified` subset against CLAUDE.md's >=90% target
(ADR-0028). Two blocks, in order per instruction. No annotation run started.

## BLOCK 1 — growing the unbiased eval set

### (a) The remaining 25 "not found" rows, rechecked

`docs/learned/q3-verification-extension-2026-09-15.md`'s Table 2 had 35 "not found" rows; 10 were
rechecked in a prior same-day session (6 confirmed). The remaining **25 were rechecked this
session** via pentruanimale's public VTEX Catalog API (full SKU list per product — the same
mechanical method that made the earlier 7-row check fast), query = brand root + 1-2 distinguishing
words, never brand + product_line.

**12 of 25 are genuine, confirmed matches** — the petmax weight appears in the product's full SKU
list, missed by the original full-descriptive-query check:

| # | petmax item | confirmed at |
|---:|---|---:|
| 0 | Agility, piele de rață, 450g | 450g (only SKU) |
| 1 | RAW PALEO Puppy, curcan, 400g | 400g |
| 4 | ACANA Dog Grasslands, 11.4kg | 11.4kg |
| 5 | Fresh Farm Smooth pate pork, 400g | 400g (dog line) |
| 8 | Royal Canin British Shorthair Kitten, 10kg | 10kg (out of stock, listed) |
| 18 | Unica Classe Mini Puppy, 7.5kg | 7.5kg |
| 21 | Acana Free-Run Duck, 11.4kg | 11.4kg (out of stock, listed) |
| 22 | Pro Plan Optiderma Small&Mini Somon, 3kg | 3kg (via the "Adult S" variant) |
| 31 | Sheba Mini, 6x50g | 50g x 6buc (exact) |
| 32 | Pro Plan Large Athletic Adult, 14kg | 14kg |
| 35 | Mr Bandit Creamy Mousse, pui, 60g | 60g |
| 37 | Calibra Cat Pouch Premium Line Trout&Salmon, 100g | 100g |

13 remained genuine non-matches or absences after the full-SKU check (2 brand-not-found, 3
weight-mismatch-confirmed-by-full-SKU-list [rows 23/29 — no matching weight exists at all], 1
flavour-combo mismatch [row 19: petmax's 3-flavour combo doesn't exist as a single SKU], 1
form/life-stage/species mismatch [row 36: pouch vs can, junior vs adult], others genuinely
not-found even bare-brand).

**Corrected 40-row rate: 5 (original) + 6 (prior session's 10-row recheck) + 12 (this session's
25-row recheck) = 23/40 = 57.5%, Wilson 95% CI [42.2%, 71.5%].**

**This reconciles with Q3's original 54%** — the point estimate now essentially matches it, and
54% sits well inside the CI (previously, at 12.5%, the CI's own upper bound was 60.9%, barely
brushing 54%; the acute contradiction addendum #3 first flagged is now closed, not just bounded).
This closes the TASK A question completely, as the prior session's note said the remaining recheck
would: every one of the 35 "not found" rows from the extension has now been checked against a
full SKU list, not just the default/shown variant.

**Caveat carried forward honestly**: this 40-row sample is still a small, non-random-in-the-usual-
sense subsample (drawn once, seed `20260915`) of the much larger keyable population; it is not
itself the Phase 1 gate measurement (ADR-0023's own p̂=0.52, n=50, remains that), and the CI here
[42.2%, 71.5%] is wide. It was never meant to re-measure the gate — its purpose was always to grow
the retrieval eval set's headline subset, which is BLOCK 1(b)'s job below.

Not usable for BLOCK 1(b) despite being confirmed real-world matches: rows 0, 5, 8, 31 — the exact
matching pentruanimale SKU exists live on the site but was never collected by our own daily
scraper (out of stock at scrape time, or a specific SKU the scraper's VTEX-variant expansion
missed). A confirmed market match and a retrieval-testable pair are different claims; only pairs
present on BOTH sides in our own `norm_listings` can test our retrieval system.

### (b) New random draw, brand-root query, growing the eval set

**Population**: petmax, in-scope (food/litter), keyable, brand stated, excluding every title
already checked in `q3-verification.md` and its extension (120 titles extracted and excluded,
somewhat more than the ~90 actually checked — over-exclusion is safe here, never contaminating).
**2,380 eligible rows.** Drew **300** with a new seed (`20260916`).

**Method, strictly query-independent of the embedding input** per instruction: query = brand
alone (VTEX Catalog API `ft=<brand>`), not brand+product_line. For each result sharing the target
brand, checked every SKU's weight against the petmax listing's weight (±1%). A purely
weight-plus-brand automated match is **not enough on its own** — checked directly, not assumed:
an unscored first pass produced obvious false positives (same brand, same weight, wrong product —
"Royal Canin Kitten 10kg" matched to "Royal Canin Hairball Care Adult 10kg", a coincidence of
brand+weight with zero token overlap). Tightened to require flavour-canonical agreement
(`normalize.flavour.extract_flavour`, already EN/RO-canonicalising) or substantial title-token
overlap before treating a candidate as high-confidence — and **every surviving candidate was
still read by eye before counting it**, the same "scan by eye" discipline Q3's own method used,
not blind trust in the automated score. This caught real remaining false positives the automated
score alone would have accepted: a Purina "Pro Plan" queried but matched to "Cat Chow" (same
parent brand, different retail tier — not the same purchasable unit), a Calibra DOG product
matched to a Calibra CAT product (species mismatch), a "Julius-K9 Vital Essentials" matched to
"Julius-K9 Hypoallergenic" (a formula-defining qualifier under this project's own conventions
rule 3, genuinely a different product), and two "Brit Care Fillets In Gravy" queries that both
matched the same wrong (Duck) flavour variant regardless of the actual requested flavour.

**Coverage/cost, reported plainly**: of 300 drawn, 226 were successfully queried (74 hit a
transient fetch failure this session could not recover even on retry — a real, unexplained
reliability gap in this pass, not investigated further; reported as a limitation, not padded
past). Of 226 queried, 18 scored high-confidence automatically; after eye review, **11 were
genuine matches with both sides present in our own collected data** (a 12th, real-world-confirmed
match — Libra Adult Light Curcan 12kg — was dropped for the same DB-absence reason as the 4 rows
above). 83 scored as weak candidates; **0 survived eye review** (all were flavour, species, or
life-stage mismatches the automated score's weaker signal missed).

**Per-item cost**: roughly 300 draws -> 11 usable confirmed pairs, ≈27 draws per usable pair at
this population's current match rate and this session's query strategy — reaching 100 total
headline pairs (61 more needed beyond the 39 this block already produced) would take on the order
of 1,600-1,700 more draws, not achievable in this session's remaining budget. **Stopped at n=50
for the headline subset, reported honestly rather than padded**, per instruction.

**Final unbiased headline subset: n = 26 (original) + 13 (block 1a, both prior-session's 6 and
this session's new 8/12 usable) + 11 (block 1b) = 50.**

### Recall@20, the new baseline, BEFORE any Block 2 change

| | dense, unblocked | dense, blocked by `brand_blocking_key` |
|---|---:|---:|
| headline (n=50) | 19/50 = 38.0%, CI [25.9%, 51.8%] | **33/50 = 66.0%, CI [52.2%, 77.6%]** |

**66.0% (33/50) is the honest new baseline** — this already includes ADR-0028's own prior fixes
(embedding-text weight tail, brand blocking); nothing in BLOCK 1 changed retrieval itself, only
grew the measurement. It is higher than the previously-reported 57.7% (15/26) — the 24 new pairs
this session added skew somewhat easier to retrieve on average than the original 26, a real
composition effect of an unbiased-but-different draw, not a retrieval change. Still below the
90% gate.

## BLOCK 2 — improving recall@20 toward >=90%

### (c) Failure-shape analysis, current misses, current (larger) eval set

17 misses in the blocked-dense baseline (33/50). Re-grouped from scratch — the embedding text,
blocking key, XS-XL nulling, canonical breed size and extended life_stage have all changed since
ADR-0028's original grouping, so its "roughly half weight-crowding, half weak discrimination"
split is not assumed to still hold and is not carried forward:

| shape | count | % of misses | example |
|---|---:|---:|---|
| **EN/RO flavour-word crossing** — Salmon/Somon, Lamb/Miel, Turkey/Curcan, Chicken/Pui, Trout/Păstrăv; the multilingual embedding does not reliably place these close for this domain's rare/compound vocabulary | 5 | 29% | "Brit Premium Cat Sterilized **Salmon**" vs "BRIT Premium Sterilized **Somon**" |
| **Retailer-specific line/sub-brand naming divergence** — same formula, marketed under a different name per shop (no shared vocabulary at all, not even a translation pair) | 4 | 24% | "Pro Plan **Optiderma**" vs "PURINA Pro Plan **Sensitive Skin**" (same product) |
| **One-sided extra descriptive text** — one shop's title states an ingredient/qualifier the other omits entirely, diluting a whole-title embedding | 4 | 24% | "Brit Care Dog Sustainable Sensitive 1kg" vs "...XS-XL, **Insecte și Pește**, ...1kg" |
| **Near-identical text, still missed** — likely same-brand/-line crowding inside a large product family even after blocking | 3 | 18% | "Calibra Cat Life Adult **Herring**" vs "CALIBRA Life, **Hering**" |
| **Packaging/pack-count description variant** | 1 | 6% | single 85g pouch vs a 12-pack SKU of the same line |

**EN/RO flavour crossing is now the largest single shape** (was not separately named in ADR-0028's
grouping) — notable because `build_embeddings.py::embedding_text()` does **not** currently include
the canonical `flavour` field at all (already EN-canonicalised by `normalize/flavour.py` on both
sides), only `product_line`, which carries whatever raw EN/RO word the title happened to use.

### (d) Hybrid retrieval — lexical channel + Reciprocal Rank Fusion

Built `scripts/measure_recall_hybrid.py`: a lexical channel (Postgres full-text,
`to_tsvector('simple', ...)` / `ts_rank_cd`) over the **same text** the dense embedding uses (not
a different, hand-picked text — isolates the ranking method, not a text change), fused with RRF
(`k=60`, the standard constant — no score-scale calibration needed between cosine distance and
`ts_rank_cd`, which do not share units).

| channel | recall@20 (headline, n=50) |
|---|---:|
| 1. Dense alone, unblocked | 19/50 = 38.0%, CI [25.9%, 51.8%] |
| 2. Lexical alone, unblocked | 6/50 = 12.0%, CI [5.6%, 23.8%] |
| 3. RRF fused, unblocked | 22/50 = 44.0%, CI [31.2%, 57.7%] |
| **4. RRF fused, blocked by `brand_blocking_key`** | **36/50 = 72.0%, CI [58.3%, 82.5%]** |

**Lexical alone is much weaker than dense alone** (12.0% vs 38.0%) — expected, and itself a
finding: raw keyword overlap cannot bridge the EN/RO flavour-crossing shape at all (Salmon and
Somon share zero tokens), so a lexical channel is a poor *replacement* for the dense channel here,
only a *complement*. Fusing the two still lifts blocked recall from **66.0% to 72.0% (+6pp)** —
a real, measured improvement, not from a stronger model but from combining two weak, differently-
wrong signals.

**Checked, not assumed to help further**: adding the canonical `flavour` field to the lexical
channel's text (directly targeting the #1 failure shape) was tried and measured — blocked+fused
recall stayed at 72.0% (36/50, unchanged), unblocked figures moved by 1-2pp, within noise. Not
adopted; reported as a checked dead end, not silently dropped.

### (e) Recall at K = 20, 50, 100

| | K=20 | K=50 | K=100 |
|---|---:|---:|---:|
| **unblocked** | 38.0% (19/50) | 42.0% (21/50) | 42.0% (21/50) |
| **blocked** | 66.0% (33/50) | 82.0% (41/50) | **94.0% (47/50)** |

**These two curves answer different questions, and the answer differs sharply between them.**
Unblocked, recall is nearly flat past K=20 (38% -> 42%, +2 pairs total) — most unblocked misses
are **absent from the ranking entirely**, not merely outside the top 20; the global embedding
ranking genuinely does not place these pairs near each other in the full population, no widening
of K recovers them. **Blocked, recall climbs steadily and reaches 94% by K=100** — most blocked
misses ARE present, just ranked 21-100 within the (already brand-restricted) candidate pool. This
says plainly where the remaining problem lives: **blocking (candidate generation) is doing nearly
all the real work already; the open problem is within-block ranking at the top of a correctly-
scoped pool, not absence of the true match from that pool.** This is exactly consistent with (d)'s
result — RRF fusion, which only re-ranks within whatever pool it's given, recovered some of that
21-100 rank gap and pushed blocked K=20 from 66% to 72%.

### (f) A stronger embedding model — not attempted, blocked by the environment, not skipped by choice alone

Checked before deciding, not assumed unnecessary: `import sentence_transformers` was attempted in
this session's environment and **fails outright** —
`ImportError: DLL load failed while importing _argkmin: An Application Control policy has blocked
this file` (scikit-learn's compiled `_pairwise_distances_reduction` extension, a transitive
dependency of `sentence_transformers` via `sklearn.metrics`). This is the same Windows sandbox
Application Control restriction that blocked `psycopg`'s binary wheel in the previous session
(worked around there with a pure-Python driver; no pure-Python equivalent exists for a
transformer-model forward pass). **This session cannot load ANY sentence-transformers model,
including the current one already in production** — every measurement above read pre-computed
embeddings out of Postgres via `pgvector`'s `<=>` operator in raw SQL, never recomputed one. A new,
stronger model could not have been encoded this session regardless of the recall figures.

This is reported as an environment limitation, not a judgement call dressed up as one — but two
things temper how much that limitation actually costs: (1) (e)'s own finding is that **ranking
within an already-correct candidate pool, not the embedding's absolute quality, is the dominant
remaining gap** (94% of blocked misses are recoverable by K=100 — the true match is already
"nearby," just not ranked in the top 20) — a materially better embedding model narrows that
somewhat but does not address the two largest failure shapes ((c): EN/RO flavour-crossing and
retailer-specific line naming, 53% of misses combined), which are lexical/domain-vocabulary
problems no generic multilingual model is trained to resolve for this catalogue specifically; (2)
CLAUDE.md's own Phase 3 architecture already calls for a small, fine-tuned, CPU-servable model as
the *matching* stage — the natural home for exactly this re-ranking work, not a second embedding
model bolted onto candidate generation. Recorded as a real open item for a session with a working
`sentence-transformers` environment, not silently dropped.

## 2026-09-17 session — the cheapest untried fix: canonical fields in the embedding text

### Per-field audit: raw token or canonical value?

Every field `build_embeddings.py::embedding_text()` uses, audited before changing anything:

| field | in the text? | raw or canonical |
|---|---|---|
| `brand` | yes | **canonical** (`canonicalize_brand()` output, already deduplicated across spelling) — but NOT the further hyphen/space-insensitive `brand_blocking_key`. Left as-is: `brand_blocking_key` only differs from `brand` for ~5 known punctuation-collision cases, a much narrower gap than the two below, and `brand` itself is already real canonical text, not a raw title token. |
| `product_line` | yes | **canonical** (brand-stripped extraction) |
| `net_weight_g`/`net_volume_ml` | yes | **canonical** (parsed structured numeric) |
| `pack_count` | yes | **canonical** (structured numeric) |
| `life_stage` | yes | **canonical** (extractor output, includes the age-qualifier extension) |
| `breed_size_code` | yes | **RAW TOKEN** — "Medium" and "M" stayed different strings even though `breed_size_class()` (built last session) already unifies them |
| `flavour` | **absent entirely** | N/A — `extract_flavour()` already canonicalises Salmon/Somon, Lamb/Miel, Turkey/Curcan etc. to one EN value on both sides, but the embedding never saw it |

Two real gaps, both fixed in `build_embeddings.py` (full docstring/audit table also lives there):
`breed_size_code` swapped for canonical `breed_size_class`; `flavour` added to the tail.

### Re-embedding: how, given `sentence-transformers` is blocked in this environment

Confirmed again this session: `import sentence_transformers` still fails
(`ImportError: DLL load failed while importing _argkmin`). Checked one level deeper before giving
up: the SAME model can be run via `transformers`' `AutoTokenizer`/`AutoModel` directly (mean-
pooling + L2-normalize is the documented standard recipe for this model family — exactly what
`SentenceTransformer.encode()` does internally) — but `transformers` ALSO transitively imports
`sklearn` (for an unrelated assisted-generation feature, `roc_curve`), hitting the same blocked
compiled extension. **Fix**: stub `sklearn`/`sklearn.metrics` in `sys.modules` before either
library is imported, with dummy functions for the two names actually referenced
(`roc_curve`, `pairwise_distances`) — neither is ever called for a plain embedding forward pass.
This runs the real model with its real downloaded weights; nothing here is simulated or
estimated. Confined to a scratch script for this session's re-embedding pass, the same discipline
applied to the `pg8000` workaround — `build_embeddings.py` itself is untouched and still imports
`sentence_transformers` normally, since this sandbox's restriction is not assumed to exist on
Bogdan's own machine or the deployment target. Encoded all 10,532 rows in 134s.

### Recall@20, before vs. after, on the same n=50 unbiased set

| | dense, unblocked | dense, blocked | RRF fused, blocked |
|---|---:|---:|---:|
| before (raw `breed_size_code`, no `flavour`) | 38.0% (19/50) | 66.0% (33/50) | 72.0% (36/50) |
| **after (canonical fields)** | 36.0% (18/50) | **74.0% (37/50)** | **88.0% (44/50)** |

Unblocked dense moved by one pair, within noise (38.0% -> 36.0%). **Blocked dense — the
production-relevant number — improved 66.0% -> 74.0% (+8pp), and blocked+fused reached
88.0% (44/50), CI [76.2%, 94.4%]** — a combined +22pp over last session's reported final figure,
from a text change alone plus the existing hybrid fusion, no new model.

### Failure shapes after the change — does the EN/RO shape actually shrink?

13 misses now (blocked dense), down from 17. Re-checked, not assumed: **all 4 pairs still
readable as "EN/RO flavour crossing" (Salmon/Somon, Lamb/Miel, Turkey/Curcan, Chicken/Pui) were
queried directly against `norm_listings` — `flavour` is extracted correctly and MATCHES on both
sides for every one of them** (`salmon`=`salmon`, `lamb`=`lamb`, `turkey`=`turkey`,
`chicken`=`chicken`). **The prediction this fix made — that adding canonical flavour would shrink
the EN/RO shape — is only partly borne out, and the honest reading matters more than the round
number:** the shape's raw count barely moved (5 of 17 -> 4 of 13), but **the mechanism changed**.
The flavour-alignment problem this fix targeted is actually fixed at the data level for these 4
pairs (verified above) — they no longer fail because of an EN/RO mismatch, since that signal is
now correctly present and matching in the embedding text. They still miss for a different reason:
substantial remaining divergence elsewhere in `product_line` phrasing (`"Care Cat Fillets in
Gravy Choise Chicken"` vs. `"Care Fillets In Gravy, Pui"` — extra words, reordered structure,
word choice) inside a large, crowded product family (Brit Premium by Nature, Brit Care), which
the dense embedding still doesn't fully collapse even with brand+flavour+weight+breed-size all
aligned. **One of the five original EN/RO-crossing misses (Calibra Cat Pouch Trout & Salmon) WAS
resolved by this fix** — so the mechanism does work, it is just not sufficient on its own for
titles that also differ this much in general phrasing. Reported as a finding, not rounded away:
the fix's own prediction (raw shape count shrinks) mostly did not happen, even though its
underlying mechanism (flavour alignment) demonstrably did.

New shape breakdown on the 13 remaining misses: one-sided flavour/crowding-in-a-large-family (6,
46%), residual EN/RO-labelled misses now shown to be a phrasing/crowding problem, not a flavour
problem (4, 31%), line-naming divergence (2, 15%), title-length asymmetry (1, 8%).

### K-sweep, re-measured

| | K=20 | K=50 | K=100 |
|---|---:|---:|---:|
| unblocked | 36.0% (18/50) | 38.0% (19/50) | 38.0% (19/50) |
| blocked | 74.0% (37/50) | 78.0% (39/50) | **96.0% (48/50)** |

Same shape as before the fix, at a higher level: blocked recall keeps climbing to 96% by K=100 —
the "true match is in the block, just ranked low" finding still holds, now even more strongly.

## Final figure against the 90% gate

**88.0% (44/50), Wilson 95% CI [76.2%, 94.4%].** This is close enough that the CI's own
upper bound (94.4%) clears the gate, but the point estimate does not, and the point estimate is
what's reported.

**Correction, 2026-09-17 (ADR-0028 addendum #8), left here rather than silently edited above: the
"MISSED against the target" framing overstated what n=50 can support.** The >=90% target sits
INSIDE the 95% CI — 88% and 90% are not statistically distinguishable at this sample size. The
honest reading is a measurement-power finding, not a pass/fail verdict: point estimate below
target, gap inside the measurement's own noise, ~1,000 verified positive pairs (~27,000 draws at
this project's observed hit rate) needed to resolve it further. Full correction:
`docs/learned/phase3-embedding-equivalence-2026-09-17.md` and DECISIONS.md ADR-0028 addendum #8.

The K=20-vs-K=100 argument — a re-ranking component (the Phase 3 matching model itself) could
close the remaining gap, since most misses are ranked 21-100, not absent — is written up as a
**PROPOSED** decision, not applied, in DECISIONS.md ADR-0028 addendum #7 (item 3). Nothing about
that argument has been acted on; recall@20 stands as measured and missed.

## Structural limitation of the eval set itself, recorded honestly

**Every one of the 50 headline pairs was found by a brand-root query against pentruanimale.**
Blocked retrieval — the config every recall figure above that matters uses — blocks candidates on
`brand_blocking_key`. Those are nearly the same condition: for a pair to exist in this eval set at
all, a recognisable, shared brand string had to be found by the query that built it; for blocking
to find that same pair, a recognisable, shared brand string has to exist in the data. **The eval
set structurally cannot contain the class blocking fails hardest on** — pairs whose brand strings
do NOT align across shops, which is exactly the distributor-code class ADR-0028 already documented
(`"Ipts"`, `"opti"`, the `brand_is_distributor_code` flag) and the reason
`top_k_hashes_blocked()`/`fused_blocked()` both carry an explicit fallback to unblocked search
when `brand_blocking_key` is null or flagged a distributor code.

**Checked directly, not assumed**: queried all 50 headline pairs' 100 listing rows against
`norm_listings` — **0 have `brand_is_distributor_code = true`, and 0 have a null
`brand_blocking_key`.** The fallback code path inside blocked retrieval has **never been
exercised by any measurement in this document.** Every blocked/fused recall figure reported here
— 66.0%, 74.0%, 72.0%, 88.0%, all of it — is recall **on brand-aligned pairs specifically**.
Recall on brand-misaligned pairs, where blocking cannot help and the fallback path is the only
thing standing between the query and a miss, is **unmeasured**.

**This is not a defect introduced this session.** Q3's own original method (2026-09-13) was
brand-anchored too ("brand root + weight, then scan by eye" — the method this whole eval set has
used from its first pair onward, precisely because it's the query strategy independent of the
embedding input). All 50 pairs inherit this the same way. It is a structural property of how every
verification pass in this project's history has built this eval set, not a new gap.

**Part of the measured "blocking lift" is therefore a sampling artefact, not purely a retrieval
result.** Blocking's own +28-38pp lift over unblocked search (measured repeatedly across sessions)
is real for brand-aligned pairs, but this eval set could not have shown a SMALLER lift even if
blocking's fallback path performed badly on brand-misaligned pairs, because no brand-misaligned
pair is in the set to show it.

**What an unbiased draw would require**: a random sample of petmax listings whose MATCH is
verified by some method that does NOT presuppose a shared brand string — e.g., drawing from
`raw_listings` rows already flagged `brand_is_distributor_code` and manually searching
pentruanimale by product_line/flavour/weight text alone, ignoring brand entirely, then checking
whether the found match's brand field actually differs. This is a fundamentally different (and
slower — no brand root to anchor the search) verification method than every pass so far, and
**would need its own session**; not attempted here, recorded as a known, named gap rather than
quietly extrapolated past.
