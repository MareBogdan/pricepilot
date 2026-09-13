"""Breed-size code, life stage, food form (STEP 3, "the rest" in CLAUDE.md §7's build order).

Life stage and food form are low-risk, near-literal word lookups. Breed-size is the hard one —
CLAUDE.md §7 names it as a real trap, and a bare single letter ("L", "M", "S") is dangerously
easy to false-positive on inside ordinary prose. Restricted accordingly; see `extract_breed_size`.
"""

from __future__ import annotations

import re

from pricepilot.overlap import strip_diacritics

# ---------------------------------------------------------------------------
# Breed-size code
# ---------------------------------------------------------------------------

# Compound hyphenated codes first (longest-first isn't needed here since they don't nest, but
# ordering by specificity keeps the intent readable) — these are unambiguous wherever they occur,
# no delimiter requirement needed.
_COMPOUND_SIZE = re.compile(r"\b(XS-XL|XS-S|XS-M|XS-L|S-XL|S-M|S-L|M-XL|M-L|L-XL)\b", re.IGNORECASE)

# Word-form codes (Mini/Medium/Maxi) are distinctive enough as whole words to match anywhere.
_WORD_SIZE = re.compile(r"\b(mini|medium|maxi)\b", re.IGNORECASE)

# A single bare letter (XS, S, M, L, XL) is real (CLAUDE.md §7 names it explicitly), but two
# real false-positive classes were found and verified against every stored title before trusting
# this pattern (same discipline as the " pd " token check, ADR-0025):
#
# 1. A volume unit: "Nisip Silicat ... 7,6 L" is 7.6 LITRES, not a size code. Guarded by
#    requiring the letter not be immediately preceded by a digit (with optional separating
#    whitespace/comma) — that shape is a quantity, never a size code in this data.
# 2. A possessive brand apostrophe: "HILL'S ...", "SAM'S FIELD ...", "WOLF'S MOUNTAIN ..." each
#    produce a *phantom* standalone "S" match purely from the apostrophe creating a word
#    boundary — `\bS\b` matches the "S" in "Hill'S" itself, nothing to do with breed size.
#    Guarded by requiring the letter not be immediately preceded by an apostrophe (straight or
#    curly). Found by checking real candidate counts before trusting the regex, not assumed —
#    every HILL'S-branded title in the data would otherwise have silently gained a fabricated
#    "S" breed-size code.
#
# Uppercase-only (no IGNORECASE): these shops always write a real size code in capitals, and
# requiring it removes a further slice of incidental-lowercase-letter risk for free.
_SINGLE_LETTER_SIZE = re.compile(r"\b(XS|XL|S|M|L)\b")
_LOOKS_LIKE_A_QUANTITY = re.compile(r"\d\s*,?\s*$")
_PRECEDED_BY_APOSTROPHE = re.compile(r"['’]\s*$")  # noqa: RUF001 — curly apostrophe, real


def extract_breed_size(title: str) -> str | None:
    if (match := _COMPOUND_SIZE.search(title)) is not None:
        return match.group(1).upper()
    if (match := _WORD_SIZE.search(title)) is not None:
        return match.group(1).capitalize()
    for match in _SINGLE_LETTER_SIZE.finditer(title):
        before = title[: match.start()]
        if _LOOKS_LIKE_A_QUANTITY.search(before) or _PRECEDED_BY_APOSTROPHE.search(before):
            continue
        return match.group(1).upper()
    return None


# ---------------------------------------------------------------------------
# Life stage
# ---------------------------------------------------------------------------

# "pui" (chicken) is deliberately excluded here even though it colloquially can mean "puppy" in
# Romanian — it's already claimed by flavour.py's protein-source table and is ambiguous between
# the two meanings in this data; "puppy" (the English loanword) is what these shops actually
# write for that life stage, per `overlap.py`'s own `_STOPWORDS` (junior/senior/adult(i/ți) are
# listed there; "pui" is not treated as a life-stage word there either). Matched against the
# diacritic-folded title, so "adulți"/"adulti" both fold to "adulti" before this ever runs.
_LIFE_STAGE = re.compile(r"\b(puppy|junior|adulti|adult|senior)\b")


def extract_life_stage(title: str) -> str | None:
    folded = strip_diacritics(title.lower())
    match = _LIFE_STAGE.search(folded)
    if match is None:
        return None
    word = match.group(1)
    return "adult" if word.startswith("adult") else word


# ---------------------------------------------------------------------------
# Food form
# ---------------------------------------------------------------------------

# Checked in two tiers, not by whichever word happens to sit leftmost in the title: "tin"/"pouch"
# are the more specific of CLAUDE.md §7's four categories (dry/wet/tin/pouch are four distinct
# values, not "wet" ⊃ "pouch"), so a title naming both a packaging word and the generic
# "umeda"/wet ("...plic hrana umeda pisici...") must resolve to the packaging word regardless of
# which one it happens to write first.
_SPECIFIC_FORM = re.compile(r"\b(conserv[aă]|plic(?:uri)?)\b")
_GENERIC_FORM = re.compile(r"\b(uscat[aă]?|umed[aă]?)\b")
_FOOD_FORM_CANONICAL = {
    "uscata": "dry",
    "uscat": "dry",
    "umeda": "wet",
    "umed": "wet",
    "conserva": "tin",
    "plic": "pouch",
    "plicuri": "pouch",
}


def extract_food_form(title: str) -> str | None:
    folded = strip_diacritics(title.lower())
    match = _SPECIFIC_FORM.search(folded) or _GENERIC_FORM.search(folded)
    if match is None:
        return None
    return _FOOD_FORM_CANONICAL.get(match.group(1))


__all__ = ["extract_breed_size", "extract_food_form", "extract_life_stage"]
