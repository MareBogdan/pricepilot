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


# Phase 3 finding 6 (2026-09-15 session, pilot positions 28/69/88/94): "XS-XL" is
# pentruanimale_ro's own "fits any breed size" marker, not a real breed-size claim — checked
# against the full population before trusting (not assumed): of 985 in-scope rows carrying this
# literal code, **100% are pentruanimale_ro** (0 from petmax_ro, 0 from animax_ro), and it is by
# far the single largest breed_size_code value in the whole population (985, ahead of "Mini"'s
# 400) — consistent with it being a boilerplate default stamped on most of that shop's product
# pages rather than a size the product is actually restricted to. Storing it as a real code made
# the field falsely "stated" on the pentruanimale side of a pair whose other side (petmax/animax)
# states nothing, which the annotation-queue forecast's rule 6 (one-sided field -> S) then
# over-counted as an ambiguous case. Treated as "no breed-size stated", same as if the title had
# never mentioned a size at all.
_ALL_SIZES_MARKER = "XS-XL"


def extract_breed_size(title: str) -> str | None:
    folded = strip_diacritics(title.lower())
    if _ACCESSORY_CONTEXT.search(folded) is not None or _HARNESS_PREFIX.match(folded) is not None:
        return None
    if (match := _COMPOUND_SIZE.search(title)) is not None:
        code = match.group(1).upper()
        return None if code == _ALL_SIZES_MARKER else code
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


# Phase 3 finding 5 (2026-09-15 session): a canonical breed-size code alongside the raw token,
# same idea as `brand_blocking_key` — the raw string alone makes "Medium" and "M" (a real
# cross-shop match, pilot position 12) or "Mini" and "XS-S" (pilot 55) look like a mismatch when
# they name the same size. Checked against the real population before building the mapping, not
# assumed complete from the two examples the finding named (`docs/learned/` census + a
# same-real-product cross-shop join, both this session): every distinct `breed_size_code` value
# was printed with its count first, then pentruanimale_ro's OWN titles were mined for cases where
# a word form ("Large Breed", "Small & Medium Breed", ...) and a compact code ("L-XL", "XS-M", ...)
# appear together in the SAME title — self-consistent, single-source evidence, no cross-shop
# noise. Dominant, unambiguous pairings found this way: Mini/Small <-> XS-S (170+ titles), Small &
# Mini <-> XS-S, Large <-> L-XL (63), bare Maxi <-> L-XL (18), "Medium & Maxi"/"Medium and Maxi"
# (a distinct compound WORD phrase, not bare Maxi) <-> M-XL (27), Giant <-> XL (4). Word "Medium"
# alone maps to letter "M" per the task's own confirmed cross-shop case (pilot 12); internal
# evidence for this specific pairing was thin (n=2) but did not contradict it.
#
# Modelled as a RANK INTERVAL, not a flat bucket string, because the real relationship is a
# continuum (XS < S < M < L < XL) that shops chunk differently, and several compact codes
# genuinely SPAN more than one rank (e.g. "M-XL" legitimately means "fits Medium through
# Extra-Large" — collapsing it into one flat bucket would silently pick a side). Two codes are
# then compared by RANK OVERLAP (any shared rank = compatible, not forced N), not string
# equality — Medium(3,3) overlaps M-XL(3,5) at rank 3, which is exactly the real cross-shop match
# found while building this table (`REMI PREMIUM Junior Medium&Large, M-XL` = `Remi Premium
# Junior Medium&Large`, animax tagging it "Medium" because its own extractor only ever catches a
# single word). Stored as a compact `"lo-hi"` string (e.g. `"3-3"`, `"1-2"`) — same shape as
# `brand_blocking_key`, a derived lookup column, not a new raw field.
_RANK = {"XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5}
_WORD_RANK: dict[str, tuple[int, int]] = {
    "Mini": (1, 2),
    "Medium": (3, 3),
    "Maxi": (4, 5),
}


def breed_size_rank(code: str | None) -> tuple[int, int] | None:
    """The canonical (lo, hi) rank interval for a raw `breed_size_code` value, or `None` when the
    code is unmapped (should not happen for any value this module itself produces, since every
    value `extract_breed_size` can return is covered below) or the input is `None`."""
    if code is None:
        return None
    if code in _RANK:
        return (_RANK[code], _RANK[code])
    if code in _WORD_RANK:
        return _WORD_RANK[code]
    if "-" in code:
        lo_s, _, hi_s = code.partition("-")
        lo, hi = _RANK.get(lo_s), _RANK.get(hi_s)
        if lo is not None and hi is not None:
            return (lo, hi)
    return None


def breed_size_class(code: str | None) -> str | None:
    """`breed_size_rank()` packed as a compact `"lo-hi"` string for storage/lookup."""
    rank = breed_size_rank(code)
    return None if rank is None else f"{rank[0]}-{rank[1]}"


def breed_size_overlaps(left: str | None, right: str | None) -> bool | None:
    """`True` if both sides have a mapped rank interval and they share at least one rank (same
    real size, however each shop wrote it). `False` if both are mapped and DISJOINT (confidently
    different sizes). `None` if either side is unmapped/unstated — not a guess either way."""
    lr, rr = breed_size_rank(left), breed_size_rank(right)
    if lr is None or rr is None:
        return None
    return lr[0] <= rr[1] and rr[0] <= lr[1]


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

# Phase 3 finding 7 (2026-09-15 session, pilot 15: "RC Maxi Adult" vs "RC Maxi Adult (5+)"; pilot
# 30: "RC Medium Adult" vs "RC Medium Adult 7+" — both real N, both scored M because the ladder
# only ever saw "adult" on both sides). Royal Canin (and a few others) qualify "Adult"/"Senior"
# with a minimum-age band — "(5+)", "7+", "8+", "11+" — that names a genuinely different formula,
# not a synonym for plain Adult. Checked against the full population before trusting this pattern
# (not assumed): 97 in-scope titles carry a bare `\d+\+` token; the overwhelming majority are this
# age-qualifier shape, but a real false-positive class exists too — BONUS-WEIGHT phrases like
# "10+2kg GRATUIT" / "12+2 kg" / "8+1kg GRATUIT" (quantity.py's own bonus_weight_g pattern) also
# match a bare `\d+` immediately followed by `+`. Distinguished the same way quantity.py already
# tells the two apart: a bonus-weight `+` is always immediately followed by ANOTHER digit (the
# bonus amount); a genuine age qualifier never is (it's followed by `)`, `,`, a space, or the
# string's end) — verified against every one of the 97 titles, not just the pattern's shape.
_AGE_QUALIFIER = re.compile(r"\((\d{1,2})\+\)|\b(\d{1,2})\+(?!\d)")


def extract_life_stage(title: str) -> str | None:
    folded = strip_diacritics(title.lower())
    match = _LIFE_STAGE.search(folded)
    if match is None:
        return None
    word = match.group(1)
    stage = "adult" if word.startswith("adult") else word
    # Only appends the qualifier when a life-stage word was already found — a bare age qualifier
    # with no life-stage word at all ("Royal Canin Sterilised 7+") is left as a separate, still-
    # open gap (no life-stage word to attach it to), not guessed into a new category.
    age_match = _AGE_QUALIFIER.search(title)
    if age_match is not None:
        n = age_match.group(1) or age_match.group(2)
        stage = f"{stage}+{n}"
    return stage


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


__all__ = [
    "breed_size_class",
    "breed_size_overlaps",
    "breed_size_rank",
    "extract_breed_size",
    "extract_food_form",
    "extract_life_stage",
]
