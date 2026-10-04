"""Phase 5 session 3: mock-store record -> `products` row mapping (ADR-0038). Pure logic, no DB."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from services.mock_store.app import Product as StoreProduct
from services.mock_store.app import get_catalogue

from sync_catalogue import SYNCED_FIELDS, product_to_row


def test_weighted_product_maps_exact_values() -> None:
    row = product_to_row(get_catalogue()[0])
    assert row == {
        "id": 1,
        "sku": "ORI-DRY-1800g-001",
        "title": "Orijen Original Dog Adult Mini 1.8 kg",
        "brand": "Orijen",
        "category": "dry_food",
        "purchase_cost": Decimal("119.00"),
        "current_price": Decimal("179.00"),
        "stock": 12,  # random.Random(SEED + 1).randint(0, 120), deterministic
        "net_weight_g": 1800,
    }
    assert isinstance(row["purchase_cost"], Decimal) and isinstance(row["current_price"], Decimal)


def test_unweighted_product_keeps_null_weight() -> None:
    grooming = next(p for p in get_catalogue() if p.category == "grooming")
    assert product_to_row(grooming)["net_weight_g"] is None


def test_whole_catalogue_maps_with_decimal_money_and_unique_keys() -> None:
    products: list[StoreProduct] = get_catalogue()
    rows = [product_to_row(p) for p in products]
    assert len(rows) == 30
    assert len({r["sku"] for r in rows}) == 30
    assert all(set(r) == set(SYNCED_FIELDS) for r in rows)
    assert all(type(r["purchase_cost"]) is Decimal for r in rows)
    assert all(r["current_price"] > r["purchase_cost"] for r in rows)
