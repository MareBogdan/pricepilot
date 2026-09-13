"""Schema invariants that later phases depend on."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import UniqueConstraint

from pricepilot.models import Base, LlmCall, RawListing, ScrapeRun

ROOT = Path(__file__).resolve().parents[1]


def test_operational_tables_exist_from_day_one() -> None:
    """CLAUDE.md §5.6 and §5.4 both require logging from the first run onwards."""
    names = set(Base.metadata.tables)
    assert {"scrape_runs", "llm_calls", "raw_listings", "products"} <= names


def test_raw_listings_is_append_only_time_series() -> None:
    """Price history cannot be backfilled, so every day's observation is kept — but STEP 4 /
    ADR-0016 requires ingest to be idempotent *within* a day, on (source, external_id,
    collected_date), so a manual run and the scheduled run on the same day cannot duplicate
    a row or double-count a day of history."""
    cols = RawListing.__table__.columns
    assert not cols["scraped_at"].nullable
    assert not cols["external_id"].nullable
    assert not cols["collected_date"].nullable
    assert cols["content_hash"].index, "Phase 2 caches extraction on this column"
    assert any(
        set(idx.columns.keys()) == {"source", "scraped_at"} for idx in RawListing.__table__.indexes
    )
    assert any(
        isinstance(c, UniqueConstraint)
        and set(c.columns.keys())
        == {
            "source",
            "external_id",
            "collected_date",
        }
        for c in RawListing.__table__.constraints
    ), "idempotent-ingest unique constraint is missing"


def test_scrape_run_can_record_a_volume_alert() -> None:
    assert "status" in ScrapeRun.__table__.columns
    assert "items_found" in ScrapeRun.__table__.columns


def test_llm_calls_records_cost_and_cache_hits() -> None:
    cols = LlmCall.__table__.columns
    assert {"cost_usd", "cache_hit", "cache_key", "model", "phase"} <= set(cols.keys())


def test_migration_covers_every_model_table() -> None:
    """A model with no migration is a silent Phase-1 failure.

    Originally checked migration 0001 alone, back when every table was created there. Phase 2
    added `norm_listings` in a later migration (0005) — a genuinely new table, not a column added
    to an existing one — so the check now scans every migration file, not just the first."""
    versions_dir = ROOT / "alembic" / "versions"
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(versions_dir.glob("*.py"))
    )
    for table in Base.metadata.tables:
        assert f'"{table}"' in combined, f"{table} is missing from every migration"
    assert "CREATE EXTENSION IF NOT EXISTS vector" in combined
