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

# Convention 7 (ADR-0027): breed_size_code names the ANIMAL a product is sized for, never a
# physical accessory's own dimension band. A harness, leash, collar or transport crate routinely
# carries a size letter/word drawn from the exact same vocabulary ("L", "Medium", "XS-XL") — but
# it's the *product's* size, not a breed classification, and reading it as one is a real, checked
# false-positive class (see the samples grounding this list in DECISIONS.md ADR-0027): "Cusca
# transport animale MPB GIPSY L, 58x38x38 cm" (51 distinct titles carry "cusca", 54 "transport"),
# "Lesa ... Pana la 15 kg, S, ..." (187 distinct titles carry "lesa"), "Zgarda ... 20-33 cm" (113
# distinct titles carry "zgarda") — every one of these categories states its own size
# independently of which breed it fits, and none of the words below collided with anything
# food-related when checked against the full in-scope population (no "hrana"/"recompense" title
# matched any of them).
_ACCESSORY_CONTEXT = re.compile(r"\b(zgarda|zgarzi|lesa|lese|cusca|custi|transport)\b")

# "ham" (harness) is handled separately, anchored to the *start* of the title, not matched
# anywhere: unlike the words above, a bare `\bham\b` collides with the English loanword "ham"
# (the meat) that a handful of titles use in a flavour phrase — "... with ham and chicken", "Pate
# With Ham" (2 real titles, checked) — neither of which is a harness. Every real harness title
# checked (130 distinct) opens with "Ham" as the product-category word, so anchoring to the start
# clears both false positives at the cost of one known, accepted miss: "Curea Y, ham Julius K9 -
# M" states "ham" mid-title with no other accessory word present, so its own "M" is not excluded.
# Not fixed by adding "curea" as its own vocabulary word — that string appears in only 2 titles
# total in this data, too thin to trust as a general accessory-category signal the way the others
# above are (checked in DECISIONS.md ADR-0027 alongside the words that were added).
_HARNESS_PREFIX = re.compile(r"^ham\b")

# A size letter/word immediately followed by its own numeric dimension/capacity band ("M 30-51
# cm", "L, 40x30x20 cm", "S, ... Pana la 15 kg" read in reverse as "kg ... S") is the product's
# own measurement whatever the title's category words say — checked at the match itself, not
# only via the vocabulary above, so an accessory outside that closed word list is still caught.
_FOLLOWED_BY_DIMENSION = re.compile(
    r"^[\s,]*\d+(?:[.,]\d+)?\s*(?:[x×-]\s*\d+(?:[.,]\d+)?\s*)*(?:cm|mm)\b"  # noqa: RUF001
)

# STEP 3 fix #2 (2026-09-14, gate mismatches #3322/#3908, both "... M-PETS ..."): a bare size
# letter immediately followed by a hyphen and more letters is a hyphenated code or word, never a
# size — the hyphen creates a `\b` word boundary that makes the letter look free-standing to
# `_SINGLE_LETTER_SIZE`, the same mechanism `_PRECEDED_BY_APOSTROPHE` already guards against on
# the other side. Checked against the full population before trusting this as a general guard,
# not a brand-specific patch: every `<letter>-<word>` shape that isn't already a legitimate
# `_COMPOUND_SIZE` code (XS-XL, S-M, etc. — matched first, never reaches this loop) is
# `"m-pets"`/`"m-pets "` (81 distinct titles, the brand M-Pets — 73 of them currently mis-tagged
# `breed_size_code="M"`), `"m-pes"` (1 title, a typo/OCR variant of the same brand), and
# `"l-carnitina"` (1 title, L-Carnitine — a supplement ingredient, not a size at all). All three
# are real false positives this guard clears; none is a real size code shaped like this in the
# checked data.
_FOLLOWED_BY_HYPHEN_WORD = re.compile(r"^-[A-Za-z]")


def extract_breed_size(title: str) -> str | None:
    folded = strip_diacritics(title.lower())
    if _ACCESSORY_CONTEXT.search(folded) is not None or _HARNESS_PREFIX.match(folded) is not None:
        return None
    if (match := _COMPOUND_SIZE.search(title)) is not None:
        return match.group(1).upper()
    if (match := _WORD_SIZE.search(title)) is not None:
        return match.group(1).capitalize()
    for match in _SINGLE_LETTER_SIZE.finditer(title):
        before = title[: match.start()]
        after = title[match.end() :]
        if _LOOKS_LIKE_A_QUANTITY.search(before) or _PRECEDED_BY_APOSTROPHE.search(before):
            continue
        if _FOLLOWED_BY_DIMENSION.search(after) or _FOLLOWED_BY_HYPHEN_WORD.search(after):
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
#
# STEP C (prior session): six more words folded into this same specific tier, each checked
# against the full in-scope population before adding (counts in STATE.md/DECISIONS.md) — "jerky"
# (dry by definition — dried meat), "pate"/"ragout"/"cremoasa"/"cremos"/"tub"/"sos" (all wet —
# pâté, ragout, a creamy topping, a squeezable tube, and "in sauce" are all liquid/moist
# preparations). "cutie" (box) was checked too and dropped — real samples showed it packaging
# both dry treats and wet toppers with no reliable way to tell which from the word alone, so
# mapping it to any single category would have been a guess, not a finding.
#
# STEP 3 fix #1 (2026-09-14, gate mismatch #9747/#11418/#9752): "punguta" (diminutive of "pungă",
# the shop's own word for a treat pouch — "punguță recompense") added to this tier, same category
# as "plic". Checked against the full in-scope population before trusting: 420 distinct titles,
# **every one** in a "recompense" (treat) context, zero collisions with any other use of the word.
_SPECIFIC_FORM = re.compile(
    r"\b(conserv[aă]|plic(?:uri)?|punguta|jerky|pate|ragout|cremo(?:asa|s)|tub|sos)\b"
)
# STEP 3 fix #3 (2026-09-14, gate mismatch #17595 "fâșii uscate"): the plural "uscate" (dry) added
# to the generic tier — `uscat[aă]?e?` now matches "uscat"/"uscata"/"uscată"/"uscate". Checked
# against the full population: 8 distinct titles, all genuine dried treats ("Urechi Uscate",
# "chipsuri uscate", "fâșii uscate") — no collisions.
#
# The plural "umede" (wet) was checked the same way and deliberately NOT added: 17 distinct
# titles carry it, and every single one is "Servetele umede" (wet WIPES — a hygiene accessory),
# never wet food. Adding it would have manufactured 17 false positives, tagging a hygiene product
# as a food form — exactly the class of bug this checked-before-adding discipline exists to catch.
#
# STEP 3 fix (2026-09-14, gate mismatch #28159): "semi-umeda" (semi-moist) was matching the
# generic "umeda" alternative via its own substring, tagging semi-moist food/treats as "wet" —
# a real category error (semi-moist fits none of the four dry/wet/tin/pouch values cleanly, so
# the honest answer is null, matching what the external label already said for this case). The
# `umed[aă]?` alternative is now guarded against an immediately preceding "semi-"/"semi " —
# checked against the full population: 8 distinct titles carry "semi-umeda", every one of them a
# real semi-moist product, none of them a plain wet one the guard would wrongly null out instead.
_GENERIC_FORM = re.compile(r"\b(uscat[aă]?e?)\b|(?<!semi-)(?<!semi )\b(umed[aă]?)\b")
_FOOD_FORM_CANONICAL = {
    "uscata": "dry",
    "uscat": "dry",
    "uscate": "dry",
    "umeda": "wet",
    "umed": "wet",
    "conserva": "tin",
    "plic": "pouch",
    "plicuri": "pouch",
    "punguta": "pouch",
    "jerky": "dry",
    "pate": "wet",
    "ragout": "wet",
    "cremoasa": "wet",
    "cremos": "wet",
    "tub": "wet",
    "sos": "wet",
}


def extract_food_form(title: str) -> str | None:
    folded = strip_diacritics(title.lower())
    match = _SPECIFIC_FORM.search(folded) or _GENERIC_FORM.search(folded)
    if match is None:
        return None
    # `_GENERIC_FORM` has two alternatives, each its own capture group (the second carries the
    # negative-lookbehind guard against "semi-"); `_SPECIFIC_FORM` has exactly one. Either way,
    # exactly one group is populated on a match — take whichever it is.
    word = next(g for g in match.groups() if g is not None)
    return _FOOD_FORM_CANONICAL.get(word)


__all__ = ["extract_breed_size", "extract_food_form", "extract_life_stage"]
