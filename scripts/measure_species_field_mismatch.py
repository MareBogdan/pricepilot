r"""Phase 3 finding (DECISIONS.md ADR-0028 addendum #13, TASK 5) -- measures class (e) of
`scripts/check_label_rule_consistency.py` over the WHOLE `norm_listings` population, not just the
997-row frozen annotation queue: how many listings have a title that clearly states one species
("pentru pisici", "caini", ...) while the stored `species` field says the other.

    uv run python scripts/measure_species_field_mismatch.py

This is a REPORT, not a fix (Phase 2 is closed; CLAUDE.md's own rule is that a closed phase's
defect becomes a recorded finding, not a reopening). It never writes to `norm_listings` and never
changes `normalize/species.py`.

Uses the SAME title-keyword test as class (e) (`pricepilot.normalize.species._from_title`) --
this is deliberate: the finding is "the stored field disagrees with the title using the tool's own
keyword test", not a new or stricter test invented for this report.
"""

from __future__ import annotations

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
from pricepilot.models import NormListing  # noqa: E402
from pricepilot.normalize.species import _from_title  # noqa: E402


def main() -> int:
    if not check_database():
        print(
            "database UNREACHABLE -- falling back to the frozen queue's 1,994 listing rows is "
            "NOT done automatically by this script (that fallback is a documented, explicit "
            "limitation, not a silent substitute for the full population). Start the database "
            "and re-run.",
            file=sys.stderr,
        )
        return 2

    with session_scope() as session:
        rows = session.execute(
            select(
                NormListing.content_hash,
                NormListing.sample_title,
                NormListing.sample_source,
                NormListing.species,
            )
        ).all()

    total = len(rows)
    mismatches: list[tuple[str, str, str, str, str]] = []
    for content_hash, title, source, field_species in rows:
        title_species = _from_title(title)
        if title_species and field_species and title_species != field_species:
            mismatches.append((content_hash, title, source, title_species, field_species))

    by_source: Counter[str] = Counter(m[2] for m in mismatches)

    print(f"norm_listings population: {total:,} rows")
    print(
        f"title/field species mismatches: {len(mismatches)} ({len(mismatches) / total * 100:.2f}%)"
    )
    print(f"by source: {dict(sorted(by_source.items()))}")
    print()
    for content_hash, title, source, title_species, field_species in mismatches:
        print(
            f"  {content_hash[:12]}... [{source}]  title says {title_species!r}, "
            f"field says {field_species!r}"
        )
        print(f"    {title}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
