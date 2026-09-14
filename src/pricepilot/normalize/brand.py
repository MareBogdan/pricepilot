"""Brand canonicalization (STEP 3, second in build order per CLAUDE.md §7).

**Built from real per-source data, not guessed.** Before writing a single alias, every distinct
brand string collected so far (in-scope, all three sources) was printed with its count — 132
distinct strings on animax_ro, 153 on pentruanimale_ro, 185 on petmax_ro. The suffix words and
aliases below come from reading that output, not from assumption. The full listing lives in this
session's tool output, not committed (it's a live snapshot of `raw_listings`, not a fixture) —
re-run the same query (`raw_payload->>'brand'` grouped by source, in-scope only) to reproduce it.

**Target shape is convention 5 (ADR-0026): the manufacturer, lowercased, simplest form.**
`"brit"` not `"Brit Premium"`, `"hill's"` not `"HILL'S Science Plan"`. The sub-line belongs in
`product_line` (not built this session — see STATE.md Open issues), never in `brand`.

**Mechanism, in priority order:**

1. Case/quote-fold the shop's raw brand string (`.lower()`, curly apostrophe -> straight — never
   full diacritic stripping: CLAUDE.md §7 names Smolke and Hill's explicitly as brands that must
   survive canonicalization intact, and folding "o slash" to a plain "o" would be exactly the
   kind of mangling that violates that, even though `overlap.py`'s *matching key* deliberately
   does fold it for its own, different purpose).
2. An exact-match alias table for strings with no shared prefix to strip structurally — a
   standalone `"PRO PLAN"` or `"Dog Chow"` carries no `"purina"` substring for a suffix-stripper
   to preserve, so these are named explicitly, each justified by what a compound sibling string
   in the same data confirms (`"Purina Pro Plan"`, `"Purina Dog Chow"` both exist alongside the
   standalone forms).
3. A trailing marketing-suffix stripper for the sub-line fragmentation the 2026-09-13 diagnostic
   documented (Brit, Calibra, Hill's) plus a few more the printed data made equally unambiguous
   (Purina's "one"/"pro plan"/"cat chow"/"dog chow" suffixes, Unica's "classe"). Never strips a
   suffix that would leave nothing behind — that case belongs in the alias table above instead
   (`"dog chow"` alone must not become `""`).

**Known, deliberate gap.** Only three sources' worth of data has been read. Many of the ~470
distinct raw strings are genuinely single, unfragmented manufacturer names already (Royal Canin,
Trixie, Josera, Taste of the Wild...) and pass through unchanged, correctly. Some fragmentation
almost certainly remains uncaught (e.g. "Essential Foods" vs "Essential" — no suffix word here
covers "foods", and nothing in the printed data confirmed they're the same manufacturer strongly
enough to alias without guessing). STEP 4's coverage report is where any of that should surface,
not a claim of completeness made here.
"""

from __future__ import annotations

import re

_QUOTE_FOLD = str.maketrans(
    {
        "’": "'",  # curly right single quote  # noqa: RUF001
        "‘": "'",  # curly left single quote  # noqa: RUF001
    }
)


def _normalize_case(text: str) -> str:
    return text.translate(_QUOTE_FOLD).lower().strip()


# Exact-string aliases: the raw value carries no manufacturer-name prefix a suffix-stripper could
# preserve, so each is named directly. Every entry is grounded in a compound sibling actually
# observed in the same data (see the module docstring).
_ALIASES: dict[str, str] = {
    "pro plan": "purina",  # petmax: "PRO PLAN" (85) / "Pro Plan" (2), alongside "PURINA Pro Plan"
    "dog chow": "purina",  # petmax: "Dog Chow" (28), alongside pentruanimale's "Purina Dog Chow"
    "cat chow": "purina",  # pentruanimale carries "Purina Cat Chow"; no bare "Cat Chow" seen, but
    #                         kept for symmetry with "Dog Chow" and Purina's well-known lineup
    "affinity advance": "advance",  # animax: "Affinity Advance" (8) vs. "Advance" (33 here, 138
    #                                  on pentruanimale, 90 on petmax) — Affinity is Advance's
    #                                  parent company, not a second brand
    "julius k-9": "julius-k9",  # petmax writes "Julius k-9" (space), pentruanimale "Julius-K9"
    #                              (hyphen) — same manufacturer, spacing/hyphenation differs only
    "m-petss": "m-pets",  # petmax: "M-Petss" (32) is a doubled-s scrape/typo duplicate of the
    #                        same source's own "M-Pets" (160) — not a second brand
}

# Longest phrases first, so "science plan" is matched whole rather than leaving a stray "plan".
# Every phrase here is a genuine trailing suffix seen on a real brand string in this data.
_SUFFIX_PHRASES: tuple[str, ...] = (
    "science plan",  # Hill's Science Plan / HILL'S Science Plan -> hill's
    "pet nutrition",  # Hill's Pet Nutrition -> hill's
    "pro plan",  # Purina Pro Plan / PURINA Pro Plan -> purina
    "cat chow",  # Purina Cat Chow -> purina
    "dog chow",  # Purina Dog Chow -> purina
    "premium",  # Brit Premium, Calibra Premium -> brit / calibra
    "care",  # Brit Care -> brit
    "life",  # Calibra Life -> calibra
    "expert",  # Calibra Expert -> calibra
    "fresh",  # Brit Fresh -> brit
    "classe",  # Unica Classe -> unica (matches pentruanimale's bare "UNICA")
    "one",  # Purina ONE / Purina One -> purina
)


def _strip_marketing_suffix(normalized: str) -> str:
    """Removes at most one trailing suffix phrase, and only when something non-empty remains —
    never reduces a brand to nothing (that case is the alias table's job, not this function's)."""
    for phrase in _SUFFIX_PHRASES:
        if normalized == phrase:
            continue  # exact match: handled by _ALIASES or left as-is, never emptied here
        if normalized.endswith(" " + phrase):
            remainder = normalized[: -(len(phrase) + 1)].strip()
            if remainder:
                return remainder
    return normalized


def brand_span_text(source_brand: str | None) -> str | None:
    """The quote/case-folded substring of `source_brand` that `product_line` should strip from
    the title — the manufacturer name only, never sub-line text the shop packed into the same
    field. `None` under the same conditions `canonicalize_brand` returns `None`.

    Two shapes, matching the two branches `canonicalize_brand` itself takes:

    - **Alias-table entry** (a full-string remap, e.g. `"Affinity Advance"` -> `"advance"`,
      `"PRO PLAN"` -> `"purina"`): the *entire* raw field names the manufacturer, with no
      separate sub-line inside it, so the whole normalized string is returned.
    - **Marketing-suffix case** (e.g. `"Brit Premium"` -> `"brit"`, `"HILL'S Science Plan"` ->
      `"hill's"`): only the retained *prefix* is returned. The stripped suffix (`"premium"`,
      `"science plan"`) is real sub-line text — per convention 5 (ADR-0026) it belongs in
      `product_line`, and stripping the whole raw field (the bug this function replaces) cut it
      out of the title along with the brand, silently fragmenting the same product's sub-line
      differently on every shop that phrases its brand field differently (petmax's `"Brit
      Premium"` vs pentruanimale's bare `"BRIT"` — see the 2026-09-14 diagnostic in
      DECISIONS.md/ADR-0027). Falls out of `_strip_marketing_suffix` returning its input
      unchanged when no suffix phrase matches, so a bare `"BRIT"`/`"CALIBRA"` naturally returns
      the whole (short) string with no special-casing needed here.
    """
    if not source_brand or not source_brand.strip():
        return None
    normalized = _normalize_case(source_brand)
    if not normalized:
        return None
    if normalized in _ALIASES:
        return normalized
    return _strip_marketing_suffix(normalized)


def canonicalize_brand(title: str, source_brand: str | None) -> str | None:
    """`title` is accepted for a future title-only fallback (not built this session — every
    source's structured brand field is populated for all but a handful of rows, so the fallback's
    value is low relative to the risk of guessing wrong; see STATE.md Open issues) and is unused
    for now. Returns `None` — "not stated" — when the shop's own brand field is empty, which is a
    real, honest answer, not an extraction failure."""
    del title  # reserved for a future fallback; see docstring
    if not source_brand or not source_brand.strip():
        return None
    normalized = _normalize_case(source_brand)
    if normalized in _ALIASES:
        return _ALIASES[normalized]
    return _strip_marketing_suffix(normalized)


# Phase 3 STEP 3: a hyphen/space/punctuation-insensitive key for candidate BLOCKING, never for
# display. `canonicalize_brand()`'s own output is still the right thing to show a human or store
# as `brand` — this exists only so an exact-match blocking step doesn't silently miss two
# spellings of the same manufacturer. Grounded in real, checked collisions among today's own
# canonical brand values (not a hypothetical): `"club 4 paws"`/`"club4paws"`,
# `"cat's best"`/`` "cat`s best" `` (straight vs curly-backtick apostrophe — `_normalize_case`
# folds curly *quotes* but not this particular backtick-as-apostrophe variant), `"my love"`/
# `"mylove"`, `"lolopets"`/`"lolo pets"`, `` "dr. clauder's" ``/`` "dr. clauder`s" `` — five
# distinct manufacturers, found by stripping every non-alphanumeric character from every current
# canonical brand and grouping by what collides. Julius K-9's two real spellings
# (`"Julius k-9"`/`"Julius-K9"`) were checked too and turned out to already canonicalize
# identically via the existing alias — not every hyphen variant needs this key, but relying on
# hand-maintained aliases catching every future one is exactly the fragility this key exists to
# remove.
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def brand_blocking_key(canonical_brand: str | None) -> str | None:
    """Lowercased, every non-alphanumeric character removed. `None` in, `None` out."""
    if not canonical_brand:
        return None
    key = _NON_ALNUM.sub("", canonical_brand.lower())
    return key or None


# Phase 3 STEP 3: brand-trustworthiness. **An automated per-brand classifier was attempted and
# rejected as unreliable, not shipped.** The first approach tried — flag a canonical brand as
# suspicious when its own text rarely appears inside the titles of its own listings — fails
# badly in practice: checked against the full population, `"essential foods"`, `"chicoppe"`,
# `"dr seidel"` and `"dolina"` (all real, verifiable manufacturers — Chicopee is a genuine Polish
# pet-food maker, Dolina Noteci owns the "Piper" house brand its titles show instead of its own
# name) all score 0% title-overlap, identical to confirmed-suspicious values — the statistic
# cannot tell "a real manufacturer whose name a generic-category title just doesn't repeat" from
# "a distributor code with no real brand identity" at all. No threshold on this statistic
# separates the two classes; shipping one anyway would present an unreliable signal as a
# trustworthy one, which is worse than shipping nothing.
#
# What ships instead: a small, hand-verified list, built by actually reading a sample of each
# candidate's real titles (same discipline as ADR-0025's token checks) rather than trusting the
# statistic that flagged them as candidates in the first place.
#
# - `"opti"` (165 listings) — CONFIRMED. Every sampled title is a generic, colour-varying cat
#   scratching-post/play-set description ("Ansamblu de joaca... culoare bej/gri/mov...") with no
#   brand-identity word anywhere, consistent with an unbranded OEM product line the shop labels
#   internally, not a real consumer-facing manufacturer.
# - `"ipts"` (33 listings) — WEAKER EVIDENCE, flagged anyway. Spans disjoint product types (a
#   dental chew, a frisbee, latex toys) under one name that reads as a supplier code rather than
#   an established brand, but roughly half its titles DO carry "Ipts" visibly (`"Jucarie...Ipts
#   Curcan"`) — a real (if minor) brand would look like this too. Kept in the list with this
#   caveat recorded, not silently upgraded to "confirmed" the way `"opti"` is.
#
# Checked and explicitly NOT added: `"record"` — real, identifiable Italian pet-accessories
# manufacturer (est. 1969); most of its titles do carry recognizable "Record"/"BiscoRe"/"Cat&Rina
# Record" text, unlike a true distributor code. An earlier, hastier read of this same data
# (2026-09-14 gate-fix session) called it a distributor code without checking title context this
# closely — corrected here, not left standing.
_SUSPECTED_DISTRIBUTOR_CODES = frozenset({"opti", "ipts"})


def is_suspected_distributor_code(canonical_brand: str | None) -> bool:
    """`True` only for the small, hand-verified list above — never a statistical threshold. See
    the module docstring above this function for why an automated version was rejected."""
    if not canonical_brand:
        return False
    return canonical_brand.lower() in _SUSPECTED_DISTRIBUTOR_CODES


__all__ = [
    "brand_blocking_key",
    "brand_span_text",
    "canonicalize_brand",
    "is_suspected_distributor_code",
]
