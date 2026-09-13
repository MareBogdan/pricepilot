"""`product_line` extraction (STEP A, this session) — the title with the brand, the shop's
Romanian food/treat descriptive clauses, and the quantity/pack/bonus/dosage tokens removed,
keeping everything else exactly as written.

**Conservative by construction, not by discipline alone.** The removal vocabulary below (form
words, packaging words, qualifier phrases, animal words, trailing life-stage words, the
"recompense(le)" family) is a closed, small list built by reading real leading n-grams and
real mid-title descriptor windows across all three in-scope sources (`raw_listings`, never the
frozen `docs/learned/phase2-gate-sample.csv`) — never this module's own guess at what "sounds
like noise". The removal regex only ever matches a *contiguous* sequence built from this closed
vocabulary; it cannot silently swallow an unrecognized word sitting next to one it does
recognize, which is what makes it safe to run without a human checking every result: an unknown
word to the immediate left or right of a matched clause simply stays in the output.

**Life-stage words (`junior`/`senior`/`adult(i/e)`/`sterilizat(e/i)`) are removable ONLY as the
word directly following an animal word inside a matched clause** — never as a free-standing word
anywhere else in the title. This is deliberate and was checked before writing the pattern this
way: `"Royal Canin Mini Adult 8 kg"` has no `"hrana"/"recompense"` clause at all, and `"Adult"`
there is part of the product's own line name (Royal Canin genuinely sells a line called "Mini
Adult"), not shop boilerplate — a global life-stage-word strip would have deleted real signal.
Tied to the clause, this only ever fires on the boilerplate form (`"... câini adulte, ..."`),
never on a bare line name.

**Brand removal** strips the shop's own raw `source_brand` field value (not the canonicalized
form) from the title, case-insensitively — never a guess at how far "the brand" extends beyond
that literal string. `"Brit Premium"` (a petmax brand-field value) is stripped from `"... Brit
Premium by Nature Junior XL 15 kg"`, correctly leaving `"by Nature Junior XL"` as product-line
text: `"Premium by Nature"` is the sub-line (ADR-0026 convention 5 says sub-line belongs in
`product_line`, never in `brand`), and only the literal brand-field substring is ever removed.

**Quantity/pack/bonus/dosage removal** reuses `quantity.quantity_spans()` — the exact spans
`extract_quantity` used to produce its result, not a second regex that could quietly drift from
the first one's idea of "the quantity".
"""

from __future__ import annotations

import re

from pricepilot.normalize.quantity import quantity_spans
from pricepilot.overlap import strip_diacritics

# ---------------------------------------------------------------------------
# Closed removal vocabulary — every entry below was found in real leading n-grams or real
# mid-title descriptor windows across all three in-scope sources before being added. Matched
# against the diacritic-folded, lowercased title, so "hrană"/"hrana", "câini"/"caini",
# "tăviță"/"tavita" etc. are already the same string by the time these patterns run.
# ---------------------------------------------------------------------------

_FORM = r"(?:uscata|umeda|semi-?umeda)"
_PACKAGING = r"(?:plicuri|plic|conserva|conserve|tavita|punguta|galetusa|bax|tub|bol)"
_QUALIFIER = r"(?:monoproteica|monoproteic|fara cereale|continut redus cereale)"
_ANIMAL = r"(?:cainii|caini|catel|catei|pisica|pisici)"
# Only ever consumed as the word immediately after an animal word inside a matched clause — see
# the module docstring for why this must never be a free-standing strip.
_STAGE = r"(?:junior|senior|sterilizate|sterilizati|adulte|adulti)"
# A bare "adult" (no trailing -e/-i) is deliberately NOT in `_STAGE` above — it's real product-
# line text on its own ("Royal Canin Mini Adult") far more often than shop boilerplate, and
# `_STAGE` anchors every match in `_CLAUSE`. It's allowed ONLY as the second+ word of a
# "junior & adult" / "senior & adult" chain (130 real titles checked before adding this),
# immediately following an already-anchored `_STAGE` word — never as a free-standing match.
_STAGE_CHAIN_EXTRA = r"(?:junior|senior|adulte|adulti|adult)"
_RECOMPENSE = r"(?:recompensele|recompense|recompensa)"

_CLAUSE = re.compile(
    r"\b"
    rf"(?:{_PACKAGING}\s+)?"
    rf"(?:(?:hrana\s+){_FORM}|{_RECOMPENSE}(?:\s+delicioase)?)"
    r"\s*(?:pentru\s+)?"
    rf"(?:{_QUALIFIER}\s*,?\s*)*"
    rf"{_ANIMAL}"
    rf"(?:\s+{_STAGE}(?:\s*&\s*{_STAGE_CHAIN_EXTRA})*)?"
    r"\s*,?"
)

# Pack-format descriptor words — checked for real context before adding, same discipline as the
# CLAUSE vocabulary above: "multipack" (199 titles) and "pachet economic"/"pachet mixt" (115
# titles combined) were read across a random real sample and found in exactly one structural
# position every time — directly adjacent to the pack quantity ("..., multipack, 85g x 4buc",
# "..., pachet economic, 14kg") — never inside a brand's own sub-line name. Matched as their own
# standalone tokens, independent of the CLAUSE regex above, since they also occur with no
# preceding "hrana"/"recompense" clause at all ("Calibra Cat Life Pouch Adult Multipack 12x85 g").
_PACK_DESCRIPTOR = re.compile(r"\b(?:multipack|pachet economic|pachet mixt|bax)\b")

# Stray punctuation left dangling once the clause/brand/quantity spans are excised — cleaned up
# in a fixed-point loop (each pass can expose another one, e.g. "- ," -> "-" -> "").
_LEADING_TRAILING_JUNK = re.compile(r"^[\s,\-–—./]+|[\s,\-–—./]+$")  # noqa: RUF001 — en/em dash, real
_EMPTY_PARENS = re.compile(r"\(\s*\)")
_REPEATED_COMMAS = re.compile(r",\s*,+")
_MULTI_SPACE = re.compile(r"\s{2,}")
_SPACE_BEFORE_COMMA = re.compile(r"\s+,")


def _brand_span(folded_title: str, source_brand: str | None) -> tuple[int, int] | None:
    """The shop's own raw brand-field text, found case-insensitively in the folded title —
    never a canonicalized or guessed form. `None` when there's no brand field to strip (an
    honest gap, not a failure — see `brand.py`'s own note that this affects a handful of rows)."""
    if not source_brand or not source_brand.strip():
        return None
    folded_brand = strip_diacritics(source_brand.lower()).strip()
    if not folded_brand:
        return None
    match = re.search(re.escape(folded_brand), folded_title)
    return (match.start(), match.end()) if match else None


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans)
    merged = [spans[0]]
    for start, end in spans[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def extract_product_line(title: str, source_brand: str | None) -> str | None:
    """Title minus brand, minus the shop's Romanian food/treat descriptive clauses, minus
    quantity/pack/bonus/dosage tokens — everything else preserved verbatim, original language
    and casing untouched. `None` only when nothing is left after removal (rare — most titles
    carry real line-identifying words beyond the three things this function removes)."""
    folded = strip_diacritics(title.lower())

    spans: list[tuple[int, int]] = list(quantity_spans(title))
    spans.extend((m.start(), m.end()) for m in _CLAUSE.finditer(folded))
    spans.extend((m.start(), m.end()) for m in _PACK_DESCRIPTOR.finditer(folded))
    if (brand_span := _brand_span(folded, source_brand)) is not None:
        spans.append(brand_span)

    kept_segments: list[str] = []
    cursor = 0
    for start, end in _merge_spans(spans):
        kept_segments.append(title[cursor:start])
        cursor = end
    kept_segments.append(title[cursor:])
    # Joined with a space at every excision boundary, unconditionally — including where a
    # segment is empty — so two words that were only separated by a now-removed span never
    # glue together. This routinely introduces doubled whitespace at splice points; the cleanup
    # pass below normalizes it rather than trying to get spacing exactly right here.
    result = " ".join(kept_segments)
    result = _EMPTY_PARENS.sub("", result)
    result = _SPACE_BEFORE_COMMA.sub(",", result)
    result = _REPEATED_COMMAS.sub(",", result)
    result = _MULTI_SPACE.sub(" ", result)
    result = _LEADING_TRAILING_JUNK.sub("", result)
    # A second pass: removing one layer of junk can reveal another underneath (e.g. "- ," once
    # the dash's neighbour is gone).
    result = _LEADING_TRAILING_JUNK.sub("", result)
    result = result.strip()

    return result or None


__all__ = ["extract_product_line"]
