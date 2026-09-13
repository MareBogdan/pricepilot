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


__all__ = ["canonicalize_brand"]
