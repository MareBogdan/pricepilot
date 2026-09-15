"""Phase 3 finding 4 (2026-09-15 session, reference labelling pass) — a species signal (dog / cat),
the most basic blocking dimension in pet food and the one field this project's schema never had:
`category` (food/accessory/litter/toy) says nothing about which animal a food product is FOR, and
4 of the 100-pair pilot labelling slice (positions 8, 14, 39, 72) were cross-species pairs the
matching pipeline had no way to rule out on its own.

Same pattern as `category.py`: a structured signal where a source publishes one, a checked
title-keyword vocabulary otherwise — never guessed from an unvalidated word list.

- `petmax_ro` — the URL path segment already used for `category` also carries species
  unambiguously: every `-caini`/`-pisici` suffixed segment names the animal directly; the one
  segment that doesn't (`asternut-litiera-nisip-silicat`, litter) is resolved by the litter rule
  below instead, not guessed from the URL.
- `animax_ro` — `raw_payload["product_type"]`, the same structured field `category.py` already
  uses, names the animal in most of its values directly (`"...pentru caini"`/`"...pentru
  pisici"`/`"...pentru catei"`/`"...pentru pisicute"`).
- **Litter is cat-only in this catalogue, checked, not assumed**: every in-scope `category="litter"`
  row was inspected this session and every one is cat litter (nisip/așternut for a litter tray) —
  this catalogue carries no dog litter product at all. `category == "litter"` therefore resolves
  to `"cat"` directly, before any per-source signal is consulted, the same kind of evidence-backed
  structural default `category.py` already uses for pentruanimale's "nothing fired -> food".
- Title-keyword fallback (`pentruanimale_ro`, which — like `category` — has no structured species
  field at all in `raw_payload`, only `ean`/`brand`; and the rare petmax/animax row whose
  structured signal doesn't resolve): checked against the full in-scope population before
  trusting, not guessed. Two real false-positive classes were found and excluded this way:
  1. **`"canin"` (bare stem) collides with the brand name "Royal Canin"** on cat products
     ("Royal Canin Feline Sterilised...") — checked directly (282 titles initially flagged as
     "both dog and cat" collapsed to this one cause). The dog-word list uses `"canine"` (the
     word Hill's actually writes for its own dog line, "Hill's SP **Canine**") instead, which does
     not collide with "Canin" (no trailing e in the brand spelling in this data).
  2. English `"dog"`/`"cat"` loanwords appear in a real, checked slice of titles
     ("Advance **Dog** Adult Sensitive...", "NATURES PROTECTION Superior Care White **Dogs**...")
     that carry no Romanian species word at all — added as their own alternatives, not a guess.
  A title carrying BOTH a dog word and a cat word (a genuine dual-species product, e.g. "supliment
  pentru articulatii câini si pisici") or NEITHER (rawhide bones/dental chews with no species word
  in the title at all, e.g. "Os Presat Trixie 22 cm, 230 g") resolves to `None` — an honest gap,
  not guessed either way, the same discipline `category.py`'s own `None` return uses.

**Checked against the full population, this session**: title-keyword fallback alone left 250 of
8,803 in-scope rows unresolved before the "canine"/English-loanword/litter fixes; 124 after
(1.4%), concentrated in exactly the two classes named above (dog-only accessories/dental chews
with no species word: ~120 pentruanimale rows; genuine dual-species products: a small remainder).
"""

from __future__ import annotations

import re
from typing import Any

from pricepilot.overlap import strip_diacritics

# petmax_ro: same URL path segment category.py already reads, mapped to species instead of
# category. The litter segment carries no species information by itself (resolved by the
# category=="litter" rule in classify_species below, not here).
PETMAX_URL_SPECIES: dict[str, str] = {
    "hrana-uscata-caini": "dog",
    "hrana-umeda-caini": "dog",
    "recompense-delicioase-caini": "dog",
    "accesorii-caini": "dog",
    "igiena-si-ingrijire-caini": "dog",
    "jucarii-caini": "dog",
    "hrana-uscata-pisici": "cat",
    "hrana-umeda-pisici": "cat",
    "recompense-delicioase-pisici": "cat",
    "accesorii-pisici": "cat",
    "igiena-si-ingrijire-pisici": "cat",
}
_PETMAX_URL_SEGMENT = re.compile(r"petmax\.ro/([^/]+)/")

# animax_ro: same raw_payload["product_type"] field category.py already uses.
ANIMAX_PRODUCT_TYPE_SPECIES: dict[str, str] = {
    "hrana umeda pentru pisici": "cat",
    "hrana uscata pentru caini": "dog",
    "recompense pentru caini": "dog",
    "hrana uscata pentru pisici": "cat",
    "hrana umeda pentru caini": "dog",
    "recompense pentru pisici": "cat",
    "hrana uscata pentru catei": "dog",
    "hrana uscata pentru pisicute": "cat",
    "hrana semi-umeda pentru caini": "dog",
    "hrana semi-umeda pentru pisici": "cat",
    "hrana umeda pentru pisicute": "cat",
    "salam pentru caini": "dog",
    "jucarie pentru pisici": "cat",
    "jucarie pentru caini": "dog",
    "sampon pentru caini": "dog",
    "zgarda pentru caini": "dog",
}

# Title-text fallback. Checked against the full in-scope population before trusting (module
# docstring above): "canine" not "canin" (avoids the Royal Canin brand-name collision), plus the
# English loanwords "dog"/"cat" (bare and plural) that a real, checked slice of titles use with no
# Romanian species word at all. `pisic\w*` is a stem match (catches "pisica"/"pisici"/"pisicii"/
# "pisicilor"/"pisicuta" etc. in one pattern) — checked for collisions against the full population,
# none found.
_DOG_WORDS = re.compile(r"\b(caini|caine|catei|catelus\w*|canine|dogs?|puppy)\b")
_CAT_WORDS = re.compile(r"\b(pisic\w*|felin\w*|cats?|kitten)\b")


def _from_title(title: str) -> str | None:
    folded = strip_diacritics(title.lower())
    is_dog = _DOG_WORDS.search(folded) is not None
    is_cat = _CAT_WORDS.search(folded) is not None
    if is_dog and not is_cat:
        return "dog"
    if is_cat and not is_dog:
        return "cat"
    return None  # neither, or a genuine dual-species title -- not guessed either way


def classify_species(
    source: str,
    url: str,
    raw_payload: dict[str, Any] | None,
    title: str,
    category: str | None,
) -> str | None:
    """`"dog"` / `"cat"`, or `None` when nothing — structured signal or title keyword —
    identifies it (an honest gap, not guessed). Takes `category` because litter is a
    cat-only product class in this catalogue (checked, module docstring above) and that
    structural fact resolves species more reliably than any per-source signal below it."""
    if category == "litter":
        return "cat"
    if source == "petmax_ro":
        match = _PETMAX_URL_SEGMENT.search(url)
        if match and (mapped := PETMAX_URL_SPECIES.get(match.group(1))):
            return mapped
        return _from_title(title)
    if source == "animax_ro":
        product_type = (raw_payload or {}).get("product_type")
        if isinstance(product_type, str) and (
            mapped := ANIMAX_PRODUCT_TYPE_SPECIES.get(product_type.strip().lower())
        ):
            return mapped
        return _from_title(title)
    # pentruanimale_ro (or any future source with no structured species field): title only.
    return _from_title(title)


__all__ = ["classify_species"]
