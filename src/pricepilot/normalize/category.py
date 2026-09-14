"""Phase 3 STEP 3 — a cheap category signal (food / accessory / litter / toy), checked against
the full population before trusting, same discipline as ADR-0025/ADR-0027.

**Why this exists.** Two real false-positive classes surfaced building Phase 2 (STATE.md's own
"What Phase 3 will need" list): a food product line genuinely named `"Sheba Mini"` colliding with
an accessory's own `"Mini"` dimension; `"Servetele umede"` (wet WIPES, an accessory) colliding
with wet FOOD. Neither `brand` nor `product_line` alone can rule these out — a category filter
run before candidate retrieval can, cheaply, for the cost of one more SQL predicate.

**Not a title-text guess where a structured signal already exists.** Two of the three sources
publish their own category classification directly:

- `petmax_ro` — the URL path segment IS the shop's own category
  (`petmax.ro/hrana-uscata-caini/...`) — checked against the full population before trusting:
  12 distinct segments, every one unambiguous (`docs/SOURCES.md`-style verification, counts in
  DECISIONS.md).
- `animax_ro` — `raw_payload["product_type"]`, the shop's own structured field (already the
  regulated-product detector's second signal, ADR-0025) — 29 distinct values, checked the same
  way.

Only `pentruanimale_ro` has no structured category field at all (its VTEX `categories`/
`categoryId` is captured going forward only, per ADR-0025 — cannot be backfilled onto rows
already collected). For it, and as a fallback for the rare row an unmapped URL segment or
`product_type` value slips through, a small title-keyword vocabulary is used — checked against
the full population before trusting, not guessed: `nisip`/`litiera` (litter), `jucarie` (toy),
and the exact accessory-context vocabulary Phase 2's `attributes.py::extract_breed_size` already
validated (`zgarda`/`lesa`/`cusca`/`transport`, plus the first-word-anchored `ham` check) — reused
here, not re-derived, because it was already checked against the full population for a different
purpose and the underlying words mean the same thing in this context.

**Found and worth recording**: `pentruanimale_ro`'s entire in-scope, collected catalogue (4,023
distinct titles, checked this session) carries **zero** hits for any of `nisip`/`litiera`/
`jucarie`/`zgarda`/`lesa`/`cusca`/`ham`(anchored)/`transport` — the source's collected categories
are food/treats only. `categorize()` correctly defaults such rows to `"food"`, and that default
is evidence-backed for this source, not a guess.
"""

from __future__ import annotations

import re
from typing import Any

from pricepilot.overlap import strip_diacritics

# petmax_ro: the URL path segment is the shop's own category, verified against the full
# population (12 distinct segments, this session) before trusting. Every segment maps
# unambiguously to one of the four canonical values.
PETMAX_URL_CATEGORY: dict[str, str] = {
    "hrana-uscata-caini": "food",
    "hrana-uscata-pisici": "food",
    "hrana-umeda-caini": "food",
    "hrana-umeda-pisici": "food",
    "recompense-delicioase-caini": "food",
    "recompense-delicioase-pisici": "food",
    "accesorii-caini": "accessory",
    "accesorii-pisici": "accessory",
    "igiena-si-ingrijire-caini": "accessory",
    "igiena-si-ingrijire-pisici": "accessory",
    "asternut-litiera-nisip-silicat": "litter",
    # Only 2 rows carry this segment — petmax cross-lists toys under "accesorii-caini" too, and
    # the run-wide dedup (STATE.md, 2026-09-12 session) keeps a product filed under whichever
    # category it's encountered first, so most petmax toys are correctly, if not ideally,
    # classified "accessory" rather than "toy" — a structural quirk of the source, not a bug in
    # this mapping, and not fixed here (would need re-ordering the scraper's own category walk).
    "jucarii-caini": "toy",
}

_PETMAX_URL_SEGMENT = re.compile(r"petmax\.ro/([^/]+)/")

# animax_ro: raw_payload["product_type"], the shop's own structured field — already used as the
# regulated-product detector's second signal (ADR-0025). 29 distinct values, checked against the
# full population before trusting; the empty string ("", 2 rows) is deliberately left unmapped.
ANIMAX_PRODUCT_TYPE: dict[str, str] = {
    "hrana umeda pentru pisici": "food",
    "hrana uscata pentru caini": "food",
    "recompense pentru caini": "food",
    "hrana uscata pentru pisici": "food",
    "hrana umeda pentru caini": "food",
    "recompense pentru pisici": "food",
    "hrana uscata pentru catei": "food",
    "hrana uscata pentru pisicute": "food",
    "hrana semi-umeda pentru caini": "food",
    "hrana semi-umeda pentru pisici": "food",
    "hrana umeda pentru pisicute": "food",
    "salam pentru caini": "food",
    "lapte praf": "food",
    "pesti albi la punga": "food",
    "snack lichid pentru pisici": "food",
    "snack nuggets cu branza": "food",
    "jucarie pentru pisici": "toy",
    "jucarie pentru caini": "toy",
    # "Asternut" (bedding/litter substrate) groups with litter, not accessory — the same grouping
    # petmax's own url segment makes explicit ("asternut-litiera-nisip-silicat" bundles bedding,
    # litter tray and litter sand as one category).
    "nisip pentru litiera": "litter",
    "asternut": "litter",
    "sampon pentru caini": "accessory",
    "ingrijire": "accessory",
    "accesorii racoritoare": "accessory",
    "accesorii": "accessory",
    "sampon pentru caini si pisici": "accessory",
    "sisal pentru pisici": "accessory",
    "zgarda pentru caini": "accessory",
    "imbracaminte": "accessory",
}

# Title-text fallback — used for pentruanimale_ro (no structured category field at all) and as a
# cross-check for the rare row an unmapped url segment/product_type slips through. Every word
# checked against the full in-scope population before trusting (counts in DECISIONS.md): "nisip"/
# "litiera" (litter), "jucarie" (toy). The accessory vocabulary is reused verbatim from
# `attributes.py`'s own already-validated accessory-context guard (zgarda/lesa/cusca/transport,
# plus the first-word-anchored "ham" check) rather than re-derived — same words, same meaning.
_LITTER_WORDS = re.compile(r"\b(nisip|litiera)\b")
_TOY_WORDS = re.compile(r"\bjucarie\w*\b")
_ACCESSORY_WORDS = re.compile(r"\b(zgarda|zgarzi|lesa|lese|cusca|custi|transport)\b")
_HARNESS_PREFIX = re.compile(r"^ham\b")


def _from_title(title: str) -> str | None:
    folded = strip_diacritics(title.lower())
    if _LITTER_WORDS.search(folded):
        return "litter"
    if _TOY_WORDS.search(folded):
        return "toy"
    if _ACCESSORY_WORDS.search(folded) or _HARNESS_PREFIX.match(folded):
        return "accessory"
    return None


def categorize_listing(
    source: str, url: str, raw_payload: dict[str, Any] | None, title: str
) -> str | None:
    """One of `"food"`/`"accessory"`/`"litter"`/`"toy"`, or `None` when nothing — structured
    signal or title keyword — identifies it. `None` is an honest gap for `petmax_ro`/`animax_ro`
    (a genuinely unmapped url segment or `product_type` value with no title keyword hit either —
    worth a fresh check before silently defaulting, not guessed as `"food"`). For
    `pentruanimale_ro`, which carries no structured category field at all, the same "nothing
    fired" outcome resolves to `"food"` instead — that default is evidence-backed for this source
    specifically (this session's own full-population check: zero hits on every non-food keyword
    across its entire collected catalogue), not an assumption extended to the other two."""
    if source == "petmax_ro":
        match = _PETMAX_URL_SEGMENT.search(url)
        if match and (mapped := PETMAX_URL_CATEGORY.get(match.group(1))):
            return mapped
        return _from_title(title)
    if source == "animax_ro":
        product_type = (raw_payload or {}).get("product_type")
        if isinstance(product_type, str) and (
            mapped := ANIMAX_PRODUCT_TYPE.get(product_type.strip().lower())
        ):
            return mapped
        return _from_title(title)
    # pentruanimale_ro (or any future source with no structured category field): the "nothing
    # fired" outcome is itself the evidence-backed food default described above.
    return _from_title(title) or "food"


__all__ = ["categorize_listing"]
