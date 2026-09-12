"""Runs one adapter, logs the run, and persists listings.

CLAUDE.md §5.6: every run logs to `scrape_runs` — source, items found, errors, duration — and
**if a source's item count drops more than 40% versus the previous run, raise an alert instead of
silently ingesting.** That rule is the whole reason this module exists rather than the adapter
writing to the database itself: the decision to ingest or not is an operational one, and it has to
be made in one place for every source.

`raw_listings` is append-only across days, one row per (listing, day) — see DECISIONS.md
ADR-0005. **STEP 4 / ADR-0016 (2026-09-12):** ingest is idempotent *within* a day. A manual run
and the scheduled run on the same calendar day upsert the same row on
`(source, external_id, collected_date)` rather than duplicating it or double-counting a day of
history — this is why the insert below is `INSERT ... ON CONFLICT DO UPDATE`, not a plain insert.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from pricepilot.db import session_scope
from pricepilot.models import RawListing, ScrapeRun
from pricepilot.scrapers.base import Scraper, ScrapeResult

# Columns updated on a same-day re-run. `source`, `external_id` and `collected_date` are the
# conflict key and never change; `run_id` moves to whichever run touched the row last, so
# scrape_runs.items_ingested for an earlier same-day run stays historically accurate while the
# listing itself reflects the latest observation.
_UPSERT_COLUMNS = (
    "run_id",
    "source_product_id",
    "url",
    "title",
    "price",
    "currency",
    "compare_at_price",
    "in_stock",
    "raw_payload",
    "scraped_at",
    "content_hash",
)

# CLAUDE.md §5.6. A drop this large is a markup change or a block, not a quiet sale.
VOLUME_DROP_THRESHOLD = 0.40


@dataclass
class RunOutcome:
    """What `run_source` did. `ingested` is 0 on a volume alert — deliberately."""

    source: str
    run_id: int | None
    items_found: int
    ingested: int
    errors: int
    skipped_out_of_scope: int
    duration_seconds: float
    status: str
    notes: str | None = None

    @property
    def alerted(self) -> bool:
        return self.status == "volume_alert"


def previous_item_count(source: str) -> int | None:
    """Items found by the last completed, non-alerting run of this source."""
    with session_scope() as session:
        return session.execute(
            select(ScrapeRun.items_found)
            .where(ScrapeRun.source == source, ScrapeRun.status == "ok")
            .order_by(ScrapeRun.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()


def is_volume_drop(found: int, previous: int | None) -> bool:
    """True when `found` is more than 40% below `previous`.

    A first run (`previous is None`) is never an alert — there is nothing to compare to. Nor is
    an increase, nor a previous run of zero.
    """
    if previous is None or previous <= 0:
        return False
    return (previous - found) / previous > VOLUME_DROP_THRESHOLD


def run_source(
    scraper: Scraper,
    limit: int | None = None,
    dry_run: bool = False,
) -> RunOutcome:
    """Scrape one source and persist the result.

    `dry_run=True` parses and reports but writes nothing at all — not the listings, and not the
    `scrape_runs` row either, because a dry run is not a run of the source.
    """
    started = time.monotonic()
    # The ACTUAL wall-clock start, not the cron's intended trigger time. STEP 4 (session note
    # 2026-09-12): GitHub Actions delays scheduled runs under load, often by 10-30 minutes, so
    # a `schedule` trigger's nominal 06:10 can genuinely execute later. scrape_runs.started_at
    # and RawListing.collected_date both derive from this real timestamp, never from the cron
    # expression, which is also why a run that slips past midnight still gets its own honest
    # collected_date rather than silently inheriting the day it was supposed to run on.
    started_at = datetime.now(UTC)
    previous = None if dry_run else previous_item_count(scraper.name)

    result: ScrapeResult = scraper.scrape(limit=limit, dry_run=dry_run)
    duration = time.monotonic() - started
    found = len(result.listings)

    if dry_run:
        return RunOutcome(
            source=scraper.name,
            run_id=None,
            items_found=found,
            ingested=0,
            errors=len(result.errors),
            skipped_out_of_scope=result.skipped_out_of_scope,
            duration_seconds=duration,
            status="dry_run",
            notes=f"{result.pages_fetched} pages fetched; nothing written",
        )

    alert = is_volume_drop(found, previous)
    status = "volume_alert" if alert else ("failed" if found == 0 else "ok")
    notes = f"{result.pages_fetched} pages fetched"
    if alert:
        notes = (
            f"VOLUME ALERT: {found} items vs {previous} on the previous run "
            f"(>{VOLUME_DROP_THRESHOLD:.0%} drop). Listings NOT ingested — "
            f"check the adapter against a fresh fixture before re-running. {notes}"
        )
    elif found == 0:
        notes = f"no items parsed — {notes}"

    with session_scope() as session:
        run = ScrapeRun(
            source=scraper.name,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            duration_seconds=duration,
            items_found=found,
            items_ingested=0,
            errors=len(result.errors),
            status=status,
            notes=notes[:4000],
        )
        session.add(run)
        session.flush()

        ingested = 0
        if status == "ok" and result.listings:
            collected_date = started_at.date()
            rows = [
                {
                    "run_id": run.id,
                    "source": listing.source,
                    "source_product_id": listing.source_product_id,
                    "external_id": listing.source_product_id or listing.url,
                    "collected_date": collected_date,
                    "url": listing.url,
                    "title": listing.title,
                    "price": listing.price,
                    "currency": listing.currency,
                    "compare_at_price": listing.compare_at_price,
                    "in_stock": listing.in_stock,
                    "raw_payload": {**(listing.raw_payload or {}), "brand": listing.brand},
                    "scraped_at": started_at,
                    "content_hash": listing.content_hash,
                }
                for listing in result.listings
            ]
            stmt = pg_insert(RawListing).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["source", "external_id", "collected_date"],
                set_={col: getattr(stmt.excluded, col) for col in _UPSERT_COLUMNS},
            )
            session.execute(stmt)
            ingested = found
            run.items_ingested = ingested
        run_id = run.id

    return RunOutcome(
        source=scraper.name,
        run_id=run_id,
        items_found=found,
        ingested=ingested,
        errors=len(result.errors),
        skipped_out_of_scope=result.skipped_out_of_scope,
        duration_seconds=duration,
        status=status,
        notes=notes,
    )
