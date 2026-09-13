"""EN/RO flavour (protein source) extraction (STEP 3, third in build order per CLAUDE.md §7).

CLAUDE.md §7 names eight EN/RO pairs as the starting table: Chicken/Pui, Lamb/Miel, Beef/Vita,
Salmon/Somon, Turkey/Curcan, Duck/Rata, Rabbit/Iepure, Tuna/Ton — **both** halves of each pair are
matched, not just the Romanian one (an English-language title, or an EN/RO-mixed one, must still
resolve). "Extended from the data rather than guessed" — reading real titles in the frozen gate
sample and the sources scanned while building `brand.py` surfaced three more unambiguous pairs:
Fish/Peste, Liver/Ficat, Game/Vanat (venison).

A title can genuinely name more than one protein ("cu Iepure si Vita" — rabbit AND beef). The
schema has one `flavour` column, not a list, so multiple matches are joined with "+" in the order
they appear in the title, deduplicated — information-preserving rather than arbitrarily keeping
only the first match and discarding the rest.
"""

from __future__ import annotations

import re

from pricepilot.overlap import strip_diacritics

# Surface word (diacritic-folded, so "ă"/"â"/"î" already fold to "a"/"i") -> canonical EN name.
# Both the English and Romanian spelling of each pair are listed, mapping to the same canonical
# value — a title can be written in either language, or mix the two.
_FLAVOUR_WORDS: tuple[tuple[str, str], ...] = (
    ("chicken", "chicken"),
    ("pui", "chicken"),
    ("lamb", "lamb"),
    ("miel", "lamb"),
    ("beef", "beef"),
    ("vita", "beef"),  # "vită" folds to "vita"
    ("salmon", "salmon"),
    ("somon", "salmon"),
    ("turkey", "turkey"),
    ("curcan", "turkey"),
    ("duck", "duck"),
    ("rata", "duck"),  # "rață" folds to "rata"
    ("rabbit", "rabbit"),
    ("iepure", "rabbit"),
    ("tuna", "tuna"),
    ("ton", "tuna"),
    ("fish", "fish"),
    ("peste", "fish"),  # "pește" folds to "peste"
    ("liver", "liver"),
    ("ficat", "liver"),
    ("game", "game"),
    ("vanat", "game"),  # "vânat" folds to "vanat"
)

_PATTERN = re.compile(r"\b(" + "|".join(re.escape(word) for word, _ in _FLAVOUR_WORDS) + r")\b")
_CANONICAL = dict(_FLAVOUR_WORDS)


def extract_flavour(title: str) -> str | None:
    folded = strip_diacritics(title.lower())
    seen: list[str] = []
    for match in _PATTERN.finditer(folded):
        canonical = _CANONICAL[match.group(1)]
        if canonical not in seen:
            seen.append(canonical)
    return "+".join(seen) if seen else None


__all__ = ["extract_flavour"]
