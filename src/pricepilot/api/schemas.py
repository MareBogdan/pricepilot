"""Response models for the read-only dashboard API.

Money is `Decimal` (serialised as a string by pydantic v2), never float. Every number here comes
from a SQL query or `config/pricing-policy.toml`; the fields named `*_synthetic` / `*_placeholder`
say out loud what is simulated.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class ProductRow(BaseModel):
    id: int
    sku: str
    title: str
    brand: str
    category: str
    cost: Decimal
    current_price: Decimal
    margin_pct: Decimal | None  # (price - cost) / price * 100; None if price/cost is corrupt
    margin_floor_pct: Decimal  # the policy floor for the category, from config
    stock: int
    matches: int
    guard_status: str | None  # of the latest real recommendation; None = none yet


class MatchRow(BaseModel):
    shop: str
    competitor_title: str
    price: Decimal
    score: Decimal
    threshold: Decimal
    price_date: date
    in_stock: bool | None
    url: str | None  # None unless http(s): scraped URLs are untrusted


class PricePosition(BaseModel):
    """Where our price sits against the matched competitors (None when there are none)."""

    our_price: Decimal
    competitors: int
    min: Decimal | None
    median: Decimal | None
    max: Decimal | None
    vs_min_pct: Decimal | None
    vs_median_pct: Decimal | None


class PolicyPassage(BaseModel):
    section_ref: str
    similarity: float
    heading: str | None
    text: str | None


class RecommendationOut(BaseModel):
    id: int
    created_at: datetime
    run_label: str
    scenario: str | None
    llm_model: str
    proposed_price: Decimal | None
    rationale: str | None
    guard_status: str
    guard_final_price: Decimal | None
    guard_reason: str | None
    cost: Decimal
    current_price: Decimal
    margin_floor_pct: Decimal
    proposed_margin_pct: Decimal | None
    final_margin_pct: Decimal | None
    rag_sections: list[PolicyPassage]
    competitor_prices: list[dict[str, Any]]
    price_7d_ago: Decimal | None
    price_7d_ago_source: str
    elasticity_placeholder: dict[str, Any]
    llm_cost_usd: Decimal
    llm_latency_ms: int | None


class StressTest(BaseModel):
    """A guard stress-test row: the competitor prices were perturbed on purpose (synthetic)."""

    scenario: str
    proposed_price: Decimal | None
    guard_status: str
    guard_final_price: Decimal | None
    guard_reason: str | None


class ProductDetail(BaseModel):
    product: ProductRow
    floor_price: Decimal  # lowest price that still clears the category margin floor
    matches: list[MatchRow]
    position: PricePosition
    recommendation: RecommendationOut | None
    stress_tests: list[StressTest]


class OurPricePoint(BaseModel):
    day: date
    price: Decimal
    units_sold: int


class CompetitorSeries(BaseModel):
    shop: str
    points: list[tuple[date, Decimal]]


class PriceHistory(BaseModel):
    product_id: int
    our_price_synthetic: list[OurPricePoint]
    our_price_note: str
    competitors_real: list[CompetitorSeries]
    competitors_note: str


class SourceStatus(BaseModel):
    source: str
    in_scope_listings: int  # distinct listings (source + external id)
    price_observations: int  # one row per listing per collection day
    collection_days: int
    last_run_status: str | None
    last_run_at: datetime | None


class MatcherFacts(BaseModel):
    model: str
    threshold: Decimal | None
    links: int
    products_with_link: int
    precision_pre_guard: str
    precision_post_guard: str
    precision_caveat: str


class PhaseState(BaseModel):
    phase: str
    state: str


class Status(BaseModel):
    database: bool
    collection_days: int | None
    first_day: date | None
    last_day: date | None
    in_scope_listings: int | None  # distinct listings
    price_observations: int | None
    sources: list[SourceStatus]
    products: int | None
    recommendations_real: dict[str, int]
    matcher: MatcherFacts
    phases: list[PhaseState]
    real_vs_simulated: list[dict[str, str]]
