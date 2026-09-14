# Phase 3 annotation conventions — read this before opening the annotation tool

Written **before** the tool exists, not derived from labelling — Phase 2's own lesson
(`docs/learned/phase2-gate-sample-README.md`) is that conventions invented mid-labelling produce a
dataset that disagrees with itself. If a real pair doesn't fit cleanly under one of the rules
below, that is new information about the problem, not a reason to guess — flag it (`S`) and it
gets folded into a future revision of this file, the same way Phase 2's conventions grew from 5 to
7 as real data revealed gaps.

**Revision 2, 2026-09-15 (architect session).** Revision 1 listed six cases the rules did not
cover and defaulted every one of them to `S`. Six `S` defaults on shapes that each occur dozens of
times in a 1,000-pair queue is not caution, it is an unlabelled dataset — so each is decided here,
with its reasoning, *before* any labelling starts. Rules 1–3 of revision 1 are also consolidated
into a single quantity rule, because they were three statements of one idea and the gap between
them is exactly where case 1 fell through.

## The operational question

> **Are these the same purchasable unit, such that a price-comparison engine should compare
> their prices?**

Not "is this the same product family" and not "would a shopper consider these similar" — the
literal test a matching engine needs to pass: if PricePilot recommended a price for Listing A by
looking at Listing B's price, would that recommendation be sound? A 4.5 kg bag and a 12 kg bag of
the identical formula are not the same purchasable unit — their per-kg price differs structurally,
and comparing them directly would recommend the wrong price. This is the single test every rule
below exists to operationalise.

## The three answers

- **M (match)** — same purchasable unit. Compare their prices.
- **N (no match)** — different purchasable unit, or a different product entirely. Never compare
  their prices.
- **S (skip / uncertain)** — a real answer, not a failure to decide. Used when the title text
  genuinely doesn't resolve the question, or when a decision would take real research per pair
  (checking the manufacturer's site, reading ingredient lists) that isn't worth the annotator's
  time at 200 pairs/hour. **The `S` rate is reported as a finding about how hard this matching
  problem actually is — never silently dropped from the dataset, never treated as noise to
  minimise.** A high `S` rate on a particular hard-case tier is itself useful evidence for Phase
  3's error analysis.

---

## The decision ladder

Apply in order. The first rule that fires decides the pair. At 200 pairs/hour the median decision
is under 18 seconds, so the ladder is built so that the cheapest checks come first.

### Rule 0 — out of scope → `S`, move on

If either listing is not **food, treat, or litter** — an accessory, toy, bowl, leash, collar,
crate, grooming item — press `S` and move on without thinking about it. See *Scope* below: the
first annotation round deliberately covers food/treat/litter only, and the queue builder is
supposed to have filtered these out. One that reaches you is a queue bug, not a hard case; the
`S` rate on rule 0 is the measurement of that bug.

### Rule 1 — the quantity tuple differs → `N`, always

The purchasable unit is defined by this tuple:

> `(net_weight_g or net_volume_ml, pack_count, bonus_weight_g)`

**Any difference in any element → `N`.** No exceptions, no "close enough" (1.5 kg vs 1.4 kg is
`N`). This single rule replaces revision 1's rules 1, 2 and 3, which were three faces of it:

| Shape | Tuple left | Tuple right | Answer |
|---|---|---|---|
| 4.5 kg vs 12 kg, same formula | (4500, –, –) | (12000, –, –) | N — weight |
| `12x85 g` multipack vs single `85 g` | (85, 12, –) | (85, 1, –) | N — pack_count |
| `12+2 kg` bonus vs plain `12 kg` | (12000, –, 2000) | (12000, –, –) | N — bonus |
| **`4x14 g` vs `6x14 g`** (revision 1's case 1) | (14, 4, –) | (14, 6, –) | **N — pack_count** |

Case 1 fell through revision 1 because rule 1 read only the weight (14 g = 14 g) and rule 2 only
distinguished multipack from single. Reading the whole tuple closes it: a 4-pouch box and a
6-pouch box are different SKUs at different prices, exactly as a 4.5 kg and a 12 kg bag are.

**`pack_count` null and `pack_count` 1 mean the same thing.** Phase 2 convention 3 stores
`"1 x 85 g"` as `pack_count = 1` while a plain `"85 g"` stores `null`. These are the same
purchasable unit written two ways — treat null and 1 as equal, never as a difference. Marking
these `N` would manufacture false negatives on precisely the cross-shop pairs this project
exists to find.

> **Known data-model ambiguity, flag but do not solve at the keyboard.** Phase 2 convention 6
> stores `"12x85 g"` as `net_weight_g = 85, pack_count = 12` (total 1,020 g) and
> `"6 bucati / 90 g"` as `net_weight_g = 90, pack_count = 6` (total 90 g). Two genuinely
> different products can therefore carry an identical stored tuple. If a pair looks equal on the
> tuple but the titles use these two different forms, press `S` with a note. This is a Phase 2
> representation gap resurfacing, not a judgement you should make in 18 seconds.

### Rule 2 — the formula qualifier differs → `N`

A *formula-defining* qualifier names a distinct SKU. The manufacturer puts it in the product
name and no shop drops it, so a difference — including present on one side and absent on the
other — means different products.

**Formula-defining (a difference → `N`):** life stage (Puppy, Junior, Kitten, Adult, Senior,
Mature, 7+, 8+, 12+) · Sterilised / Sterilizat / Neutered · Light / Weight Control · Sensitive /
Sensible / Digestive · Hypoallergenic · Indoor / Outdoor · Hairball · Dental / Oral · Urinary ·
Joint / Mobility · Skin & Coat.

`Adult` vs `Adult 7+` is a difference. `Medium Adult` vs `Medium Sterilised Adult` is a
difference — this settles revision 1's case 5 (Sterilised), and yes, it belongs here rather than
being a special case of life stage: a sterilised formula is a distinct nutritional SKU for the
same reason a senior formula is.

**Descriptive (a difference → *ignore it*, decide on everything else):** grain free / fără
cereale · monoproteic · natural · premium · complete / completă · hrană uscată / umedă · super
premium · holistic · the shop's own category prefix (`"Hrana uscata pentru caini ..."`).

Shops add and drop these freely — Orijen is always grain-free whether or not the title says so.
Treating their presence as a product difference would manufacture false negatives.

If a qualifier is not on either list and you cannot place it in five seconds, press `S`.

### Rule 3 — the breed size differs → `N`

`Mini` vs `Maxi` at the identical bag weight are different formulas (different kibble size,
different nutrient profile), not the same purchasable unit.

**Dosage bands are asymmetric** — this settles revision 1's case 4. A dosage band (`"12-25 kg"`)
is the ANIMAL's weight, never the product's (Phase 2 convention 4):

- **Both sides state a band and the bands differ → `N`.** A dental stick for 12–25 kg dogs is a
  physically different stick from one for 5–10 kg dogs.
- **One side states a band, the other states none → ignore it entirely.** Absence is a shop's
  title-verbosity difference, not a product difference — the same reasoning as rule 5's brand
  provenance.

### Rule 4 — the flavour differs → `N`

`Chicken` and `Salmon` of the identical line, quantity and life stage are different purchasable
units.

**Cross-language flavour words are the SAME flavour**, not different ones — `Salmon`/`Somon`,
`Turkey`/`Curcan`, `Chicken`/`Pui`. Phase 2's `flavour.py` table is the reference for which EN/RO
pairs are one flavour written two ways.

**Variety and mixed packs are their own flavour value** — this settles revision 1's case 2. If a
title says `variety`, `mix`, `mixt`, `selection`, `multi-flavour` or lists three or more flavours,
read its flavour as `MIXED`:

- `MIXED` vs any single flavour → **`N`** (a variety box is not the salmon box)
- `MIXED` vs `MIXED`, same line and same quantity tuple → decide normally, usually **`M`**

**Flavour stated on one side only, neither being a variety pack → `S`.** Do not read a missing
flavour as "matches anything."

### Rule 5 — same product, different brand string → `M`

When the shops' brand fields differ only because one shows the real manufacturer and the other a
distributor or private-label code for the identical physical product (`"Dolina Noteci"` vs the
`"Piper"` house brand it manufactures), that is still the same purchasable unit. The brand-FIELD
mismatch is a data-provenance artifact, not a product difference.

Judge this from the **title and packaging description**, not the structured field alone: if the
title text, quantity, flavour and line name all point to the same physical product, a disagreeing
brand field does not change the answer.

### Rule 6 — no quantity stated on one side → `S`

If either title gives no parseable net weight or volume, the pair cannot be tested against rule 1.
Do not guess that "no weight stated" means either "assume it matches" or "assume it doesn't."

### Rule 7 — reformulation, same line and same quantity → `M`, flagged

A line that has visibly been reformulated (a "New Formula" marker, a generation number) but keeps
the same line name and quantity tuple is still `M` — a price-comparison engine should still
compare them — but press the flag key so Phase 3's error analysis can count this shape separately
from a clean match.

### Rule 8 — uncertain for more than ~15 seconds → `S`

If the ladder doesn't resolve it and a confident answer isn't reachable quickly, skip. A guess
recorded as `M` or `N` is worse than an honest `S`: it corrupts the dataset silently, where an `S`
is visible and counted.

---

## Scope of the first annotation round

**Food, treats and litter only. Accessories and toys are excluded** — revision 1's case 3,
decided rather than deferred.

The reasoning is the project's own: the matching problem CLAUDE.md describes, and the one the
fine-tuned model has to earn its keep on, is the food-title problem — brand, line, quantity,
flavour, breed size, life stage, with same-line-different-capacity as the dominant hard negative.
Accessories have a different title grammar, no meaningful quantity semantics, and a different
notion of "purchasable unit" entirely (dimensions, colour, set size). Mixing them into one dataset
splits the model's capacity across two unrelated problems, splits the annotator's scarce hours the
same way, and leaves CLAUDE.md §7's required per-category breakdown with a category whose rules
were never written down.

By the STEP 3 category signal, this scopes the queue to **food 8,601 + litter 202 = 8,803 of the
10,532 rows (83.6%)**, and drops accessory 1,550 + toy 177 + unknown 2. Litter stays in because a
litter bag has real mass semantics and behaves exactly like food under rule 1.

This is a deliberate, recorded scoping decision, not a silent omission. If accessory matching is
wanted later it gets its own conventions file and its own annotation round — it does not get
folded into this one.

**Accessory bundles** (a 2-bowl set vs 1 bowl, a leash+collar set vs a leash) therefore fall out
of scope with the rest of case 3. Within food and treats, a "bundle" is a multipack and rule 1's
`pack_count` already decides it.

## Data defects are not hard cases

Revision 1's case 6: pentruanimale.ro groups size variants under one product URL (CLAUDE.md's own
structural note, hit again while building the retrieval eval set — DECISIONS.md ADR-0028's
`_resolve_variant`). A listing whose title-stated weight doesn't match what its page actually
sells is a **data problem**, not a matching judgement.

**The annotator should never meet one.** The queue builder is to detect and exclude any listing
whose title-stated quantity cannot be resolved to a single variant on its own page, and report
how many it excluded. If one reaches the tool anyway, press `S` with a one-line note and move on —
do not diagnose it at the keyboard.

## Worked examples, drawn from real titles

| Left | Right | Answer | Rule |
|---|---|---|---|
| `Brit Premium by Nature Adult L 15 kg` | `BRIT Premium By Nature Adult Large Breed, L, ... 15kg` | M | tuple equal, qualifiers equal, breed size equal |
| `Royal Canin Medium Adult 4 kg` | `ROYAL CANIN Medium Adult 7+, ... senior, 4kg` | N | rule 2 — `7+` qualifier |
| `Royal Canin Medium Adult 15 kg` | `Royal Canin Medium Adult 4 kg` | N | rule 1 — weight |
| `Royal Canin Medium Adult 4 kg` | `ROYAL CANIN Medium Sterilised Adult, 4 kg` | N | rule 2 — Sterilised |
| `Calibra Cat Life Pouch Sterilised Multipack 12x85 g` | `Calibra Cat Life Pouch Sterilised 85 g` | N | rule 1 — pack_count 12 vs 1 |
| `Churu Chicken 4x14 g` | `Churu Chicken 6x14 g` | N | rule 1 — pack_count 4 vs 6 |
| `Churu Variety Pack 20x14 g` | `Churu Chicken 20x14 g` | N | rule 4 — MIXED vs single flavour |
| `Orijen Original Dog Adult Mini 1.8 kg` | `Orijen Original Dog Adult Mini fara cereale 1,8 kg` | M | rule 2 — "fara cereale" is descriptive |
| `Bete dentare pentru caini 12-25 kg, 7 buc` | `Bete dentare pentru caini 5-10 kg, 7 buc` | N | rule 3 — dosage bands both stated, differ |
| `Bete dentare Medium 7 buc` | `Bete dentare pentru caini talie medie 12-25 kg, 7 buc` | M | rule 3 — band on one side only, ignored |
| `Hrana umeda caini Dolina Noteci Premium Vanat 800 g` | same product, shop shows `Piper` as brand | M | rule 5 — brand provenance |

## Status

Revision 2, 2026-09-15 — written by the architect session before any labelling, replacing
revision 1's six deferred `S` defaults with decisions and consolidating revision 1's rules 1–3
into a single quantity-tuple rule.

Revise this file, not the tool's code, when real labelling surfaces a case these rules don't
resolve — the same discipline Phase 2's conventions followed (ADR-0026 → ADR-0027 added
conventions 6–7 from real labelling gaps, never silently absorbed into the extractor without
being written down first).
