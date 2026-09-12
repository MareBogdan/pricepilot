"""Schema invariants that later phases depend on."""

from __future__ import annotations

from pathlib import Path

from pricepilot.models import Base, LlmCall, RawListing, ScrapeRun

ROOT = Path(__file__).resolve().parents[1]


def test_operational_tables_exist_from_day_one() -> None:
    """CLAUDE.md §5.6 and §5.4 both require logging from the first run onwards."""
    names = set(Base.metadata.tables)
    assert {"scrape_runs", "llm_calls", "raw_listings", "products"} <= names


def test_raw_listings_is_append_only_time_series() -> None:
    """Price history cannot be backfilled, so listings must not be keyed for upsert."""
    cols = RawListing.__table__.columns
    assert not cols["scraped_at"].nullable
    assert cols["content_hash"].index, "Phase 2 caches extraction on this column"
    assert any(
        set(idx.columns.keys()) == {"source", "scraped_at"} for idx in RawListing.__table__.indexes
    )


def test_scrape_run_can_record_a_volume_alert() -> None:
    assert "status" in ScrapeRun.__table__.columns
    assert "items_found" in ScrapeRun.__table__.columns


def test_llm_calls_records_cost_and_cache_hits() -> None:
    cols = LlmCall.__table__.columns
    assert {"cost_usd", "cache_hit", "cache_key", "model", "phase"} <= set(cols.keys())


def test_migration_covers_every_model_table() -> None:
    """A model with no migration is a silent Phase-1 failure."""
    migration = (ROOT / "alembic" / "versions" / "0001_initial_schema.py").read_text(
        encoding="utf-8"
    )
    for table in Base.metadata.tables:
        assert f'"{table}"' in migration, f"{table} is missing from the initial migration"
    assert "CREATE EXTENSION IF NOT EXISTS vector" in migration
