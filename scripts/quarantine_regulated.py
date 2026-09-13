r"""One-off backfill: quarantine already-collected regulated-product rows (ADR-0025).

    uv run python scripts/quarantine_regulated.py            # report only, writes nothing
    uv run python scripts/quarantine_regulated.py --apply     # actually set excluded_reason

2026-09-13/14 diagnostic + implementation session: the tightened `is_regulated()` (line-code
tokens + diacritic folding) and animax's `product_type` cross-check catch veterinary-diet
products that the original 12-token check missed. Those products were already collected under
the old, looser rule and are sitting in `raw_listings`. CLAUDE.md §7 says regulated products are
filtered "at ingest, not later" — but for rows already ingested, "later" is now, and deleting them
would destroy real, unrecoverable price history for a filtering rule that could still need another
correction (ADR-0025's Rejected section). Quarantine instead: `raw_listings.excluded_reason`
records which signal fired, `NULL` means in scope, nothing is ever deleted.

Only touches rows where `excluded_reason IS NULL` — rerunning this script after a manual
un-flag (clearing the column by hand) will not re-flag that row; only genuinely new matches
(a token/token-set edit, or new rows since the last run) get touched.

**Never applies to Tier-B / symptom-word matches** — this script only runs the exact rule
`is_regulated()`/`regulated_match()` and animax's `product_type` check already enforce at ingest
for *new* rows; it does not carry its own, separate, broader definition of "regulated".
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

from pricepilot.db import session_scope  # noqa: E402
from pricepilot.models import RawListing  # noqa: E402
from pricepilot.scrapers.petmax import regulated_match  # noqa: E402

# animax's own classification, checked alongside the title (ADR-0025, A4). Kept here rather than
# imported from animax.py because it is a query-time property of already-stored `raw_payload`,
# not a parse-time property of a live Shopify response — the two checks share the same substring
# test, not the same code path.
PRODUCT_TYPE_VET_DIET_MARKER = "diete veterinare"


def reason_for(source: str, title: str, raw_payload: object) -> str | None:
    """The `excluded_reason` string for one row, or `None` if it is in scope.

    Both signals are checked and both are named in the reason when both fire, so a future
    reader can see exactly why a row was quarantined without re-deriving it.
    """
    reasons: list[str] = []

    token = regulated_match(title)
    if token is not None:
        reasons.append(f"title_token:{token.strip()}")

    if source == "animax_ro" and isinstance(raw_payload, dict):
        product_type = raw_payload.get("product_type")
        if isinstance(product_type, str) and PRODUCT_TYPE_VET_DIET_MARKER in product_type.lower():
            reasons.append(f"product_type:{product_type.lower()}")

    return ";".join(reasons) if reasons else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write excluded_reason; default is report-only"
    )
    args = parser.parse_args(argv)

    with session_scope() as session:
        rows = (
            session.execute(select(RawListing).where(RawListing.excluded_reason.is_(None)))
            .scalars()
            .all()
        )

        by_source_total: dict[str, int] = {}
        by_source_matched: dict[str, int] = {}
        to_update: list[tuple[RawListing, str]] = []

        for row in rows:
            by_source_total[row.source] = by_source_total.get(row.source, 0) + 1
            reason = reason_for(row.source, row.title, row.raw_payload)
            if reason is not None:
                by_source_matched[row.source] = by_source_matched.get(row.source, 0) + 1
                to_update.append((row, reason))

        print(f"rows considered (excluded_reason IS NULL): {len(rows)}")
        for source in sorted(by_source_total):
            print(
                f"  {source}: {by_source_total[source]:,} total, "
                f"{by_source_matched.get(source, 0)} newly matched"
            )
        print(f"total newly matched: {len(to_update)}")

        if not args.apply:
            print("\n--dry-run (default): nothing written. Pass --apply to quarantine these rows.")
            return 0

        for row, reason in to_update:
            row.excluded_reason = reason
        session.flush()
        print(f"\nAPPLIED: {len(to_update)} rows quarantined.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
