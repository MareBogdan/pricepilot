r"""Phase 5 session 3 -- sync OUR catalogue from the mock store into `products` (ADR-0038).

    uv run python scripts/sync_catalogue.py [--dry-run]

The mock store (`services/mock_store/app.py`) is the system of record for our 30 products,
deterministic from SEED. This reads it in-process via `get_catalogue()` (no server needed,
read-only) and upserts every product into `products`, keyed on the stable `id` (the `sku` is
also unique and derived from it). Re-runnable: a second run updates in place, never duplicates.

Money stays `Decimal` end to end: the mock store holds `Decimal`, the columns are
`Numeric(12, 2)`, and nothing here touches `float`.

If `import psycopg` is blocked by Application Control (ADR-0038), run with
`PRICEPILOT_DB_DRIVER=pg8000` set -- `.env` is never edited.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from services.mock_store.app import Product as StoreProduct  # noqa: E402
from services.mock_store.app import get_catalogue  # noqa: E402
from sqlalchemy import func  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.models import Product as ProductRow  # noqa: E402

# Columns copied from the mock store. `updated_at` is set by the database, not copied.
SYNCED_FIELDS = (
    "id",
    "sku",
    "title",
    "brand",
    "category",
    "purchase_cost",
    "current_price",
    "stock",
    "net_weight_g",
)


def product_to_row(product: StoreProduct) -> dict[str, Any]:
    """Map one mock-store record to a `products` row. Pure: no I/O, no float conversion."""
    return {field: getattr(product, field) for field in SYNCED_FIELDS}


def sync(rows: list[dict[str, Any]]) -> int:
    """Upsert `rows` into `products` keyed on `id`. Returns the number of rows written."""
    stmt = pg_insert(ProductRow).values(rows)
    update_cols = {f: stmt.excluded[f] for f in SYNCED_FIELDS if f != "id"}
    stmt = stmt.on_conflict_do_update(
        index_elements=[ProductRow.id], set_={**update_cols, "updated_at": func.now()}
    )
    with session_scope() as session:
        session.execute(stmt)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print rows, write nothing")
    args = parser.parse_args()

    rows = [product_to_row(p) for p in get_catalogue()]
    if args.dry_run:
        for row in rows:
            print(row)
        print(f"dry-run: {len(rows)} rows, nothing written")
        return 0
    if not check_database():
        print("database unreachable (if psycopg is blocked, set PRICEPILOT_DB_DRIVER=pg8000)")
        return 1
    print(f"synced {sync(rows)} products")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
