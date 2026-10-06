"""Phase 5 s3b: deterministic attribute-consistency guard on cross-encoder matches (ADR-0041).

The cross-encoder returns a similarity score; it can still say "same product" for two listings
that `docs/learned/phase3-annotation-conventions.md` defines as different purchasable units (a
litter bag and a kitten-food bag from the same brand at the same weight). A wrong match feeds a
wrong competitor price into the pricing decision, so the check is Python that runs after the model
and before anything is persisted -- the same rule the margin floor follows (CLAUDE.md §6.2).

A pair is REJECTED only on a conflict the conventions call unambiguous; missing information never
rejects (an unknown category, no flavour on one side, no stage on both sides all pass -- Rule 5:
"flavour stated on one side only" is the annotator's `S`, not an `N`).

  * category   -- our six mock-store categories mapped onto the competitor taxonomy
                  (`normalize.category`: food / accessory / litter / toy). Conventions: Rule 0 +
                  Scope (food, treat and litter are the matched universe; a litter bag and a food
                  bag are never the same unit).
  * life stage -- Rule 3 lists life stage as formula-defining. Both sides stated and different ->
                  reject. One side stated and it is not plain "adult" while the other states none ->
                  reject: Kitten / Puppy / Junior / Senior (and an "Adult 7+" age band) each name a
                  distinct SKU that no shop drops from the product name. Plain "adult" is the
                  unmarked default stage, so adult-vs-silent passes -- narrower than Rule 3 on
                  purpose, because a missed match costs a link while a wrong match costs a price.
  * flavour    -- Rule 5. Both sides state a flavour and they differ -> reject. The extractor
                  already folds EN/RO synonyms (beef/vita) into one value.

Why the life stage reads the TITLE as well as `norm_listings.life_stage`: the extractor's regex
(`normalize.attributes._LIFE_STAGE`) knows puppy/junior/adult/senior but not "kitten", so every
Kitten listing stores `life_stage = NULL`. The guard recovers that marker from the title; it does
not change the frozen extraction layer.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pricepilot.overlap import strip_diacritics

# Our mock-store category -> the competitor `norm_listings.category` values it may legitimately
# match. Treats map to "food" (petmax files "recompense" under food); grooming maps to "accessory"
# (petmax files "igiena-si-ingrijire" under accessory); accessories may also be filed as "toy".
CATEGORY_COMPATIBLE: Mapping[str, frozenset[str]] = {
    "dry_food": frozenset({"food"}),
    "wet_food": frozenset({"food"}),
    "treats": frozenset({"food"}),
    "litter": frozenset({"litter"}),
    "grooming": frozenset({"accessory"}),
    "accessories": frozenset({"accessory", "toy"}),
}

# Stages the extractor does not produce but the conventions name. "pisoi" is Romanian for kitten.
_TITLE_STAGE = re.compile(r"\b(kitten|pisoi|puppy|junior|senior)\b")
_DEFAULT_STAGE = "adult"


@dataclass(frozen=True)
class ListingFacts:
    """What the guard reads about one side of a pair. `category` is already in the taxonomy of its
    own side (see `CATEGORY_COMPATIBLE`)."""

    category: str | None
    title: str
    life_stage: str | None
    flavour: str | None


def life_stage_marker(title: str, extracted: str | None) -> str | None:
    """The stage this listing names: the extractor's value, else a stage word from the title
    (the extractor has no 'kitten'). None = the listing names no stage."""
    if extracted:
        return extracted.lower()
    found = _TITLE_STAGE.search(strip_diacritics(title.lower()))
    if found is None:
        return None
    return "kitten" if found.group(1) == "pisoi" else found.group(1)


def conflicts(our: ListingFacts, competitor: ListingFacts) -> list[str]:
    """Reasons the two listings cannot be the same purchasable product; empty = consistent."""
    reasons: list[str] = []

    allowed = CATEGORY_COMPATIBLE.get(our.category or "")
    if (
        allowed is not None
        and competitor.category is not None
        and competitor.category not in allowed
    ):
        reasons.append(f"category_conflict:{our.category}!={competitor.category}")

    ours = life_stage_marker(our.title, our.life_stage)
    theirs = life_stage_marker(competitor.title, competitor.life_stage)
    if ours is not None and theirs is not None:
        if ours != theirs:
            reasons.append(f"life_stage_conflict:{ours}!={theirs}")
    elif (ours or theirs) not in (None, _DEFAULT_STAGE):
        reasons.append(f"life_stage_conflict:{ours or 'none'}!={theirs or 'none'}")

    if our.flavour and competitor.flavour and our.flavour.lower() != competitor.flavour.lower():
        reasons.append(f"flavour_conflict:{our.flavour}!={competitor.flavour}")

    return reasons
