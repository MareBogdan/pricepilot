"""EN/RO flavour (protein source) extraction (STEP 3, third in build order per CLAUDE.md §7).

CLAUDE.md §7 names eight EN/RO pairs as the starting table: Chicken/Pui, Lamb/Miel, Beef/Vita,
Salmon/Somon, Turkey/Curcan, Duck/Rata, Rabbit/Iepure, Tuna/Ton — **both** halves of each pair are
matched, not just the Romanian one (an English-language title, or an EN/RO-mixed one, must still
resolve). "Extended from the data rather than guessed" — reading real titles in the frozen gate
sample and the sources scanned while building `brand.py` surfaced three more unambiguous pairs:
Fish/Peste, Liver/Ficat, Game/Vanat (venison).

**STEP C (this session).** A random, seeded sample of 60 real titles flagged by
`normalize_coverage.py` as "likely a real food item, flavour missing" or "..., food_form missing"
was read (never `docs/learned/phase2-gate-sample.csv`, which stays frozen). Every candidate word
below was checked against the full in-scope population before being added — counts and sample
context are in `STATE.md`/`DECISIONS.md`, not repeated here. Ten more species/protein words:
Bison/Bizon, Mackerel/Macrou, Ham/Sunca/Jambon, Poultry/Pasare (generic bird — kept distinct from
Chicken/Pui, which names the specific species), Deer/Caprioara/Venison, Reindeer/Ren (a different
species from deer, kept as its own canonical value rather than merged into "game" or "deer" —
lumping distinct species would hurt Phase 3 matching precision, not help it), Goose/Gasca,
Sardine, Cod (identical spelling in both languages).

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
    # STEP C additions — each checked against the full in-scope population before adding.
    ("bizon", "bison"),  # 14 catches, all TASTE OF THE WILD / PRIMORDIAL, all genuine
    ("macrou", "mackerel"),  # 36 catches, all ACANA/PRIMORDIAL/APPLAWS, all genuine
    ("sunca", "ham"),  # "șuncă" folds to "sunca" — 77 catches, all genuine
    ("jambon", "ham"),  # French loanword, 5 catches, same meaning as "sunca" above
    ("pasare", "poultry"),  # "pasăre" folds to "pasare" — 210 catches, generic bird, kept
    # distinct from "pui"/chicken (the specific species) rather than merged into it
    ("caprioara", "deer"),  # "căprioară" folds to "caprioara" — 61 catches
    ("venison", "deer"),  # EN synonym of "căprioară" — 24 catches, same species as above
    ("ren", "reindeer"),  # 17 catches — a different species from deer, not merged with it
    ("gasca", "goose"),  # "gâsca" folds to "gasca" — 23 catches
    ("sardine", "sardine"),  # 28 catches
    ("cod", "cod"),  # 142 catches — identical spelling in English and Romanian
    # STEP 3 fix #4 (2026-09-14, gate mismatch #11166 "Ton și Creveți" scoring as "tuna" alone,
    # missing "shrimp"): checked against the full in-scope population before adding — 52 distinct
    # titles carry "creveti" ("creveți" folds to it post-diacritic-strip), every one a real
    # cat-food/treat shrimp flavour ("Ton și Creveți", "cu ton si creveti", "Somon și Creveți"),
    # no collisions found. The singular RO form "crevete" and the EN "shrimp" have zero hits in
    # this data today — kept anyway, same defensive-EN/RO-twin discipline this table's own
    # docstring commits to for every other pair, not because either was observed.
    ("creveti", "shrimp"),
    ("crevete", "shrimp"),
    ("shrimp", "shrimp"),
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
