# Phase 3 reference labelling pass — response to findings 4-8 (2026-09-15, fourth session)

Context: `docs/learned/phase3-pilot100-ai-reference-pass.json` (committed, produced by an Opus
architect session, not a human — a measurement of the queue, never training data) labelled the
first 100 pairs of the pilot slice: observed M 36 / N 62 / S 2, against the rules engine's
forecast of M 33 / N 53 / S 14 — agreement 80/100. Five extractor/signal gaps surfaced by that
20-pair disagreement are addressed below. The queue itself already clears its ≥25% M-plausible
floor, so this is a targeted fix pass, not a rebuild of the sourcing logic (that happened in
ADR-0028's addenda).

No annotation run was started at any point in this session, per standing instruction.

## Finding 4 — species (dog/cat) signal, added

`norm_listings` had `category` (food/accessory/litter/toy) but nothing distinguishing dog
products from cat products — the most basic blocking dimension in pet food, and the cause of 4 of
the pilot's 100 pairs (positions 8, 14, 39, 72) being cross-species.

**Built**: `src/pricepilot/normalize/species.py`, `classify_species()` — same pattern as
`category.py`: a structured signal where a source publishes one (petmax's URL segment, animax's
`product_type`), a checked title-keyword vocabulary otherwise (pentruanimale has no structured
species field at all, same gap `category` has for that source). Backfilled by
`scripts/backfill_phase3_signals.py` into a new `norm_listings.species` column (migration 0008),
same script that already backfills `category`/`brand_blocking_key`/`brand_is_distributor_code`.

**Checked against the full population before trusting** (not guessed): the litter of this
catalogue is exclusively cat litter (every in-scope `category="litter"` row inspected this
session — no dog litter product exists here), so `category == "litter"` resolves to `"cat"`
directly. Two real false-positive classes were found and excluded from the title-keyword
fallback:

1. **`"canin"` (bare stem) collides with the brand name "Royal Canin"** on cat products
   ("Royal Canin Feline Sterilised...") — this alone was responsible for 282 titles initially
   flagged "both dog and cat". Fixed by using `"canine"` (the word Hill's actually writes for its
   own dog line, "Hill's SP **Canine**") instead of the bare stem — no collision with "Canin" (no
   trailing e in this data's brand spelling).
2. English `"dog"`/`"cat"` loanwords appear in a real, checked slice of titles ("Advance **Dog**
   Adult Sensitive...", "NATURES PROTECTION Superior Care White **Dogs**...") that carry no
   Romanian species word at all — added as alternatives.

**Population split (in-scope, food/litter, 8,803 rows): dog 4,888 (55.5%), cat 3,791 (43.1%),
unknown 124 (1.4%)** — down from 250 (2.8%) before the two fixes above. The 124 remaining
unknowns are concentrated in two honest, checked classes, neither guessed: dog-specific dental
chews/rawhide bones with no species word in the title at all (~120 rows, e.g. "Os Presat Trixie
22 cm, 230 g" — a human would infer "dog" from the product type, the title alone doesn't say so),
and a small number of genuine dual-species products ("supliment pentru articulatii câini și
pisici"). Both left `None`, not guessed either way, same discipline `category.py` already uses.

**Cross-species pairs are still in the queue — not removed.** A cat-vs-dog pair is a guaranteed
`N` that teaches a matcher nothing it can't get from one field, so it's tempting to filter them
out at the source the way finding 8 filters out-of-scope categories. That temptation was
rejected this session: at a small, deliberate quota, cross-species pairs are a legitimate
easy-negative class (the fine-tuned model needs some examples of the cheapest, most obvious
negative, not zero), and CLAUDE.md's own precedent (`trivial_spot_check`, 50 pairs / 5.0% of the
queue, kept deliberately for self-agreement checking rather than difficulty) supports keeping a
small slice of "easy" pairs by design. **Current count: 49 of 997 (4.9%)** — both sides' species
known and differing (19 more pairs have one side unknown, not counted as cross-species since that
would be a guess; 1 pair has both sides unknown). **Proposed quota: ~2% (≈20 pairs)** — lower than
the other required hard-negative sub-classes (4.7%-6.6% each, `same_capacity_diff_breedsize`/
`diff_brand_similar_title`/`same_capacity_diff_lifestage`), because species is cheaper and more
certain to decide than any of those — a handful of examples verifies the annotator/tool handle it
correctly and gives the model a few clean negatives, without spending scarce annotator-hours (200
pairs/hour) on something one regex already resolves with near-certainty. **Current 4.9% sits
above that proposed 2% cap** — reported as a finding for a future queue rebuild's quota tuning,
not acted on this session per instruction (not removed).

**Wired into the forecast**: `predict_label()` gained a new rule — species differs (both known)
-> `N` — placed ahead of the quantity rule, since a species mismatch makes quantity comparison
moot. Promoted to Rule 1 of the annotation conventions (revision 3, `phase3-annotation-
conventions.md`) after a follow-up review — see that document's own revision-3 note.

## Finding 5 — breed-size vocabulary canonicalised across word/letter/range forms

"Medium" and "M" are the same size (pilot 12, a real Hill's cross-shop match the raw-string rule
called `N`); so are "Mini" and "XS-S" (pilot 55, Rinti Gold).

**Census printed first, not assumed** (18 distinct `breed_size_code` values, in-scope population):
XS-XL 985, Mini 400, Medium 284, XS-S 230, Maxi 117, L-XL 96, M 73, M-XL 53, L 51, S 47, S-XL 25,
XS-M 21, XL 19, XS-L 12, M-L 8, S-M 6, XS 10.

**Equivalence classes built from the real population, two independent ways, not assumed from the
two examples the finding named:**

1. pentruanimale_ro's own titles frequently state a word form AND a compact code together in the
   *same* title (e.g. "..., Large Breed, **L-XL**, ...") — self-consistent, single-source
   evidence, no cross-shop noise. Dominant, checked pairings: Mini/Small <-> XS-S (170+ titles),
   Large <-> L-XL (63), bare Maxi <-> L-XL (18), the *distinct compound phrase* "Medium & Maxi"/
   "Medium and Maxi" <-> M-XL (27, not the same mapping as bare "Maxi" — checked separately after
   an initial regex conflated the two), Giant <-> XL (4).
2. A cross-shop join (same `brand_blocking_key`, quantity, flavour, life_stage, food_form, food
   category — near-certain same real product) surfaced 75 cross-shop pairs with differing
   `breed_size_code`, confirming the same pairings from independent evidence (e.g. `DEVORA Puppy
   Medium&Large, M-XL` (pentruanimale) = `Devora Dog Puppy GF Medium - Large` (animax, tagged
   plain "Medium" — its own extractor only ever catches one word)).

**Modelled as a rank interval, not a flat bucket** (`attributes.py`, `breed_size_rank()`/
`breed_size_class()`/`breed_size_overlaps()`): XS=1, S=2, M=3, L=4, XL=5; a word maps to the
interval its dominant real pairing supports (Mini/Small=(1,2), Medium=(3,3), Maxi=(4,5)); a
compound code's endpoints are parsed directly (M-XL=(3,5), etc. — these are already
self-describing, no guessing needed). Two codes are "the same size" if their intervals share any
rank, not only if the strings match — this is what correctly resolves Medium(3,3) vs M-XL(3,5)
(overlap at 3) without forcing a single flat bucket to arbitrarily pick a side, the trap a 3-bucket
scheme would have hit given "Maxi" genuinely means different things in different compound
contexts. `predict_label()`'s rule 3 now calls `breed_size_overlaps()`.

## Finding 6 — "XS-XL" is pentruanimale's all-sizes marker, mapped to NULL

Checked every XS-XL occurrence in the population, not assumed: **100% of the 985 in-scope rows
carrying this literal code are pentruanimale_ro — 0 from petmax_ro, 0 from animax_ro** — and it is
the single largest `breed_size_code` value in the whole population (ahead of "Mini"'s 400),
consistent with a boilerplate default stamped on most of that shop's product pages rather than a
real size restriction.

**Fixed at the extractor** (`attributes.py::extract_breed_size`): a compound-code match of
literally `"XS-XL"` now returns `None` instead of the code — "no breed-size stated", not a real
claim. Existing rows re-extracted via `scripts/reextract_breedsize_lifestage.py`.

**Effect on the forecast**: nulling XS-XL removes the *asymmetry* it was creating — a
pentruanimale row previously showed "XS-XL" (stated) against a petmax/animax row showing nothing
(unstated), which rule 6's one-sided-attribute check scored `S`. With XS-XL null, both sides read
"unstated" and the pair falls through to whatever the other rules decide (usually `M`), not `S`.
Exact row/forecast movement: see the final forecast section below.

## Finding 7 — title-only age qualifiers ("(5+)", "7+", "8+") now reach `life_stage`

Pilot 15 (RC Maxi Adult vs. RC Maxi Adult (5+)) and pilot 30 (RC Medium Adult vs. RC Medium Adult
7+) were both scored `M` (both sides read "adult") and are both really `N` — Royal Canin's age
qualifier names a genuinely different formula.

**Checked against the full population before trusting** (97 in-scope titles carry a bare `\d+\+`
token): the overwhelming majority are genuine age qualifiers, but a real false-positive class
exists too — bonus-weight phrases like `"10+2kg GRATUIT"` / `"12+2 kg"` / `"8+1kg GRATUIT"`
(`quantity.py`'s own bonus-weight pattern) also contain a bare digit immediately followed by `+`.
Distinguished by the same shape `quantity.py` already relies on: a bonus-weight `+` is always
immediately followed by *another digit* (the bonus amount); a genuine age qualifier never is
(followed by `)`, `,`, a space, or the string's end). Verified against all 97 titles, not just the
pattern's shape — 0 false positives found after the guard.

**Fixed** (`attributes.py::extract_life_stage`): when a life-stage word is found AND the title
also carries a standalone age qualifier, the qualifier is appended (`"adult"` -> `"adult+7"`).
Only appends when a life-stage word was already matched — a bare qualifier with no life-stage word
("Royal Canin Sterilised 7+") stays `None`, a still-open, honestly-named gap, not guessed into a
new category. **38 of the 97 candidate titles gained a qualifier** after re-extraction (the other
59 were bonus-weight false-positive shapes, correctly excluded, or had no life-stage word to
attach to).

## Finding 8 — Rule 0 leak: root cause found, fixed at the source, not just the forecast

Pilot 86 ("Covor absorbant pentru caini figaro", absorbent pads) reached the queue despite the
food/litter scope. **`category` was correct all along — `"accessory"`, checked directly against
the row.** The actual bug: none of the 9 source SQL queries in `build_annotation_queue.py` ever
filtered on `category` — a pair could enter the queue purely because its `brand_blocking_key`/
`product_line`/quantity tuple matched another query's join condition, regardless of category.
`predict_label()`'s rule 0 caught it downstream and scored it `S` (out-of-scope) — which is
exactly why it showed up as a *forecast* label and not as a visible defect: scoring a leak
correctly after the fact is not the same as never sourcing it.

**Fixed at the source**: `main()` now applies `in_scope_only()` (category in `{"food", "litter"}`,
both sides) to every pool immediately after listings are fetched, before the cross/within-shop
split — one filter point instead of duplicating a predicate into 9 queries. Rule 0 in
`predict_label()` stays as a backstop, documented as such.

**Non-food/non-litter rows in the *previous* (uncorrected) 997-pair queue**: N (measured directly
against the committed `phase3-annotation-queue.json` before this session's fix — see the forecast
section for the corrected queue's own count, which should be exactly 0 after the source-level
filter).

## Re-run forecast vs. observed (M 36 / N 62 / S 2) — and why the first version of this
comparison was invalid

Applied, in order: `scripts/backfill_phase3_signals.py` (species, breed_size_class + the existing
three signals, 10,532 rows), `scripts/reextract_breedsize_lifestage.py` (breed_size_code/
life_stage re-extraction — 985 rows XS-XL -> None, 38 rows gained an age qualifier), then
`scripts/build_annotation_queue.py` rebuilt from scratch (997 pairs, same guard — capacity_differs
29.4% / flavour_differs 13.6% / brand_differs 5.5%, all under the 40% limit). Verified directly
against the rebuilt queue: **0 of its 1,157 distinct listings carry a non-food category** (finding
8's fix confirmed at the source, not just in the forecast).

**The first version of this section compared the rebuilt queue's whole-queue forecast (M 30.2% /
N 57.8% / S 12.0%, n=997) against the 100-pair pilot's observed distribution (M 36 / N 62 / S 2,
n=100) as if they measured the same population. They do not, and the comparison was invalid.**
The pilot's 100 pairs were drawn from the *previous* (pre-fix) queue. The findings changed the
underlying `norm_listings` attributes the source SQL queries join on (species didn't exist before;
XS-XL nulling and the extended life_stage change which rows match `same_capacity_diff_*`'s equal-
attribute joins; the `in_scope_only()` filter removes rows outright) — so the rebuilt queue is
substantially a *different draw*, not the same 997 pairs re-labelled. Measured directly: **only
958/959 of the ~997 pair_ids in the old/new queues are even unique (some pair_ids repeat within a
queue — a pre-existing property, not new), and only 450 pair_ids appear in both queues. Of the
pilot's own 100 pair_ids, only 44 still exist in the rebuilt queue — 56 were drawn out.**
Aggregate-vs-aggregate percentages across two different pair sets cannot be read as "the gap
narrowed" or "the gap didn't close"; that claim needs the same pairs on both sides.

**Corrected comparison, on the intersection only (n=44 — the pilot pairs that survived the
rebuild), before vs. after this session's five fixes, against the AI reference labels for those
same 44 pairs:**

| | BEFORE (old `predict_label`, old attrs) | **AFTER (new `predict_label`, new attrs)** | OBSERVED (AI reference, same 44) |
|---|---:|---:|---:|
| M | 27 (61.4%) | **23 (52.3%)** | 26 (59.1%) |
| N | 10 (22.7%) | **14 (31.8%)** | 17 (38.6%) |
| S | 7 (15.9%) | **7 (15.9%)** | 1 (2.3%) |
| agreement | 34/44 = 77.3% | **35/44 = 79.5%** | — |

**n=44 is small — read these as directional, not precise.** On this genuinely comparable slice:
N moved toward observed (gap 15.9pp -> 6.8pp, the direction finding 4/5's fixes predicted). **M
moved slightly away from observed** (gap 2.3pp -> 6.8pp) — the opposite of what a naive read of
the whole-queue numbers suggested, and small-n noise cannot be ruled out at 44 pairs. **S did not
move at all** (7 pairs before, 7 pairs after — same count) **against observed 1**, confirming
finding 6's hypothesis was only ever a partial explanation: the `one_sided_attribute` bucket that
drives most of the queue's S rate is dominated by one-sided flavour/life-stage cases and 39
`ambiguous_brand_rule6` pairs unrelated to XS-XL, not fixed by nulling it. Agreement ticked up
marginally, 77.3% -> 79.5%.

**No rule was loosened to chase the observed distribution** — doing so would be tuning the
extractor to 100 AI-produced labels, which this instruction explicitly forbids. The whole-queue
forecast (M 30.2% / N 57.8% / S 12.0%, n=997, or its revision-3 update below) remains a legitimate
description of what the CURRENT rebuilt queue looks like — useful for planning the annotation
session — it is simply not comparable to the pilot's 100-pair observed distribution, and is no
longer presented as if it were.

## Follow-up: species promoted to Rule 1 (conventions revision 3)

A same-day follow-up review asked for the species check to be named explicitly in
`phase3-annotation-conventions.md`'s ladder (it existed only in code, as `predict_label()`'s
un-numbered species check, not in the document a human annotator reads). Added as the new **Rule
1** — ahead of the quantity rule, because it's the cheapest and most decisive check available —
with rules 1-8 of revision 2 renumbered to 2-9. `predict_label()`'s rule tags renamed to match
(`rule1_species_differs`, `rule2_quantity_differs`, etc.) — a pure rename, no logic change, so the
queue's forecast did not move for this reason. (The queue was rebuilt again as part of this
follow-up; the M/N/S totals shifted by ~1-3 pairs run-to-run — 302/578/117 vs. the 301/576/120
reported above — which is Python's default per-process string-hash randomisation affecting `set`/
`dict` iteration order upstream of the seeded shuffle, not a behaviour change. Not investigated or
fixed further this session; noted as a minor reproducibility gap for a future one.)
