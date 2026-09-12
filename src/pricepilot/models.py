"""Database schema.

Phase 0 creates only the tables that Phases 0-2 actually write to, plus the two
operational tables that CLAUDE.md §5 requires from day one (`scrape_runs`, `llm_calls`).
Tables for matching, demand and recommendations are added in their own phases so that
migrations stay small and reviewable. See DECISIONS.md ADR-0004.

Money is `Numeric(12, 2)` everywhere. Never float — CLAUDE.md §6 guardrails compare
margins and a float rounding error there is a real bug.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Product(Base):
    """Our own catalogue, mirrored from services/mock_store.

    The mock store is the system of record (it stands in for Shopify/WooCommerce);
    this table is the pipeline's local copy so joins do not require an HTTP call.
    """

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    brand: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    purchase_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    current_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScrapeRun(Base):
    """One execution of one source adapter. CLAUDE.md §5.6: every run is logged,
    and a >40% drop in items vs the previous run raises an alert instead of ingesting."""

    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_ingested: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    # "ok" | "running" | "failed" | "volume_alert"
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    listings: Mapped[list[RawListing]] = relationship(back_populates="run")


class RawListing(Base):
    """A competitor listing exactly as scraped. Append-only **across days**: one row per
    (listing, day), because the price time series *is* the data Phase 4 needs and cannot be
    backfilled. **Idempotent within a day**: a manual run and the scheduled run on the same
    calendar day upsert the same row on (source, external_id, collected_date) rather than
    duplicating it — STEP 4, ADR-0016, amending ADR-0005's original one-row-per-run design.
    """

    __tablename__ = "raw_listings"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "external_id",
            "collected_date",
            name="uq_raw_listings_source_external_collected_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("scrape_runs.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(64), index=True)
    # The shop's own internal id. Useless across shops (CLAUDE.md §7 Phase 1) but the
    # only stable handle *within* a shop, so it anchors the time series.
    source_product_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # `source_product_id` when the shop has one, else the listing URL — the same fallback the
    # petmax adapter already uses to dedupe within one run (ADR-0016). Half of the idempotency
    # key: (source, external_id, collected_date) is unique, enforced by the constraint above.
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    # The calendar day this observation belongs to (the run's start date, not scraped_at's
    # exact timestamp) — the other half of the idempotency key.
    collected_date: Mapped[date] = mapped_column(Date)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="RON")
    # Pre-discount price where the shop exposes one; drives promotion detection in Phase 4.
    compare_at_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    in_stock: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # sha256 of the normalized title. Phase 2 caches attribute extraction on this so the
    # LLM never re-runs on an unchanged title (CLAUDE.md §5 — largest cost risk).
    content_hash: Mapped[str] = mapped_column(String(64), index=True)

    run: Mapped[ScrapeRun] = relationship(back_populates="listings")


Index("ix_raw_listings_source_scraped", RawListing.source, RawListing.scraped_at)


class LlmCall(Base):
    """Every LLM call, logged by src/pricepilot/llm/client.py. No direct SDK calls exist
    anywhere else in the codebase — ruff enforces it (see pyproject.toml)."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    phase: Mapped[str] = mapped_column(String(32), index=True)
    purpose: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64), index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    # Content hash of the request. A cache hit is recorded with cost 0 so `make cost`
    # shows what caching actually saved.
    cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
