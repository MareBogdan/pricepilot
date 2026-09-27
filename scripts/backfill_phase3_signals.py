r"""Phase 3 STEP 3 — backfill `category`, `brand_blocking_key`, `brand_is_distributor_code`,
`species`, `breed_size_class` (the last two: finding 4/5, 2026-09-15 session, migration 0008).

    uv run python scripts/backfill_phase3_signals.py [--dry-run]

Separate from `scripts/normalize.py` deliberately: `category`/`species` need `url` and
`raw_payload`, which the deterministic `extract()` pipeline never reads (title-only, ADR-0026).
`breed_size_class` doesn't need either (it's a pure function of `breed_size_code`, itself
title-only) but is backfilled here anyway, for one consistent run instead of two. Joins each
`norm_listings` row back to one representative `raw_listings` row by `content_hash` to get the
two fields the title-only pipeline never sees.

Idempotent, not cached by content_hash the way `extract()` is: these three signals are cheap
lookups/regexes, not LLM calls, so re-running to pick up a rule change costs nothing worth
guarding against. Always recomputes every row (no --limit-to-null flag) for that reason.
"""

from __future__ import annotations

import argparse
import io
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.models import NormListing, RawListing  # noqa: E402
from pricepilot.normalize.attributes import breed_size_class  # noqa: E402
from pricepilot.normalize.brand import (  # noqa: E402
    brand_blocking_key,
    is_suspected_distributor_code,
)
from pricepilot.normalize.category import categorize_listing  # noqa: E402
from pricepilot.normalize.species import classify_species  # noqa: E402
from pricepilot.scrapers.runner import get_payload  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="compute, don't write")
    args = parser.parse_args(argv)

    if not check_database():
        print("database UNREACHABLE", file=sys.stderr)
        return 2

    with session_scope() as session:
        norm_rows = session.execute(select(NormListing)).scalars().all()
        print(f"norm_listings rows: {len(norm_rows)}")

        content_hashes = [r.content_hash for r in norm_rows]
        raw_by_hash: dict[str, tuple[str, str, str, date]] = {}
        # One representative raw_listings row per content_hash (source, url) — the same
        # "first-encountered" choice `scripts/normalize.py`/`draw_gate_sample.py` already make,
        # via ORDER BY id. `url` is a real column (unaffected by payload dedup); `raw_payload`
        # itself may be NULL on this exact row (ADR-0032), so it is resolved via get_payload
        # below rather than trusted directly -- see normalize.py for why "first row per
        # content_hash" does not guarantee a non-NULL payload.
        raw_rows = session.execute(
            select(
                RawListing.content_hash,
                RawListing.source,
                RawListing.url,
                RawListing.external_id,
                RawListing.collected_date,
            )
            .where(RawListing.content_hash.in_(content_hashes))
            .order_by(RawListing.id)
        ).all()
        for content_hash, source, url, external_id, collected_date in raw_rows:
            raw_by_hash.setdefault(content_hash, (source, url, external_id, collected_date))

        category_counts: dict[str | None, int] = {}
        species_counts: dict[str | None, int] = {}
        distributor_count = 0
        missing_raw = 0

        for row in norm_rows:
            raw = raw_by_hash.get(row.content_hash)
            if raw is None:
                missing_raw += 1
                continue
            source, url, external_id, collected_date = raw
            raw_payload = get_payload(session, source, external_id, collected_date)
            payload = raw_payload if isinstance(raw_payload, dict) else None

            category = categorize_listing(source, url, payload, row.sample_title)
            species = classify_species(source, url, payload, row.sample_title, category)
            key = brand_blocking_key(row.brand)
            is_distributor = is_suspected_distributor_code(row.brand)
            size_class = breed_size_class(row.breed_size_code)

            category_counts[category] = category_counts.get(category, 0) + 1
            species_counts[species] = species_counts.get(species, 0) + 1
            if is_distributor:
                distributor_count += 1

            if not args.dry_run:
                row.category = category
                row.species = species
                row.brand_blocking_key = key
                row.brand_is_distributor_code = is_distributor
                row.breed_size_class = size_class

        if not args.dry_run:
            session.flush()

    print(f"\nmissing raw_listings match: {missing_raw}")
    print("\ncategory distribution:")
    for cat, n in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat!r}: {n}")
    print("\nspecies distribution:")
    for sp, n in sorted(species_counts.items(), key=lambda x: -x[1]):
        print(f"  {sp!r}: {n}")
    print(f"\nbrand_is_distributor_code = True: {distributor_count}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
    else:
        print("\nAPPLIED.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
