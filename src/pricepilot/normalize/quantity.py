"""Weight/volume/pack-count/bonus/dosage-band extraction (STEP 3, built first per CLAUDE.md §7:
"weight parsing measured separately" and named as the highest-leverage field).

Deliberately **not** built on top of `overlap.py`'s `net_weight_grams()`/`bonus_weight_grams()` —
those answer a different question (a proxy-key floor estimate, CLAUDE.md §7 gate) over the *raw*
title, and for a multipack `net_weight_grams()` returns the *total* mass (count x unit weight) on
purpose for its own matching semantics. STEP 2's convention 1 for `norm_listings` is the opposite:
`net_weight_g` is the *single* purchasable unit (85, not 1020, for "12x85 g"), with `pack_count`
carrying the multiplier separately. Worse, calling either of `overlap.py`'s functions directly on
a raw title would misread a dosage band as a plain weight for a title that states both ("...Medium
12-25kg 115g") — this module masks the dosage band out *before* any weight pattern runs, which
`overlap.py` has no reason to do. So the grams/millilitres math below is a fresh, independent
implementation, even though it computes the *same* mass-conversion convention (1 kg = 1000 g, 1 l
= 1000 ml) `overlap.py` uses — matching convention 2's "reuse `OverlapKey.bonus_g`'s existing
semantics exactly" in outcome, not by literally calling into the frozen module. `overlap.py`
itself is never modified; only its diacritic folding (`strip_diacritics`, a general text utility,
not part of the measurement it protects) is imported below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from pricepilot.overlap import strip_diacritics

# Longest unit names first, so "grame" doesn't get chopped down to a false match on "g" partway
# through — the same ordering trap `overlap.py`'s `_UNIT` documents.
_UNIT = r"(?:grame|kg|gr|g|ml|l)"

_MASS_UNITS = frozenset({"kg", "g", "gr", "grame"})
_VOLUME_UNITS = frozenset({"ml", "l"})


def _grams(value: Decimal, unit: str) -> int:
    return int(value * (Decimal("1000") if unit == "kg" else Decimal("1")))


def _millilitres(value: Decimal, unit: str) -> int:
    return int(value * (Decimal("1000") if unit == "l" else Decimal("1")))


def _to_decimal(raw: str) -> Decimal:
    return Decimal(raw.replace(",", "."))


# Convention 4: an animal's dosage band ("10-25 kg") is a hyphenated range immediately followed
# by "kg" — always mass, never a decimal-comma-vs-point ambiguity in the data seen so far, and
# never volume (nobody doses an animal by litres). Matched and *removed* from the text before any
# weight/volume/pack/bonus pattern runs, so a title carrying both a dosage band and the product's
# own real weight ("...Medium 12-25kg 115g") doesn't have the band's second number mistaken for
# the product's net weight.
#
# `(?<![\w-])` before the first digit: found and fixed a real false positive before trusting this
# — "Julius K-9- 3kg" (385 titles carry this brand) parsed as dosage band "9-3 kg", swallowing
# the product's real 3kg weight, because plain `\b` treats the hyphen in "K-9" as a legitimate
# boundary. A dosage band's first number must not be glued to a letter-hyphen code like that;
# requiring the character just before it be neither a word character nor a hyphen blocks "K-9-
# 3kg" (preceded by "-") while a genuine "...Medium 12-25kg..." (preceded by a space) is
# unaffected.
_DOSAGE_BAND = re.compile(r"(?<![\w-])(\d{1,3}(?:[.,]\d+)?)\s*-\s*(\d{1,3}(?:[.,]\d+)?)\s*kg\b")

# "8 kg + 1 kg gratuit", "15 + 3 Kg Gratis" — same shape as overlap.py's `_BONUS`, kept
# independent (not imported) because this module's `_UNIT` alternation and downstream grams/ml
# conversion are its own, per the module docstring.
_BONUS = re.compile(
    rf"(?P<base>\d+(?:[.,]\d+)?)\s*(?P<base_unit>{_UNIT})?\s*\+\s*"
    rf"(?P<bonus>\d+(?:[.,]\d+)?)\s*(?P<bonus_unit>{_UNIT})\b",
)

# "24x85 g", "5 x 900 g", "1 x 85 g" (convention 3) — count x unit-quantity. A second, looser
# variant covers "4 PLICURI x 14g": a bare word (pouch/sachet/etc.) sitting between the count and
# the "x", seen in real pentruanimale/animax titles. Tried only after the tight form fails, so it
# can't steal a match the tight form would have gotten cleanly.
_PACK_TIGHT = re.compile(
    rf"(?P<count>\d+)\s*[x×]\s*(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>{_UNIT})\b"  # noqa: RUF001
)
_PACK_WITH_WORD = re.compile(
    rf"(?P<count>\d+)\s+[a-z]+\s*[x×]\s*(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>{_UNIT})\b"  # noqa: RUF001
)

# A standalone piece count with no weight multiplication attached ("6 bucati", "4 buc") — the
# fallback for titles like "...Stick din cod - 80 g" ... "6 bucati / 90 g" where the piece count
# and the weight are two separate numbers, not one "Nx" token.
# "bucati"/"bucata" already cover "bucăți"/"bucată" post-fold (ă/ț strip to a/t via
# strip_diacritics), so there's no separate accented spelling to list here.
_PIECE_COUNT = re.compile(r"\b(\d+)\s*(?:buc|bucati|bucata)\b")

_PLAIN = re.compile(rf"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>{_UNIT})\b")


@dataclass(frozen=True)
class QuantityResult:
    net_weight_g: int | None = None
    net_volume_ml: int | None = None
    pack_count: int | None = None
    bonus_weight_g: int | None = None
    dosage_band: str | None = None


def extract_quantity(title: str) -> QuantityResult:
    """The single entry point STEP 3 asked for first. Order matters: dosage band is found and
    masked out before anything else runs, then bonus, then multipack, then a plain single
    quantity — each pattern only gets a chance once the more specific ones above it have failed,
    so a bonus pack is never misread as two unrelated plain weights."""
    text = strip_diacritics(title.lower())

    dosage_band, text = _extract_and_mask_dosage_band(text)

    if (bonus := _BONUS.search(text)) is not None:
        return _from_bonus(bonus, dosage_band)

    pack = _PACK_TIGHT.search(text) or _PACK_WITH_WORD.search(text)
    if pack is not None:
        return _from_pack(pack, dosage_band)

    if (plain := _PLAIN.search(text)) is not None:
        result = _from_plain(plain, dosage_band)
        # A separate, standalone piece count ("6 bucati") can coexist with a plain weight that
        # has no "x" multiplier of its own — only applied when the plain match didn't already
        # settle pack_count via the (impossible here, since _PLAIN never sets it) multipack path.
        if (piece := _PIECE_COUNT.search(text)) is not None:
            result = QuantityResult(
                net_weight_g=result.net_weight_g,
                net_volume_ml=result.net_volume_ml,
                pack_count=int(piece.group(1)),
                bonus_weight_g=result.bonus_weight_g,
                dosage_band=result.dosage_band,
            )
        return result

    # No quantity pattern at all — still honour a bare piece count if one exists, and still
    # carry a dosage band found above. Both are legitimate partial answers, not failures.
    piece = _PIECE_COUNT.search(text)
    return QuantityResult(
        pack_count=int(piece.group(1)) if piece else None,
        dosage_band=dosage_band,
    )


def _extract_and_mask_dosage_band(text: str) -> tuple[str | None, str]:
    match = _DOSAGE_BAND.search(text)
    if match is None:
        return None, text
    band = f"{match.group(1)}-{match.group(2)} kg"
    masked = text[: match.start()] + " " * (match.end() - match.start()) + text[match.end() :]
    return band, masked


def _from_bonus(match: re.Match[str], dosage_band: str | None) -> QuantityResult:
    unit = match.group("base_unit") or match.group("bonus_unit")
    base = _to_decimal(match.group("base"))
    bonus = _to_decimal(match.group("bonus"))
    if unit in _MASS_UNITS:
        return QuantityResult(
            net_weight_g=_grams(base, unit),
            bonus_weight_g=_grams(bonus, match.group("bonus_unit")),
            dosage_band=dosage_band,
        )
    # A volume-unit bonus ("500ml + 50ml gratis") has no schema column to carry the bonus amount
    # in (ADR-0026 added only `bonus_weight_g`, matching every bonus example actually seen in
    # this data — all mass-based). Recorded as a plain volume so net_volume_ml is still correct;
    # the bonus portion is a known, documented gap, not silently invented into the wrong field.
    return QuantityResult(net_volume_ml=_millilitres(base, unit), dosage_band=dosage_band)


def _from_pack(match: re.Match[str], dosage_band: str | None) -> QuantityResult:
    unit = match.group("unit")
    value = _to_decimal(match.group("value"))
    count = int(match.group("count"))
    if unit in _MASS_UNITS:
        return QuantityResult(
            net_weight_g=_grams(value, unit), pack_count=count, dosage_band=dosage_band
        )
    return QuantityResult(
        net_volume_ml=_millilitres(value, unit), pack_count=count, dosage_band=dosage_band
    )


def _from_plain(match: re.Match[str], dosage_band: str | None) -> QuantityResult:
    unit = match.group("unit")
    value = _to_decimal(match.group("value"))
    if unit in _MASS_UNITS:
        return QuantityResult(net_weight_g=_grams(value, unit), dosage_band=dosage_band)
    return QuantityResult(net_volume_ml=_millilitres(value, unit), dosage_band=dosage_band)


__all__ = ["QuantityResult", "extract_quantity"]
