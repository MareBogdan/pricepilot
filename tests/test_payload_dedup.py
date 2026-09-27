"""ADR-0032 / migration 0009: raw_payload dedup by hash. No live site involved anywhere here --
`canonical_payload_hash`/`resolve_payload_for_storage` are pure functions, and `get_payload` is
exercised against an in-memory SQLite database built from the real ORM tables (never Neon, never
the local docker Postgres) so this suite needs no running database at all.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pricepilot.models import Base, RawListing, ScrapeRun
from pricepilot.scrapers.runner import (
    canonical_payload_hash,
    get_payload,
    previous_payload_hashes,
    resolve_payload_for_storage,
)

# --- pure functions: no DB -------------------------------------------------------------------


def test_canonical_hash_is_stable_regardless_of_key_order() -> None:
    a = canonical_payload_hash({"brand": "Purina", "product_type": "dry food"})
    b = canonical_payload_hash({"product_type": "dry food", "brand": "Purina"})
    assert a == b


def test_canonical_hash_differs_on_content_change() -> None:
    a = canonical_payload_hash({"brand": "Purina"})
    b = canonical_payload_hash({"brand": "Royal Canin"})
    assert a != b


def test_new_listing_with_no_previous_hash_stores_payload_in_full() -> None:
    payload = {"brand": "Purina"}
    stored, new_hash = resolve_payload_for_storage(payload, previous_hash=None)
    assert stored == payload
    assert new_hash == canonical_payload_hash(payload)


def test_identical_payload_stores_null_plus_the_hash() -> None:
    payload = {"brand": "Purina", "product_type": "dry food"}
    prev_hash = canonical_payload_hash(payload)
    stored, new_hash = resolve_payload_for_storage(payload, previous_hash=prev_hash)
    assert stored is None
    assert new_hash == prev_hash


def test_changed_payload_stores_both_payload_and_new_hash() -> None:
    old_payload = {"brand": "Purina"}
    new_payload = {"brand": "Royal Canin"}
    prev_hash = canonical_payload_hash(old_payload)
    stored, new_hash = resolve_payload_for_storage(new_payload, previous_hash=prev_hash)
    assert stored == new_payload
    assert new_hash == canonical_payload_hash(new_payload)
    assert new_hash != prev_hash


# --- get_payload / previous_payload_hashes: in-memory SQLite, real ORM tables ------------------


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ScrapeRun.__table__, RawListing.__table__])
    return Session(engine)


def _add_row(
    session: Session,
    run_id: int,
    *,
    source: str = "petmax_ro",
    external_id: str = "sku-1",
    collected_date: date,
    payload: dict[str, object] | None,
    payload_hash: str | None,
) -> None:
    session.add(
        RawListing(
            run_id=run_id,
            source=source,
            source_product_id=external_id,
            external_id=external_id,
            collected_date=collected_date,
            url="https://example.invalid/p/1",
            title="Test listing",
            price=100,
            currency="RON",
            raw_payload=payload,
            raw_payload_sha256=payload_hash,
            content_hash="deadbeef",
        )
    )
    session.flush()


def test_get_payload_resolves_to_last_non_null_payload_on_or_before_date() -> None:
    session = _session()
    run = ScrapeRun(source="petmax_ro", status="ok")
    session.add(run)
    session.flush()

    full = {"brand": "Purina"}
    full_hash = canonical_payload_hash(full)
    _add_row(session, run.id, collected_date=date(2026, 9, 1), payload=full, payload_hash=full_hash)
    # days 2 and 3: payload deduped to NULL, same hash carried forward
    _add_row(session, run.id, collected_date=date(2026, 9, 2), payload=None, payload_hash=full_hash)
    _add_row(session, run.id, collected_date=date(2026, 9, 3), payload=None, payload_hash=full_hash)

    assert get_payload(session, "petmax_ro", "sku-1", date(2026, 9, 3)) == full
    assert get_payload(session, "petmax_ro", "sku-1", date(2026, 9, 2)) == full
    # a date before the payload ever existed resolves to nothing
    assert get_payload(session, "petmax_ro", "sku-1", date(2026, 8, 31)) is None


def test_get_payload_picks_most_recent_full_payload_after_a_change() -> None:
    session = _session()
    run = ScrapeRun(source="petmax_ro", status="ok")
    session.add(run)
    session.flush()

    old = {"brand": "Purina"}
    new = {"brand": "Royal Canin"}
    _add_row(
        session,
        run.id,
        collected_date=date(2026, 9, 1),
        payload=old,
        payload_hash=canonical_payload_hash(old),
    )
    _add_row(
        session,
        run.id,
        collected_date=date(2026, 9, 5),
        payload=new,
        payload_hash=canonical_payload_hash(new),
    )
    _add_row(
        session,
        run.id,
        collected_date=date(2026, 9, 6),
        payload=None,
        payload_hash=canonical_payload_hash(new),
    )

    assert get_payload(session, "petmax_ro", "sku-1", date(2026, 9, 3)) == old
    assert get_payload(session, "petmax_ro", "sku-1", date(2026, 9, 6)) == new


def test_get_payload_unknown_listing_is_none() -> None:
    session = _session()
    assert get_payload(session, "petmax_ro", "does-not-exist", date(2026, 9, 1)) is None


def test_previous_payload_hashes_takes_latest_by_date_then_id() -> None:
    session = _session()
    run = ScrapeRun(source="petmax_ro", status="ok")
    session.add(run)
    session.flush()

    h1 = canonical_payload_hash({"brand": "Purina"})
    h2 = canonical_payload_hash({"brand": "Royal Canin"})
    _add_row(
        session,
        run.id,
        collected_date=date(2026, 9, 1),
        payload={"brand": "Purina"},
        payload_hash=h1,
    )
    _add_row(
        session,
        run.id,
        collected_date=date(2026, 9, 2),
        payload={"brand": "Royal Canin"},
        payload_hash=h2,
    )

    latest = previous_payload_hashes(session, "petmax_ro", ["sku-1", "sku-missing"])
    assert latest == {"sku-1": h2}


def test_previous_payload_hashes_empty_ids_returns_empty() -> None:
    session = _session()
    assert previous_payload_hashes(session, "petmax_ro", []) == {}


def test_previous_payload_hashes_ignores_legacy_rows_with_no_hash() -> None:
    """A pre-migration row has raw_payload_sha256 = NULL forever (no backfill this session);
    a row with a hash from a later day must still win over it."""
    session = _session()
    run = ScrapeRun(source="petmax_ro", status="ok")
    session.add(run)
    session.flush()

    h = canonical_payload_hash({"brand": "Purina"})
    _add_row(
        session,
        run.id,
        collected_date=date(2026, 9, 1),
        payload={"brand": "Purina"},
        payload_hash=None,
    )
    _add_row(
        session,
        run.id,
        collected_date=date(2026, 9, 2),
        payload={"brand": "Purina"},
        payload_hash=h,
    )

    assert previous_payload_hashes(session, "petmax_ro", ["sku-1"]) == {"sku-1": h}
