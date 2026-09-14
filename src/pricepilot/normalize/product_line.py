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

**Brand removal strips only `brand.brand_span_text()`'s manufacturer-only text, never the shop's
whole raw `source_brand` field.** An earlier version of this function stripped the *entire* raw
field, which for petmax's `"Brit Premium"` cut `"Premium"` out along with the brand — leaving
`"by Nature Junior XL"` where the real product line is `"Premium by Nature Junior XL"`, and
worse, making the *same* product non-comparable across shops: pentruanimale's raw brand field for
the identical product is the bare `"BRIT"`, so its product_line kept `"Premium By Nature Adult
Large Breed"` — two shops, one product, two product_lines that share barely a single token.
`brand_span_text()` fixes this at the source (see `brand.py`'s own docstring): for a
marketing-suffix brand string it returns only the retained manufacturer prefix (`"brit"`, not
`"brit premium"`), so the suffix stays in the title as real sub-line text; for an alias-table
entry (`"Affinity Advance"` -> `"advance"`, where the whole raw field names the manufacturer with
no separate sub-line) it returns the whole normalized string, same as before. Diacritic-folded
here (never inside `brand.py`, which preserves diacritics for its own canonical output) purely so
the search matches this module's already diacritic-folded title.

**Quantity/pack/bonus/dosage removal** reuses `quantity.quantity_spans()` — the exact spans
`extract_quantity` used to produce its result, not a second regex that could quietly drift from
the first one's idea of "the quantity".
"""

from __future__ import annotations

import re

from pricepilot.normalize.brand import brand_span_text
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
# in a fixed-point loop (each pass can expose another one, e.g. "- ," -> "-" -> ""). Includes "("
# alongside the dash/slash/dot forms already here: a stray trailing open-paren is the same class
# of leftover as a stray trailing dash, just from a parenthetical whose closing half survived.
_LEADING_TRAILING_JUNK = re.compile(r"^[\s,\-–—./(]+|[\s,\-–—./(]+$")  # noqa: RUF001 — en/em dash, real
_EMPTY_PARENS = re.compile(r"\(\s*\)")
_REPEATED_COMMAS = re.compile(r",\s*,+")
_MULTI_SPACE = re.compile(r"\s{2,}")
_SPACE_BEFORE_COMMA = re.compile(r"\s+,")

# ---------------------------------------------------------------------------
# Dangling-token guard (STEP 1b, 2026-09-14) — general, not a per-case patch. Found via a real
# accessory title where excising a quantity span ("2 l") left its own qualifier ("diametru")
# stranded mid-string with nothing left to modify: "Bol ..., inox, diametru 2 l, 25 cm, Negru
# Agility" -> (pre-guard) "Bol ..., inox, diametru, 25 cm, Negru" — "diametru" pointing at
# nothing. This is a structural risk in *any* removal rule that can excise a quantity/clause span
# adjacent to a connective or qualifier word, not just this one case, so the fix is a closed-
# vocabulary post-step that runs after every removal, not a fix to the quantity/diametru pair
# specifically.
_DANGLING_WORDS = frozenset({"cu", "si", "de", "din", "diametru", "and", "with"})
_EDGE_PUNCT = ",.-–—/()"  # noqa: RUF001 — en/em dash, real


def _brand_span(folded_title: str, source_brand: str | None) -> tuple[int, int] | None:
    """`brand.brand_span_text()`'s manufacturer-only text, found case-insensitively in the
    folded title — never the shop's whole raw brand-field string (see the module docstring for
    why that was wrong). `None` when there's no brand field to strip (an honest gap, not a
    failure — see `brand.py`'s own note that this affects a handful of rows)."""
    span_text = brand_span_text(source_brand)
    if not span_text:
        return None
    folded_brand = strip_diacritics(span_text).strip()
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


def _folded_word(word: str) -> str:
    return strip_diacritics(word.lower()).strip().strip(_EDGE_PUNCT).strip()


def _is_dangling(segment: str) -> bool:
    """True only when the whole (trimmed) segment folds down to exactly one dangling word —
    never fires on a segment that happens to *contain* one ("cu miel" stays; a bare "cu" from a
    now-gone "cu miel" doesn't)."""
    return _folded_word(segment) in _DANGLING_WORDS


def _drop_dangling_segments(result: str) -> str:
    """Comma-delimited segments reduced to nothing but a single dangling word are dropped
    wholesale — this is what catches a qualifier stranded *mid-string* once its quantity is gone
    (`"..., diametru, 25 cm, ..."` -> `"..., 25 cm, ..."`), not just at the string's own edges."""
    return ",".join(seg for seg in result.split(",") if not _is_dangling(seg))


def _strip_dangling_edges(result: str) -> str:
    """The string's own first/last whitespace-delimited token, dropped if it folds to a bare
    connective or qualifier with nothing left to modify. Checked token-by-token, never
    character-by-character, so this can't nibble into a real word."""
    words = result.split()
    while words and _folded_word(words[0]) in _DANGLING_WORDS:
        words = words[1:]
    while words and _folded_word(words[-1]) in _DANGLING_WORDS:
        words = words[:-1]
    return " ".join(words)


def _clean_punctuation(result: str) -> str:
    result = _EMPTY_PARENS.sub("", result)
    result = _SPACE_BEFORE_COMMA.sub(",", result)
    result = _REPEATED_COMMAS.sub(",", result)
    result = _MULTI_SPACE.sub(" ", result)
    result = _LEADING_TRAILING_JUNK.sub("", result)
    return _LEADING_TRAILING_JUNK.sub("", result)  # second pass: one layer can reveal another


def _strip_dangling_tokens(result: str) -> str:
    """The single validated post-step (STEP 1b): runs the segment-drop and edge-strip guards
    together with the punctuation cleanup to a fixed point, since dropping a segment or an edge
    word routinely exposes stray commas/whitespace that only `_clean_punctuation` knows how to
    fix, and fixing *that* can reveal another dangling word underneath (e.g. a title with two
    consecutive dangling segments). Bounded so a pathological input can't loop forever; every real
    title seen so far settles in 1-2 passes."""
    for _ in range(10):
        previous = result
        result = _drop_dangling_segments(result)
        result = _strip_dangling_edges(result)
        result = _clean_punctuation(result)
        result = result.strip()
        if result == previous:
            break
    return result


def product_line_guard_violations(result: str | None) -> list[str]:
    """The invariants a `product_line` must satisfy after `_strip_dangling_tokens` — exported
    (not test-private) so a future removal rule can be checked against the same definition rather
    than a re-guessed copy of it. Checks the whole-string edges *and* every comma-delimited
    segment (the "diametru" case is mid-string, not at either edge — an edges-only check would
    have missed the exact bug this guard exists for). Empty list means clean. `None`/empty input
    trivially passes."""
    if not result:
        return []
    violations: list[str] = []
    words = result.split()
    if words and _folded_word(words[-1]) in _DANGLING_WORDS:
        violations.append("ends_in_connective_or_qualifier")
    if words and _folded_word(words[0]) in _DANGLING_WORDS:
        violations.append("starts_with_connective_or_qualifier")
    if any(_is_dangling(segment) for segment in result.split(",")):
        violations.append("orphaned_qualifier_in_comma_segment")
    if re.search(r",\s*,", result):
        violations.append("contains_double_comma")
    if re.match(r"^[\s,.\-–—/(]", result):  # noqa: RUF001 — en/em dash, real
        violations.append("starts_with_connective_or_punctuation")
    if result[-1] in "-–—/(":  # noqa: RUF001 — en/em dash, real
        violations.append("ends_in_bare_punctuation")
    return violations


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
    result = _clean_punctuation(result)
    result = result.strip()
    # STEP 1b's guard, run last: only after brand/clause/quantity removal and punctuation
    # cleanup can a connective or qualifier word actually be left dangling with nothing to
    # modify — see `_strip_dangling_tokens`'s own docstring for the motivating case.
    result = _strip_dangling_tokens(result)

    return result or None


__all__ = ["extract_product_line", "product_line_guard_violations"]
