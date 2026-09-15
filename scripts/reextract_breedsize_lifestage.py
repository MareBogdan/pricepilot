r"""Phase 3 findings 6/7 (2026-09-15 session) — re-extract `breed_size_code` and `life_stage` for
every existing `norm_listings` row.

    uv run python scripts/reextract_breedsize_lifestage.py [--dry-run]

Narrower than a full `scripts/normalize.py` re-run: only these two fields changed this session
(`attributes.py` — "XS-XL" no longer stored as a breed-size claim; `life_stage` now carries a
trailing age qualifier like "adult+7" when the title states one). Both are pure functions of
`sample_title` alone, so this updates existing rows in place rather than re-inserting — cheap
(no LLM, no network), same discipline as `scripts/backfill_phase3_signals.py`, always recomputes
every row (no --limit-to-changed flag, for the same reason that script gives).
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.models import NormListing  # noqa: E402
from pricepilot.normalize.attributes import (  # noqa: E402
    breed_size_class,
    extract_breed_size,
    extract_life_stage,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="compute, don't write")
    args = parser.parse_args(argv)

    if not check_database():
        print("database UNREACHABLE", file=sys.stderr)
        return 2

    with session_scope() as session:
        rows = session.execute(select(NormListing)).scalars().all()
        print(f"norm_listings rows: {len(rows)}")

        breed_changed = 0
        breed_to_none = 0  # the XS-XL fix specifically
        life_changed = 0
        life_qualified = 0  # the age-qualifier fix specifically

        for row in rows:
            new_breed = extract_breed_size(row.sample_title)
            new_life = extract_life_stage(row.sample_title)
            new_class = breed_size_class(new_breed)

            if new_breed != row.breed_size_code:
                breed_changed += 1
                if row.breed_size_code == "XS-XL" and new_breed is None:
                    breed_to_none += 1
            if new_life != row.life_stage:
                life_changed += 1
                if new_life and "+" in new_life:
                    life_qualified += 1

            if not args.dry_run:
                row.breed_size_code = new_breed
                row.life_stage = new_life
                row.breed_size_class = new_class

        if not args.dry_run:
            session.flush()

    print(f"\nbreed_size_code changed: {breed_changed} (of which XS-XL -> None: {breed_to_none})")
    print(f"life_stage changed: {life_changed} (of which now age-qualified: {life_qualified})")
    print("\n--dry-run: nothing written." if args.dry_run else "\nAPPLIED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
