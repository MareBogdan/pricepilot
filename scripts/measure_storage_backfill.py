"""Storage measurement for the ADR-0032 payload-dedup fix (READ-ONLY, no DB write of any kind).

Reports (Part A step 1 and step 6 of prompt-storage-and-rule-v2.md):
  a. Current table/index sizes, and how many bytes `raw_payload` accounts for within
     `raw_listings` (`pg_column_size` sum).
  b. Backfill potential: replaying the exact ingest dedup decision
     (`pricepilot.scrapers.runner.resolve_payload_for_storage`) over every EXISTING row in id
     order, per (source, external_id) -- how many bytes would be freed if a one-off backfill
     nulled the payloads that decision would already have nulled had it been running from day 1.
     This is a report only. Nothing is written; the backfill itself is a separate, later,
     destructive decision (docs/learned/storage-dedup.md).

Run:  .venv\\Scripts\\python scripts/measure_storage_backfill.py
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT_FILE = ROOT / "docs" / "learned" / "results" / "phase4" / "storage-backfill.json"


def measure(neon_limit_mb: float | None, neon_limit_url: str | None) -> dict[str, Any]:
    from sqlalchemy import text

    from pricepilot.db import connect_with_wakeup_retry, get_engine
    from pricepilot.scrapers.runner import resolve_payload_for_storage

    conn = connect_with_wakeup_retry(get_engine())
    try:
        conn.execute(text("SET TRANSACTION READ ONLY"))

        db_size = conn.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
        tables = conn.execute(
            text(
                "SELECT c.relname, pg_total_relation_size(c.oid) AS total_bytes, "
                "pg_relation_size(c.oid) AS table_bytes "
                "FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace "
                "WHERE c.relkind = 'r' AND ns.nspname = 'public' "
                "ORDER BY total_bytes DESC LIMIT 5"
            )
        ).all()
        indexes = conn.execute(
            text(
                "SELECT indexrelname, pg_relation_size(indexrelid) AS bytes "
                "FROM pg_stat_user_indexes WHERE relname = 'raw_listings' "
                "ORDER BY bytes DESC"
            )
        ).all()
        payload_bytes = conn.execute(
            text(
                "SELECT count(*), "
                "coalesce(sum(pg_column_size(raw_payload)), 0), "
                "coalesce(sum(pg_column_size(raw_payload)) FILTER (WHERE raw_payload IS NOT NULL), 0) "
                "FROM raw_listings"
            )
        ).one()
        row_count, payload_bytes_all_rows, payload_bytes_nonnull_rows = payload_bytes
        days_union = conn.execute(
            text("SELECT count(DISTINCT collected_date) FROM raw_listings")
        ).scalar_one()

        # Replay the exact ingest decision over every existing row, in id order per listing, to
        # find out how many of those bytes a one-off backfill (nulling what ingest would already
        # have nulled) would free. Loads (source, external_id, collected_date, id, raw_payload,
        # pg_column_size(raw_payload)) -- 104 MB today, fits comfortably in memory for a one-off
        # report.
        rows = conn.execute(
            text(
                "SELECT source, external_id, collected_date, id, raw_payload, "
                "pg_column_size(raw_payload) AS payload_bytes "
                "FROM raw_listings ORDER BY source, external_id, collected_date, id"
            )
        ).all()
    finally:
        conn.rollback()
        conn.close()

    per_listing: dict[tuple[str, str], list[tuple[Any, Any, dict[str, Any] | None, int]]] = (
        defaultdict(list)
    )
    for source, external_id, collected_date, _id, payload, pbytes in rows:
        per_listing[(source, external_id)].append((collected_date, _id, payload, pbytes or 0))

    freeable_bytes = 0
    freeable_rows = 0
    already_null_rows = 0
    for entries in per_listing.values():
        prev_hash: str | None = None
        for _collected_date, _id, payload, pbytes in entries:
            if payload is None:
                already_null_rows += 1
                continue  # nothing to free; this row already carries no payload
            stored_payload, new_hash = resolve_payload_for_storage(payload, prev_hash)
            if stored_payload is None:
                freeable_bytes += pbytes
                freeable_rows += 1
            prev_hash = new_hash

    raw_total_bytes = next(
        (int(total) for name, total, _tbl in tables if name == "raw_listings"), None
    )
    rows_per_collection_day = (row_count / days_union) if days_union else None
    growth: dict[str, Any] = {
        "note": "ESTIMATE: projects raw_listings' per-row physical footprint (indexes + heap, "
        "pg_total_relation_size) minus today's payload bytes per row, assuming the dedup fix "
        "nulls virtually all repeat-day payloads going forward (D2 in price-movement.json shows "
        "the new-listing rate -- the only source of a full payload after day 1 -- is a handful "
        "per source per day).",
        "collection_days_union": int(days_union) if days_union else None,
        "rows_per_collection_day_ESTIMATE": rows_per_collection_day,
    }
    if raw_total_bytes and rows_per_collection_day and row_count:
        avg_total_bytes_per_row = raw_total_bytes / row_count
        avg_payload_bytes_per_row = payload_bytes_all_rows / row_count
        avg_nonpayload_bytes_per_row = avg_total_bytes_per_row - avg_payload_bytes_per_row
        new_daily_growth = rows_per_collection_day * avg_nonpayload_bytes_per_row
        growth["avg_raw_listings_bytes_per_row_today"] = avg_total_bytes_per_row
        growth["avg_payload_bytes_per_row_today"] = avg_payload_bytes_per_row
        growth["projected_new_daily_growth_bytes_ESTIMATE"] = new_daily_growth
        if neon_limit_mb is not None and neon_limit_url:
            remaining = neon_limit_mb * 1024 * 1024 - db_size
            days_left = remaining / new_daily_growth if new_daily_growth else None
            growth["neon_free_tier_limit_mb"] = neon_limit_mb
            growth["neon_limit_source_url"] = neon_limit_url
            if days_left is not None:
                growth["days_until_limit_with_dedup_ESTIMATE"] = days_left
                growth["limit_hit_date_with_dedup_ESTIMATE"] = (
                    datetime.now(UTC).date() + timedelta(days=days_left)
                ).isoformat()

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "database_bytes": int(db_size),
        "top5_tables": [
            {"table": name, "total_bytes": int(total), "table_bytes": int(tbl)}
            for name, total, tbl in tables
        ],
        "raw_listings_indexes": [{"index": name, "bytes": int(b)} for name, b in indexes],
        "raw_listings_row_count": int(row_count),
        "raw_payload_bytes_all_rows": int(payload_bytes_all_rows),
        "raw_payload_bytes_nonnull_rows_today": int(payload_bytes_nonnull_rows),
        "already_null_payload_rows_today": already_null_rows,
        "backfill_potential": {
            "note": "ESTIMATE: replays resolve_payload_for_storage over existing rows; a real "
            "backfill is a separate, later, destructive decision, not run here.",
            "rows_that_would_be_nulled": freeable_rows,
            "bytes_freeable": freeable_bytes,
            "mb_freeable": round(freeable_bytes / 1e6, 1),
        },
        "projected_growth_after_dedup": growth,
    }
    return report


def print_report(rep: dict[str, Any]) -> None:
    print(f"Storage / backfill measurement  {rep['generated_at']}")
    print(f"database {rep['database_bytes'] / 1e6:.1f} MB")
    for t in rep["top5_tables"]:
        print(
            f"   {t['table']}: total {t['total_bytes'] / 1e6:.1f} MB, table {t['table_bytes'] / 1e6:.1f} MB"
        )
    print("raw_listings indexes:")
    for ix in rep["raw_listings_indexes"]:
        print(f"   {ix['index']}: {ix['bytes'] / 1e6:.1f} MB")
    print(
        f"raw_listings rows: {rep['raw_listings_row_count']:,}; raw_payload bytes (all rows, "
        f"NULL counts as 0): {rep['raw_payload_bytes_all_rows'] / 1e6:.1f} MB; already-NULL "
        f"payload rows today: {rep['already_null_payload_rows_today']:,}"
    )
    bp = rep["backfill_potential"]
    print(
        f"backfill potential (ESTIMATE, not applied): {bp['rows_that_would_be_nulled']:,} rows, "
        f"{bp['mb_freeable']:.1f} MB freeable"
    )
    g = rep["projected_growth_after_dedup"]
    if "projected_new_daily_growth_bytes_ESTIMATE" in g:
        print(
            f"projected growth/collection day WITH dedup (ESTIMATE): "
            f"{g['projected_new_daily_growth_bytes_ESTIMATE'] / 1e6:.2f} MB "
            f"(rows/day {g['rows_per_collection_day_ESTIMATE']:.0f})"
        )
        if "limit_hit_date_with_dedup_ESTIMATE" in g:
            print(
                f"   Neon free-tier limit {g['neon_free_tier_limit_mb']} MB: "
                f"{g['limit_hit_date_with_dedup_ESTIMATE']} (ESTIMATE)"
            )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--neon-limit-mb", type=float, default=None)
    ap.add_argument("--neon-limit-url", type=str, default=None)
    args = ap.parse_args()
    rep = measure(args.neon_limit_mb, args.neon_limit_url)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(rep, indent=2, default=str) + "\n", encoding="utf-8")
    print_report(rep)
    print(f"\nwritten: {OUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
