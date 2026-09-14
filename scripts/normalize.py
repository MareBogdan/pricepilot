r"""Populate `norm_listings` from `raw_listings` (STEP 3/4, Phase 2, ADR-0026).

    uv run python scripts/normalize.py              # extract + insert, report only
    uv run python scripts/normalize.py --dry-run     # extract + report, write nothing

The only script that touches `norm_listings`. `src/pricepilot/normalize/` is pure — title text
in, a typed result out, nothing read from or written to the database — so every DB interaction
(the cache check, the insert) lives here, in one place, matching how `scripts/scrape.py` is the
only thing that writes `raw_listings`.

**Caches by content_hash — CLAUDE.md §5.1's rule, extended to deterministic extraction too.**
Even though this extraction is free (no LLM, no API spend), re-running it on every title on every
invocation would still be wasted work and would defeat the point of `content_hash` being the
cache key (ADR-0026): only rows whose `content_hash` has no existing `norm_listings` row are
extracted. Re-running this script after a title's extraction logic changes requires deleting the
stale rows by hand first (or bumping `EXTRACTOR_VERSION` and querying by it) — not done
automatically, so a rule change doesn't silently reprocess everything not yet clearly listed.
"""

from __future__ import annotations

import argparse
import io
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.models import NormListing, RawListing  # noqa: E402
from pricepilot.normalize import extract  # noqa: E402

# Bumped when extraction logic changes materially. Not read by this script's cache check today
# (the cache check is purely "does a norm_listings row exist for this content_hash") — recorded
# per-row so a future session can decide whether a rule change is worth re-running against rows
# that predate it, per the module docstring above.
EXTRACTOR_VERSION = "2026-09-14-v4"  # v4: STEP 1 product_line wired in (1a brand-span fix, 1b
# dangling-token guard); convention 6 tests added (no code change); convention 7 breed_size
# accessory-context guard added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="extract and report; write nothing")
    args = parser.parse_args(argv)

    if not check_database():
        print("database UNREACHABLE — run `docker compose up -d db`", file=sys.stderr)
        return 2

    with session_scope() as session:
        raw_rows = session.execute(
            select(
                RawListing.source,
                RawListing.title,
                RawListing.content_hash,
                RawListing.raw_payload,
            )
            .where(RawListing.excluded_reason.is_(None))
            .order_by(RawListing.id)
        ).all()

        existing_hashes = set(session.execute(select(NormListing.content_hash)).scalars().all())

        # One representative row per content_hash — the first one encountered (lowest id, per
        # the ORDER BY above), matching `scripts/draw_gate_sample.py`'s same dedup choice.
        by_hash: dict[str, tuple[str, str, object]] = {}
        for source, title, content_hash, raw_payload in raw_rows:
            by_hash.setdefault(content_hash, (source, title, raw_payload))

        to_extract = {h: v for h, v in by_hash.items() if h not in existing_hashes}

        print(f"in-scope rows: {len(raw_rows):,}")
        print(f"distinct content_hash: {len(by_hash):,}")
        print(f"already in norm_listings (cached, skipped): {len(existing_hashes):,}")
        print(f"new to extract: {len(to_extract):,}")

        error_field_counts: Counter[str] = Counter()
        inserted = 0
        for content_hash, (source, title, raw_payload) in to_extract.items():
            source_brand = raw_payload.get("brand") if isinstance(raw_payload, dict) else None
            result = extract(title, source_brand if isinstance(source_brand, str) else None)
            for field_name in result.errors:
                error_field_counts[field_name] += 1

            if args.dry_run:
                continue

            session.add(
                NormListing(
                    content_hash=content_hash,
                    sample_source=source,
                    sample_title=title,
                    brand=result.brand,
                    product_line=result.product_line,
                    net_weight_g=result.net_weight_g,
                    net_volume_ml=result.net_volume_ml,
                    pack_count=result.pack_count,
                    bonus_weight_g=result.bonus_weight_g,
                    breed_size_code=result.breed_size_code,
                    life_stage=result.life_stage,
                    flavour=result.flavour,
                    food_form=result.food_form,
                    dosage_band=result.dosage_band,
                    extraction_status="error" if result.errors else "ok",
                    extraction_errors=result.errors or None,
                    extractor_version=EXTRACTOR_VERSION,
                )
            )
            inserted += 1

        if args.dry_run:
            print("\n--dry-run: nothing written.")
        else:
            session.flush()
            print(f"\nAPPLIED: {inserted} rows inserted into norm_listings.")

        if error_field_counts:
            print("\nextraction_errors by field (extractor raised, not just absent):")
            for field_name, count in error_field_counts.most_common():
                print(f"  {field_name}: {count}")
        else:
            print("\nno extraction errors — every extractor ran clean on every new title.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
