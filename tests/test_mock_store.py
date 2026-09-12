"""Mock store — the Phase 0 gate requires it to serve a catalogue and accept a price update."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient


def test_health(mock_store: TestClient) -> None:
    body = mock_store.get("/health").json()
    assert body["status"] == "ok"
    assert body["products"] > 0


def test_catalogue_is_seeded(mock_store: TestClient) -> None:
    products = mock_store.get("/products").json()
    assert len(products) >= 25
    skus = [p["sku"] for p in products]
    assert len(skus) == len(set(skus)), "SKUs must be unique"
    for p in products:
        assert Decimal(p["purchase_cost"]) < Decimal(p["current_price"]), p["sku"]
        assert p["stock"] >= 0


def test_catalogue_contains_same_line_different_weight(mock_store: TestClient) -> None:
    """The dominant hard negative in Phase 3 must exist in our own catalogue too,
    otherwise the matching evaluation has nothing realistic to resolve against."""
    products = mock_store.get("/products").json()
    orijen = [p for p in products if p["brand"] == "Orijen"]
    weights = {p["net_weight_g"] for p in orijen}
    assert len(weights) >= 3, "expected several weights of the same Orijen line"


def test_filters(mock_store: TestClient) -> None:
    treats = mock_store.get("/products", params={"category": "treats"}).json()
    assert treats and all(p["category"] == "treats" for p in treats)
    assert mock_store.get("/products", params={"limit": 3}).json().__len__() == 3


def test_history_shape(mock_store: TestClient) -> None:
    body = mock_store.get("/products/1/history", params={"days": 30}).json()
    assert body["product_id"] == 1
    assert len(body["points"]) == 30
    days = [p["day"] for p in body["points"]]
    assert days == sorted(days), "history must be chronological"
    assert all(p["units_sold"] >= 0 for p in body["points"])
    assert any(p["units_sold"] > 0 for p in body["points"]), "a flat-zero series is a bug"


def test_history_contains_promotions(mock_store: TestClient) -> None:
    """Phase 4 needs visible promotion events; a series with no price variation is useless."""
    for product_id in (1, 5, 12, 21):
        points = mock_store.get(f"/products/{product_id}/history").json()["points"]
        prices = [Decimal(p["price"]) for p in points]
        assert min(prices) < max(prices) * Decimal("0.95"), f"no promotion for {product_id}"


def test_price_update_roundtrip(mock_store: TestClient) -> None:
    before = mock_store.get("/products/1").json()
    new_price = round(float(before["current_price"]) * 0.97, 2)
    resp = mock_store.patch(
        "/products/1/price", json={"price": new_price, "reason": "competitor undercut"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert Decimal(body["previous_price"]) == Decimal(before["current_price"])
    assert Decimal(body["new_price"]) == Decimal(str(new_price))
    assert Decimal(mock_store.get("/products/1").json()["current_price"]) == Decimal(str(new_price))
    assert any(e["product_id"] == 1 for e in mock_store.get("/audit-log").json())


def test_price_below_cost_is_rejected(mock_store: TestClient) -> None:
    product = mock_store.get("/products/2").json()
    resp = mock_store.patch(
        "/products/2/price",
        json={"price": float(product["purchase_cost"]) - 1, "reason": "should be rejected"},
    )
    assert resp.status_code == 422


def test_price_update_requires_a_reason(mock_store: TestClient) -> None:
    assert mock_store.patch("/products/3/price", json={"price": 10.0}).status_code == 422


def test_unknown_product(mock_store: TestClient) -> None:
    assert mock_store.get("/products/9999").status_code == 404
    assert mock_store.get("/products/9999/history").status_code == 404
