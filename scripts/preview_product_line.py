r"""Preview `product_line` extraction on real population data (STEP A) — never the frozen gate
sample. Prints before/after pairs to stdout; writes nothing to any database or file.

    uv run python scripts/preview_product_line.py

Random sample, stratified roughly evenly across sources, plus a deliberately divergent-prefix
set hand-picked from the known-different title grammars (petmax's comma-delimited "Hrana uscata
caini, {Brand}", animax's "Hrana uscata pentru caini {Brand}" with no comma, pentruanimale's
mid-title packaging clause with no leading prefix at all) — this is the review artefact CLAUDE.md
asked for before `product_line` runs over the full table; see STATE.md/ADR-0027.
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

    print(f"seed={SEED}, {len(sample)} pairs\n")
    for source, title, brand in sample:
        result = extract_product_line(title, brand)
        print(f"[{source}] brand={brand!r}")
        print(f"  BEFORE: {title}")
        print(f"  AFTER:  {result}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
