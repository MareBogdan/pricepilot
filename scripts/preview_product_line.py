r"""Preview `product_line` extraction on real population data (STEP A, extended STEP 1
2026-09-14) — never the frozen gate sample. Prints before/after pairs to stdout; writes nothing
to any database or file.

    uv run python scripts/preview_product_line.py

Random sample, stratified roughly evenly across sources, plus two deliberately hand-picked sets:
(1) a divergent-prefix set from the known-different title grammars (petmax's comma-delimited
"Hrana uscata caini, {Brand}", animax's "Hrana uscata pentru caini {Brand}" with no comma,
pentruanimale's mid-title packaging clause with no leading prefix at all); (2) STEP 1's own
acceptance-test pairs — brand-field fragmentation (1a: Brit/Brit Premium/Brit Care/Brit Fresh,
Calibra's Life/Premium/Expert, Hill's/HILL'S Science Plan, printed petmax-vs-pentruanimale
side by side) and the dangling-token guard (1b: the "diametru" bowl titles, plus real "cu
{flavour}"-leading cases the guard also fixes) — this is the review artefact CLAUDE.md asked for
before `product_line` runs over the full table; see STATE.md/DECISIONS.md ADR-0027.
"""

from __future__ import annotations

import io
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.models import RawListing  # noqa: E402
from pricepilot.normalize.product_line import extract_product_line  # noqa: E402
from pricepilot.overlap import strip_diacritics  # noqa: E402

SEED = 20260916
PER_SOURCE_RANDOM = 8

# Hand-picked because they're the known-most-divergent prefix conventions across sources — not
# themselves random, but everything they're drawn from is the real in-scope population.
DIVERGENT_HINTS: dict[str, tuple[str, ...]] = {
    "petmax_ro": ("hrana uscata caini,", "recompense delicioase pentru", "hrana umeda pisici,"),
    "animax_ro": ("hrana uscata pentru caini", "recompensa pentru caini", "hrana umeda pentru"),
    "pentruanimale_ro": ("conserva hrana umeda", "plic hrana umeda", "galetusa recompense"),
}


# STEP 1a: real petmax/pentruanimale pairs verified in this session's own DB query (raw
# `raw_payload->>'brand'` grouped by source, in-scope only) — each pair names, on both shops, the
# same manufacturer's sub-line family the 2026-09-13 diagnostic documented as fragmenting.
_STEP_1A_PAIRS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "Brit / Brit Premium": (
        (
            "petmax_ro",
            "Hrana uscata pentru caini Brit Premium by Nature Junior XL 15 kg",
            "Brit Premium",
        ),
        (
            "pentruanimale_ro",
            "BRIT Premium By Nature Adult Large Breed, L, Pui, hrană uscată câini",
            "BRIT",
        ),
    ),
    "Calibra Life / Premium / Expert": (
        (
            "petmax_ro",
            "Hrana umeda caini, Calibra Dog Life Turkey with Apples 400 g",
            "Calibra Life",
        ),
        (
            "petmax_ro",
            "Hrana umeda caini, Calibra Dog Premium Can with Veal & Chicken 1240 g",
            "Calibra Premium",
        ),
        (
            "petmax_ro",
            "Hrana uscata caini, Calibra Dog Expert+ Adult Mobility & Joint Support 2 kg",
            "Calibra Expert",
        ),
        (
            "pentruanimale_ro",
            "CALIBRA Premium Line, Miel și Pasăre, plic hrană umedă pisici, (în suc propriu), 100g",
            "CALIBRA",
        ),
    ),
    "Hill's / HILL'S Science Plan": (
        ("petmax_ro", "Hill's Pet Nutrition Adult Chicken 12 kg", "Hill's Pet Nutrition"),
        ("pentruanimale_ro", "HILL'S Science Plan Adult Chicken 12 kg", "HILL'S Science Plan"),
    ),
}

# STEP 1b: real titles found in this session by comparing pre-guard vs post-guard output over
# the full population (260 titles changed; these are representative of the two shapes found —
# an orphaned mid-string qualifier once its own quantity is excised, and a leading "cu {word}"
# connective left dangling once the clause immediately before it is gone).
_STEP_1B_TITLES: tuple[tuple[str, str | None], ...] = (
    ("Bol pentru hrană animale, inox, diametru 2 l, 25 cm, Negru Agility", "Agility"),
    ("Bol pentru hrană animale, inox, diametru 1.5 l, 21 cm, Rosu/Negru Agility", "Agility"),
    (
        "Bol pentru hrană animale, inox, diametru, PC-1008C, 750 ml, 16 cm, Roșu/Negru Agility",
        "Agility",
    ),
    ("Skipper cu Vita, 850 g", "Skipper"),
    ("Skipper cu Pui, 415 g", "Skipper"),
    (
        "Hrana uscata pentru caini de talie mica si mini Pure Nurture Grainfree, cu somon si "
        "mazare, 2kg",
        "Pure Nurture",
    ),
    ("Hrana uscata pentru caini cu Ton Dog&Dog Expert Premium Ingrijire Peste-Top 3 kg", "DOG&DOG"),
    ("Hrana uscata pentru caini cu Pui Dog&Dog Premium Intretinere fizica 3 kg", "DOG&DOG"),
)


def main() -> int:
    if not check_database():
        print("database UNREACHABLE — run `docker compose up -d db`", file=sys.stderr)
        return 2

    with session_scope() as session:
        rows = session.execute(
            select(RawListing.source, RawListing.title, RawListing.raw_payload).where(
                RawListing.excluded_reason.is_(None)
            )
        ).all()

    by_source: dict[str, list[tuple[str, object]]] = {}
    for source, title, payload in rows:
        brand = (payload or {}).get("brand") if isinstance(payload, dict) else None
        by_source.setdefault(source, []).append((title, brand))

    rng = random.Random(SEED)
    sample: list[tuple[str, str, str | None]] = []
    seen_titles: set[str] = set()
    for source, items in by_source.items():
        for title, brand in rng.sample(items, min(PER_SOURCE_RANDOM, len(items))):
            sample.append((source, title, brand if isinstance(brand, str) else None))
            seen_titles.add(title)

    for source, hints in DIVERGENT_HINTS.items():
        for hint in hints:
            for title, brand in by_source[source]:
                if title in seen_titles:
                    continue
                if hint in strip_diacritics(title.lower()):
                    sample.append((source, title, brand if isinstance(brand, str) else None))
                    seen_titles.add(title)
                    break

    print(f"seed={SEED}, {len(sample)} random/divergent pairs\n")
    for source, title, brand in sample:
        result = extract_product_line(title, brand)
        print(f"[{source}] brand={brand!r}")
        print(f"  BEFORE: {title}")
        print(f"  AFTER:  {result}")
        print()

    print("=" * 70)
    print("STEP 1a acceptance test — brand-field fragmentation, petmax vs pentruanimale,")
    print("same product family, printed side by side (must share the sub-line, not fragment it)")
    print("=" * 70)
    print()
    for brand_family, pairs in _STEP_1A_PAIRS.items():
        print(f"-- {brand_family} --")
        for source, title, brand in pairs:
            result = extract_product_line(title, brand)
            print(f"  [{source}] brand={brand!r}")
            print(f"    BEFORE: {title}")
            print(f"    AFTER:  {result}")
        print()

    print("=" * 70)
    print("STEP 1b acceptance test — dangling-token guard, real titles where it fires")
    print("=" * 70)
    print()
    for title, brand in _STEP_1B_TITLES:
        result = extract_product_line(title, brand)
        print(f"  brand={brand!r}")
        print(f"    BEFORE: {title}")
        print(f"    AFTER:  {result}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
