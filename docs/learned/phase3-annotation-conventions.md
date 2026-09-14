# Phase 3 annotation conventions — read this before opening the annotation tool

Written **before** the tool exists, not derived from labelling — Phase 2's own lesson
(`docs/learned/phase2-gate-sample-README.md`) is that conventions invented mid-labelling produce a
dataset that disagrees with itself. If a real pair doesn't fit cleanly under one of the rules
below, that is new information about the problem, not a reason to guess — flag it (`S`) and it
gets folded into a future revision of this file, the same way Phase 2's conventions grew from 5 to
7 as real data revealed gaps.

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

## The rules

Applied in this order — the first rule that fires decides the pair; if none fires, decide on the
operational question directly, and flag (`S`, with a one-line note) if that's genuinely unclear
within about 15 seconds.

1. **Different net weight or volume → N, always.** Even when everything else matches exactly. A
   4.5 kg and a 12 kg bag of the same formula are never the same purchasable unit — no exception,
   including "close enough" weights (1.5 kg vs 1.4 kg is still N). This is CLAUDE.md's own
   dominant hard-negative class and the rule with zero tolerance for judgement calls.
2. **Multipack vs single unit → N.** `"12x85 g"` (a box of 12 pouches) is not the same purchasable
   unit as a single `"85 g"` pouch, even though they're the identical formula at the identical
   per-unit weight — the SKU a shop actually sells and the price a shopper actually pays differ.
3. **Bonus pack vs plain pack → N.** `"12+2 kg"` (a promotional bonus-weight pack) is not the same
   purchasable unit as a plain `"12 kg"` bag of the same formula — same reasoning as convention 2
   of Phase 2's own schema (ADR-0026): the bonus pack is a different, larger total-content SKU.
4. **Different flavour or protein source → N.** `"Chicken"` and `"Salmon"` variants of the
   identical line, weight and life stage are different purchasable units. Cross-language flavour
   words count as the SAME flavour, not different ones (`"Salmon"`/`"Somon"`, `"Turkey"`/
   `"Curcan"` — Phase 2's own `flavour.py` table is the reference for which EN/RO pairs are one
   flavour written two ways).
5. **Different breed size, same weight → N.** `"Mini"` and `"Maxi"` formulas of the same line, at
   the identical bag weight, are different formulas (different kibble size and nutrient profile
   for different dog sizes) — not the same purchasable unit just because the bag weighs the same.
6. **Different life stage → N.** `"Puppy"`/`"Junior"` vs `"Adult"` vs `"Senior"` formulas of the
   same line are nutritionally different products, not the same purchasable unit. `"Adult"` vs
   `"Adult 7+"`/`"Senior"` counts as a life-stage difference too (a real false-collision class the
   proxy key hit this session, DECISIONS.md ADR-0028) — a life-stage QUALIFIER changes the
   product even when the base word (`"Adult"`) is shared.
7. **Same product, different brand string (distributor code vs manufacturer) → M.** When the
   shop's own structured brand field differs only because one shop shows the real manufacturer
   and the other shows a distributor/private-label code for the identical physical product (e.g.
   `"Dolina Noteci"` vs the `"Piper"` house brand it manufactures), that is still the same
   purchasable unit — the brand-FIELD mismatch is a data-provenance artifact, not a product
   difference. Judge this from the **title and packaging description**, not the structured field
   alone: if the title text, weight, flavour and line name all point to the same physical product,
   the brand field disagreeing doesn't change the answer.
8. **One side states no weight at all → S.** If either title gives no parseable net weight/volume,
   the pair cannot be resolved against rule 1 — don't guess that "no weight stated" means "assume
   it matches" or "assume it doesn't." Flag it.
9. **Consecutive generation / reformulation, same line, same weight → M, flagged.** A line that
   has visibly been reformulated (a "New Formula" marker, a revised ingredient list implied by the
   title, a generation number) but keeps the same line name and weight is still M — a
   price-comparison engine should still compare them — but flag it (`S`-adjacent: mark `M` with
   the flag key, not skip) so Phase 3's error analysis can see how often this shape occurs
   separately from a clean match.
10. **Uncertain for more than ~15 seconds → S.** If the rules above don't resolve it and a
    confident answer isn't reachable quickly, stop and skip — per CLAUDE.md §7, 200 pairs/hour
    depends on this discipline. A guess recorded as `M` or `N` is worse than an honest `S`: it
    corrupts the dataset silently, where an `S` is visible and honest.

## Cases the data already shows these rules don't fully cover

Found by re-reading this session's own real title pairs (`docs/learned/q3-verification.md`, the
proxy-key collision sample, and the STEP 5 gate mismatches) against the rules above — not
hypothesised. **None of these get a new firm rule here** — that would be inventing a convention
mid-session with the same risk Phase 2's own lesson warns about. Each defaults to `S` until the
annotator's first real pass surfaces enough of them to decide with real cases in hand, exactly the
process that took Phase 2's conventions from 5 to 7.

- **Pack-count vs total-weight ambiguity beyond rule 2.** `"4x14g"` (a 4-pouch box) vs a
  hypothetical single `"56g"` listing of the identical total content: rule 2 says N (multipack vs
  single unit) — but what about `"4x14g"` vs `"6x14g"` (same per-pouch weight, different box
  size)? Rule 1 (different net weight — if net_weight_g is read as the PER-UNIT weight, 14g=14g,
  so rule 1 doesn't fire) and rule 2 (both are multipacks, so it doesn't cleanly fire either) both
  go quiet. Default: `S`, flagged — this is a real gap in "net weight" as the single distinguishing
  number when pack_count also varies.
- **Variety/mixed-flavour packs.** A box explicitly containing multiple flavours (`"Churu Variety
  Pack"`-shaped titles) against a single-flavour listing of one of the flavours it contains. Rule
  4 (different flavour) doesn't obviously apply since the variety pack isn't "a different flavour"
  so much as "not one flavour." Default: `S`.
- **Accessory bundles vs single items** (a set of 2 bowls vs 1 bowl, a leash+collar set vs a
  leash alone). The weight-centric rules 1-3 are written for food/treats; accessories need their
  own reading of "purchasable unit" that these rules don't spell out. Default: `S`, and worth
  noting whether accessories should even be in the first annotation queue at all (STEP 6) given
  this gap — a decision for the user, not assumed here.
- **A dosage band standing in for breed size.** `"12-25 kg"` (the ANIMAL's weight, Phase 2
  convention 4) sometimes functions like a breed-size signal in context (a treat sized for
  medium-large dogs) without being `breed_size_code`. Rule 5 is written in terms of
  `breed_size_code`; a dosage-band difference at otherwise-identical weight/flavour isn't
  explicitly covered. Default: `S`.
- **Sterilised/neutered-specific formulas.** `"Sterilised"`/`"Sterilizat"` functions like a
  fourth life-stage-adjacent qualifier in real titles (seen this session, e.g. `"ROYAL CANIN
  Medium Sterilised Adult"`) — arguably falls under rule 6 (different life stage) by extension,
  but the rule as written names Puppy/Junior/Adult/Senior only. Treated as covered by rule 6 (a
  sterilised formula is nutritionally distinct, same reasoning) — noted here so a labeller doesn't
  wonder whether it's an exception.
- **A shop's own variant-grouped listing that wasn't fully expanded.** pentruanimale.ro groups
  size variants under one product URL (CLAUDE.md's own documented structural note, confirmed
  again this session building the retrieval eval set — see DECISIONS.md ADR-0028); if the queue
  ever surfaces a listing whose title's stated weight doesn't match what the page actually shows
  for that SKU, that's a **data problem**, not a matching judgement — flag it as `S` with a note,
  don't try to resolve it as if it were an ordinary hard case.

## Worked examples, drawn from real titles seen this session

| Petmax / Animax | Pentruanimale / other | Answer | Rule |
|---|---|---|---|
| `Brit Premium by Nature Adult L 15 kg` | `BRIT Premium By Nature Adult Large Breed, L, ... 15kg` | M | same weight, brand, breed size, life stage |
| `Royal Canin Medium Adult 4 kg` | `ROYAL CANIN Medium Adult 7+, ... senior, 4kg` | N | rule 6 — life-stage qualifier (7+/senior) differs |
| `Brit Premium by Nature Adult XL 3 kg` | `Brit Premium by Nature Junior XL 3 kg` | N | rule 6 — Adult vs Junior |
| `Hrana umeda caini, Calibra Dog Premium Line Senior & Light 12+2 kg` | `CALIBRA Premium Line Senior & Light, ... 12kg` (no bonus) | N | rule 3 — bonus pack vs plain |
| `Calibra Cat Life Pouch Sterilised Multipack 12x85 g` | (hypothetical) `Calibra Cat Life Pouch Sterilised 85 g` | N | rule 2 — multipack vs single |
| `Hrana umeda pentru caini Dolina Noteci Premium Vanat 800gr` | (same physical product, shop shows `Piper` as displayed brand) | M | rule 7 — brand-field provenance differs, product doesn't |

## Status

Written 2026-09-15, before the annotation tool (STEP 5) or the queue (STEP 6). Revise this file,
not the tool's own code, when real labelling surfaces a case the rules above don't resolve —
same discipline Phase 2's conventions followed (ADR-0026 → ADR-0027 added conventions 6-7 from
real labelling gaps, never silently absorbed into the extractor without being written down first).
