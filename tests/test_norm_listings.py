"""Phase 2 schema — `norm_listings` (ADR-0026, migration 0005).

Two things this file exists to prove, offline, with no live database:

1. The weight/volume mutual-exclusivity invariant actually holds — both at the ORM validator
   level and as a real DB constraint (exercised against SQLite in-memory, since the constraint
   is written in plain boolean SQL specifically so it doesn't need Postgres).
2. "Not stated in the title" and "extraction failed" stay distinguishable in the schema, not
   just in a docstring's promise.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pricepilot.models import Base, NormListing


@pytest.fixture
def sqlite_session() -> Session:
    """An in-memory SQLite DB with the real table DDL, including the check constraint —
    proves the constraint is enforceable by more than just Postgres-specific syntax."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[NormListing.__table__])
    with Session(engine) as session:
        yield session


def _row(**overrides: object) -> NormListing:
    defaults: dict[str, object] = {
        "content_hash": "a" * 64,
        "sample_source": "petmax_ro",
        "sample_title": "Royal Canin Mini Adult 8 kg",
        "extractor_version": "v0",
    }
    defaults.update(overrides)
    return NormListing(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ORM-level validator (offline, no DB)
# ---------------------------------------------------------------------------


def test_weight_and_volume_together_raises_at_assignment() -> None:
    with pytest.raises(ValueError, match="net_weight_g and net_volume_ml"):
        _row(net_weight_g=8000, net_volume_ml=500)


def test_weight_and_volume_together_raises_regardless_of_order() -> None:
    with pytest.raises(ValueError, match="net_weight_g and net_volume_ml"):
        _row(net_volume_ml=500, net_weight_g=8000)


def test_weight_alone_is_fine() -> None:
    assert _row(net_weight_g=8000).net_weight_g == 8000


def test_volume_alone_is_fine() -> None:
    assert _row(net_volume_ml=250).net_volume_ml == 250


def test_neither_is_fine_quantity_not_stated_is_a_legitimate_value() -> None:
    row = _row()
    assert row.net_weight_g is None
    assert row.net_volume_ml is None


# ---------------------------------------------------------------------------
# DB-level constraint (SQLite in-memory) — a second line of defence for any write path
# that bypasses the ORM validator above.
# ---------------------------------------------------------------------------


def test_db_constraint_rejects_both_set(sqlite_session: Session) -> None:
    """Insert directly via Core, bypassing the ORM `@validates` hook entirely, to prove the
    constraint itself — not just the Python-side guard — is what actually stops this."""
    from sqlalchemy import insert

    stmt = insert(NormListing.__table__).values(
        content_hash="b" * 64,
        sample_source="petmax_ro",
        sample_title="x",
        extractor_version="v0",
        net_weight_g=8000,
        net_volume_ml=500,
    )
    with pytest.raises(IntegrityError):
        sqlite_session.execute(stmt)
        sqlite_session.commit()


def test_db_constraint_allows_exactly_one_or_neither(sqlite_session: Session) -> None:
    sqlite_session.add(_row(content_hash="c" * 64, net_weight_g=8000))
    sqlite_session.add(_row(content_hash="d" * 64, net_volume_ml=250))
    sqlite_session.add(_row(content_hash="e" * 64))
    sqlite_session.commit()  # no error


def test_content_hash_uniqueness_is_enforced(sqlite_session: Session) -> None:
    sqlite_session.add(_row(content_hash="f" * 64))
    sqlite_session.commit()
    sqlite_session.add(_row(content_hash="f" * 64, sample_source="animax_ro"))
    with pytest.raises(IntegrityError):
        sqlite_session.commit()


# ---------------------------------------------------------------------------
# "Not stated" vs "extraction failed" stay distinguishable
# ---------------------------------------------------------------------------


def test_not_stated_and_extraction_failed_are_different_shapes() -> None:
    not_stated = _row(brand=None)  # extractor ran, title genuinely names no brand
    failed = _row(brand=None, extraction_status="error", extraction_errors={"brand": "boom"})

    assert not_stated.brand is None
    assert failed.brand is None
    # The distinguishing fact lives in extraction_errors, not in the null field itself.
    assert not_stated.extraction_errors is None
    assert failed.extraction_errors is not None
    assert "brand" in failed.extraction_errors


def test_extraction_status_defaults_to_ok(sqlite_session: Session) -> None:
    row = _row(content_hash="g" * 64)
    sqlite_session.add(row)
    sqlite_session.commit()
    sqlite_session.refresh(row)
    assert row.extraction_status == "ok"
    assert row.extraction_errors is None
