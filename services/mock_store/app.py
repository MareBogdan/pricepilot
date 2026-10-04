"""Mock store — stands in for our own shop (Shopify/WooCommerce).

It is a FIXTURE, not a feature (CLAUDE.md §7 Phase 0): a seeded catalogue, synthetic
price/sales history, and a price-update endpoint for Phase 6 tool calling to target.
No cart, no checkout, no storefront.

State is in-memory and regenerated deterministically from SEED on every start, so the
service needs no database and runs without Docker. Price updates persist for the life of
the process only — that is enough for the Phase 6 action log, which lives in Postgres.

Run:  uv run uvicorn services.mock_store.app:app --port 8001
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path, Query
from pydantic import BaseModel, Field

SEED = 20260912
HISTORY_DAYS = 180

# --------------------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------------------


class Product(BaseModel):
    id: int
    sku: str
    title: str
    brand: str
    category: Literal["dry_food", "wet_food", "treats", "litter", "grooming", "accessories"]
    net_weight_g: int | None = None
    purchase_cost: Decimal = Field(description="What we pay the distributor, RON")
    current_price: Decimal = Field(description="Our shelf price, RON")
    stock: int
    currency: Literal["RON"] = "RON"

    @property
    def margin_pct(self) -> float:
        return float((self.current_price - self.purchase_cost) / self.current_price * 100)


class HistoryPoint(BaseModel):
    day: date
    price: Decimal
    units_sold: int


class ProductHistory(BaseModel):
    product_id: int
    sku: str
    points: list[HistoryPoint]


class PriceUpdate(BaseModel):
    """Body of PATCH /products/{id}/price."""

    price: Decimal = Field(gt=0, description="New shelf price in RON")
    reason: str = Field(min_length=3, max_length=500, description="Why — stored in the audit log")


class PriceUpdateResult(BaseModel):
    product_id: int
    sku: str
    previous_price: Decimal
    new_price: Decimal
    reason: str


# --------------------------------------------------------------------------------------
# Seed data
# --------------------------------------------------------------------------------------

# (brand, line, category, net_weight_g, purchase_cost RON, retail RON)
# Deliberately includes several same-line/different-weight sets, because that is the
# dominant hard negative in Phase 3 matching (CLAUDE.md §7 Phase 1).
_CATALOGUE: list[tuple[str, str, str, int | None, str, str]] = [
    ("Orijen", "Original Dog Adult Mini", "dry_food", 1800, "119.00", "179.00"),
    ("Orijen", "Original Dog Adult Mini", "dry_food", 4500, "265.00", "389.00"),
    ("Orijen", "Original Dog Adult Mini", "dry_food", 11400, "610.00", "879.00"),
    ("Acana", "Adult Small Breed", "dry_food", 2000, "105.00", "159.00"),
    ("Acana", "Adult Small Breed", "dry_food", 6000, "275.00", "409.00"),
    ("Royal Canin", "Mini Adult", "dry_food", 2000, "68.00", "104.00"),
    ("Royal Canin", "Mini Adult", "dry_food", 8000, "225.00", "339.00"),
    ("Royal Canin", "Maxi Adult", "dry_food", 15000, "330.00", "489.00"),
    ("Purina", "Pro Plan Medium Adult", "dry_food", 3000, "82.00", "124.00"),
    ("Purina", "Pro Plan Medium Adult", "dry_food", 14000, "320.00", "469.00"),
    ("Brit", "Premium By Nature Adult Large Breed", "dry_food", 3000, "54.00", "84.00"),
    ("Brit", "Premium By Nature Adult Large Breed", "dry_food", 15000, "215.00", "319.00"),
    ("Hill's", "Science Plan Adult Medium", "dry_food", 2500, "95.00", "144.00"),
    ("Taste of the Wild", "High Prairie", "dry_food", 2000, "88.00", "134.00"),
    ("Josera", "Miniwell", "dry_food", 4500, "132.00", "199.00"),
    ("Smolke", "Medium Adult Chicken", "dry_food", 12000, "255.00", "379.00"),
    ("Bosch", "Adult Lamb & Rice", "dry_food", 3000, "72.00", "109.00"),
    ("Royal Canin", "Instinctive Cat", "wet_food", 85, "3.10", "5.20"),
    ("Purina", "Gourmet Gold Mousse", "wet_food", 85, "2.40", "4.10"),
    ("Brit", "Pate & Meat Beef", "wet_food", 400, "7.90", "12.50"),
    ("Calibra", "Joy Dog Classic Duck Strips", "treats", 80, "6.50", "11.00"),
    ("Calibra", "Joy Dog Classic Chicken Strips", "treats", 80, "6.50", "11.00"),
    ("Trixie", "Denta Fun Chicken Chewing Rings", "treats", 100, "8.20", "14.00"),
    ("Petkult", "Training Treats Salmon", "treats", 100, "7.00", "12.00"),
    ("Advance", "Cat Litter Clumping", "litter", 10000, "34.00", "56.00"),
    ("Trixie", "Silica Cat Litter", "litter", 5000, "28.00", "47.00"),
    ("Trixie", "Soft Brush Slicker", "grooming", None, "18.00", "36.00"),
    ("Trixie", "Nail Clipper Medium", "grooming", None, "14.00", "29.00"),
    ("Trixie", "Ceramic Bowl 0.3L", "accessories", None, "16.00", "34.00"),
    ("Trixie", "Nylon Collar Adjustable M", "accessories", None, "11.00", "25.00"),
]

# Category elasticity used only to shape the synthetic sales series. Phase 4 must ESTIMATE
# elasticity from the data; these are the planted ground-truth values it is graded against
# (docs/AUDIT.md concern 4). Kept here, deliberately, so the generator and the estimator
# live in different codebases.
_ELASTICITY = {
    "dry_food": -1.8,
    "wet_food": -1.4,
    "treats": -1.1,
    "litter": -1.6,
    "grooming": -0.7,
    "accessories": -0.6,
}


def _money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _build_catalogue() -> list[Product]:
    products: list[Product] = []
    for idx, (brand, line, category, weight, cost, price) in enumerate(_CATALOGUE, start=1):
        weight_tag = f"{weight}g" if weight else "std"
        sku = f"{brand[:3].upper()}-{category[:3].upper()}-{weight_tag}-{idx:03d}"
        title = f"{brand} {line}" + (f" {weight / 1000:g} kg" if weight and weight >= 1000 else "")
        if weight and weight < 1000:
            title = f"{brand} {line} {weight} g"
        products.append(
            Product(
                id=idx,
                sku=sku,
                title=title,
                brand=brand,
                category=category,
                net_weight_g=weight,
                purchase_cost=_money(float(cost)),
                current_price=_money(float(price)),
                stock=random.Random(SEED + idx).randint(0, 120),
            )
        )
    return products


def _build_history(product: Product) -> list[HistoryPoint]:
    """Synthetic price + sales series.

    Price walks around the base with occasional promotions; units are a log-linear
    response to price with weekly seasonality and Poisson-ish noise. The elasticity is
    planted (see _ELASTICITY) so Phase 4 can be scored on *recovery error*, not just MAE.
    """
    rng = random.Random(SEED * 31 + product.id)
    base_price = float(product.current_price)
    elasticity = _ELASTICITY[product.category]
    base_units = max(2.0, 400.0 / math.sqrt(base_price))
    today = date.today()
    points: list[HistoryPoint] = []
    price = base_price

    # Promotion windows are scheduled up front rather than sampled per-day. A per-day
    # coin flip can produce a product with zero promotions purely by luck, and a flat
    # price series carries no signal for Phase 4 to learn from.
    promo_days: dict[int, float] = {}
    for _ in range(rng.randint(3, 6)):
        start = rng.randrange(0, HISTORY_DAYS - 12)
        discounted = round(base_price * rng.uniform(0.78, 0.90), 2)
        for d in range(start, start + rng.randint(4, 10)):
            promo_days[d] = discounted

    for index, offset in enumerate(range(HISTORY_DAYS, 0, -1)):
        day = today - timedelta(days=offset)
        if index in promo_days:
            price = promo_days[index]
        else:
            # small random drift back toward the base price
            price = round(price + (base_price - price) * 0.25 + rng.gauss(0, base_price * 0.005), 2)
            price = max(base_price * 0.7, min(base_price * 1.15, price))

        weekday_factor = 1.15 if day.weekday() >= 5 else 1.0
        demand = base_units * (price / base_price) ** elasticity * weekday_factor
        # psychological threshold: prices ending .99/.90 sell slightly better
        if round(price % 1, 2) in (0.99, 0.90):
            demand *= 1.06
        units = max(0, int(rng.gauss(demand, math.sqrt(max(demand, 1)))))
        points.append(HistoryPoint(day=day, price=_money(price), units_sold=units))

    return points


def get_catalogue() -> list[Product]:
    """Our catalogue as built from SEED -- a fresh, deterministic copy (no server needed).

    Public accessor for pipeline code (`scripts/sync_catalogue.py`) so nothing outside this
    module reaches into `_CATALOGUE` / `_build_catalogue`. Ignores price updates applied to the
    running app: it always returns the seeded state.
    """
    return _build_catalogue()


_PRODUCTS: dict[int, Product] = {p.id: p for p in _build_catalogue()}
_HISTORY: dict[int, list[HistoryPoint]] = {p.id: _build_history(p) for p in _PRODUCTS.values()}
_AUDIT_LOG: list[PriceUpdateResult] = []

# --------------------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------------------

app = FastAPI(
    title="PricePilot Mock Store",
    version="0.1.0",
    description="Fixture standing in for our own shop. Not a storefront.",
)


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "products": len(_PRODUCTS), "history_days": HISTORY_DAYS}


@app.get("/products", response_model=list[Product])
def list_products(
    category: Annotated[str | None, Query(description="Filter by category")] = None,
    brand: Annotated[str | None, Query(description="Filter by brand")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Product]:
    items = list(_PRODUCTS.values())
    if category:
        items = [p for p in items if p.category == category]
    if brand:
        items = [p for p in items if p.brand.lower() == brand.lower()]
    return items[:limit]


@app.get("/products/{product_id}", response_model=Product)
def get_product(product_id: Annotated[int, Path(ge=1)]) -> Product:
    if product_id not in _PRODUCTS:
        raise HTTPException(status_code=404, detail=f"No product {product_id}")
    return _PRODUCTS[product_id]


@app.get("/products/{product_id}/history", response_model=ProductHistory)
def get_history(
    product_id: Annotated[int, Path(ge=1)],
    days: Annotated[int, Query(ge=1, le=HISTORY_DAYS)] = HISTORY_DAYS,
) -> ProductHistory:
    if product_id not in _PRODUCTS:
        raise HTTPException(status_code=404, detail=f"No product {product_id}")
    product = _PRODUCTS[product_id]
    return ProductHistory(
        product_id=product_id, sku=product.sku, points=_HISTORY[product_id][-days:]
    )


@app.patch("/products/{product_id}/price", response_model=PriceUpdateResult)
def update_price(product_id: Annotated[int, Path(ge=1)], update: PriceUpdate) -> PriceUpdateResult:
    """The endpoint Phase 6 tool calling targets.

    Rejects a price below purchase cost. This is the *shop's* own sanity check and is NOT
    the margin floor — that guardrail lives in our decision engine as Python, before the
    call is ever made (CLAUDE.md §6.2). Both exist on purpose.
    """
    if product_id not in _PRODUCTS:
        raise HTTPException(status_code=404, detail=f"No product {product_id}")
    product = _PRODUCTS[product_id]
    new_price = _money(float(update.price))
    if new_price <= product.purchase_cost:
        raise HTTPException(
            status_code=422,
            detail=f"Price {new_price} is at or below purchase cost {product.purchase_cost}",
        )
    previous = product.current_price
    product.current_price = new_price
    result = PriceUpdateResult(
        product_id=product_id,
        sku=product.sku,
        previous_price=previous,
        new_price=new_price,
        reason=update.reason,
    )
    _AUDIT_LOG.append(result)
    return result


@app.get("/audit-log", response_model=list[PriceUpdateResult])
def audit_log() -> list[PriceUpdateResult]:
    """Every price change this process has accepted. Phase 6 reconciles against it."""
    return _AUDIT_LOG
