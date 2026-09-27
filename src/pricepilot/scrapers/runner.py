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

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

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
    "raw_payload_sha256",
    "scraped_at",
    "content_hash",
)

# ---------------------------------------------------------------------------
# Payload dedup (ADR-0032, migration 0009): `raw_payload` is static per-listing metadata
# (brand, product_type, ...) that almost never changes day to day, unlike price/compare_at_price,
# which are separate columns and are ALWAYS written every day regardless of this. Storing it
# again on every unchanged day was the dominant recurring cost in `raw_listings`
# (docs/learned/storage-dedup.md). Nothing here touches price history.
# ---------------------------------------------------------------------------


def canonical_payload_hash(payload: dict[str, object]) -> str:
    """sha256 of the payload's canonical (sort_keys) JSON. Deterministic regardless of dict
    insertion order, so the same content always hashes the same way."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_payload_for_storage(
    payload: dict[str, object], previous_hash: str | None
) -> tuple[dict[str, object] | None, str]:
    """(payload_to_store, hash_to_store) for one listing's row.

    `previous_hash` is the `raw_payload_sha256` on that listing's most recent existing row, or
    `None` when there is none (a brand-new listing, or a legacy pre-migration row with no hash
    yet -- both are treated identically: "no previous hash to compare against", so the payload is
    always stored in full). When the new payload's hash matches, the payload itself is dropped
    (NULL) and only the hash is kept; the caller can always recover it via `get_payload`.
    """
    new_hash = canonical_payload_hash(payload)
    if previous_hash is not None and new_hash == previous_hash:
        return None, new_hash
    return payload, new_hash


def previous_payload_hashes(
    session: Session, source: str, external_ids: list[str]
) -> dict[str, str]:
    """The latest existing `raw_payload_sha256` per `external_id` for `source`, among rows
    already in the table (before this run's insert). Missing from the result == no previous hash.
    """
    if not external_ids:
        return {}
    rows = session.execute(
        select(
            RawListing.external_id,
            RawListing.collected_date,
            RawListing.id,
            RawListing.raw_payload_sha256,
        )
        .where(RawListing.source == source, RawListing.external_id.in_(external_ids))
        .order_by(RawListing.external_id, RawListing.collected_date, RawListing.id)
    ).all()
    latest: dict[str, str] = {}
    for external_id, _collected_date, _id, sha in rows:
        if sha is not None:
            latest[external_id] = sha  # rows are in ascending order, so the last write wins
    return latest


def get_payload(
    session: Session, source: str, external_id: str, on_or_before: date
) -> dict[str, object] | None:
    """The most recent non-NULL `raw_payload` for this listing on or before `on_or_before`.

    Most days now store NULL there (see `resolve_payload_for_storage`); this resolves back to
    the last day the payload was actually written, exactly like the ingest-time comparison would
    see it. `None` means no row for this listing has ever carried a payload up to that date.
    """
    return (
        session.execute(
            select(RawListing.raw_payload)
            .where(
                RawListing.source == source,
                RawListing.external_id == external_id,
                RawListing.collected_date <= on_or_before,
                RawListing.raw_payload.is_not(None),
            )
            .order_by(RawListing.collected_date.desc(), RawListing.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


# CLAUDE.md §5.6. A drop this large is a markup change or a block, not a quiet sale.
VOLUME_DROP_THRESHOLD = 0.40

# Session note (2026-09-12): `scrape_runs.errors` used to be a bare count, and twice now that
# made a real problem un-diagnosable after the fact (petmax's skipped_out_of_scope reasons,
# pentruanimale's 3 unexplained parse errors). `error_detail` persists the actual strings,
# capped so a pathological run (thousands of errors) can't bloat the row.
MAX_PERSISTED_ERRORS = 50
MAX_ERROR_LENGTH = 500


def _error_detail(errors: list[str]) -> list[str] | None:
    if not errors:
        return None
    capped = errors[:MAX_PERSISTED_ERRORS]
    truncated = [e[:MAX_ERROR_LENGTH] for e in capped]
    if len(errors) > MAX_PERSISTED_ERRORS:
        truncated.append(f"... and {len(errors) - MAX_PERSISTED_ERRORS} more errors not shown")
    return truncated


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
            error_detail=_error_detail(result.errors),
        )
        session.add(run)
        session.flush()

        ingested = 0
        if status == "ok" and result.listings:
            collected_date = started_at.date()
            external_ids = [listing.source_product_id or listing.url for listing in result.listings]
            prev_hashes = previous_payload_hashes(session, scraper.name, external_ids)
            rows = []
            for listing in result.listings:
                external_id = listing.source_product_id or listing.url
                full_payload = {**(listing.raw_payload or {}), "brand": listing.brand}
                stored_payload, stored_hash = resolve_payload_for_storage(
                    full_payload, prev_hashes.get(external_id)
                )
                rows.append(
                    {
                        "run_id": run.id,
                        "source": listing.source,
                        "source_product_id": listing.source_product_id,
                        "external_id": external_id,
                        "collected_date": collected_date,
                        "url": listing.url,
                        "title": listing.title,
                        "price": listing.price,
                        "currency": listing.currency,
                        "compare_at_price": listing.compare_at_price,
                        "in_stock": listing.in_stock,
                        "raw_payload": stored_payload,
                        "raw_payload_sha256": stored_hash,
                        "scraped_at": started_at,
                        "content_hash": listing.content_hash,
                    }
                )
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
