"""Idempotent daily ingest for raw_listings: external_id, collected_date, unique constraint.

STEP 4 (session note 2026-09-12): a manual run and the scheduled run on the same calendar day
must not produce duplicate rows or double-count a day of history. `external_id` is
`source_product_id` when the shop has one, else the listing `url` — the same fallback the
petmax adapter already uses to dedupe within one run. `collected_date` is the run's start date.
The unique constraint on (source, external_id, collected_date) is what the runner upserts on
(pricepilot.scrapers.runner). See DECISIONS.md ADR-0016, amending ADR-0005.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("raw_listings", sa.Column("external_id", sa.String(255), nullable=True))
    op.add_column("raw_listings", sa.Column("collected_date", sa.Date(), nullable=True))

    # Backfill for any row that predates this migration (none expected in a young Neon
    # database, but a fresh local docker Postgres and CI both build the schema from scratch
    # via every revision in order, so this must be correct even against zero rows).
    op.execute(
        "UPDATE raw_listings SET external_id = COALESCE(source_product_id, url) "
        "WHERE external_id IS NULL"
    )
    op.execute(
        "UPDATE raw_listings SET collected_date = scraped_at::date WHERE collected_date IS NULL"
    )

    op.alter_column("raw_listings", "external_id", nullable=False)
    op.alter_column("raw_listings", "collected_date", nullable=False)

    op.create_index("ix_raw_listings_external_id", "raw_listings", ["external_id"])
    op.create_unique_constraint(
        "uq_raw_listings_source_external_collected_date",
        "raw_listings",
        ["source", "external_id", "collected_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_raw_listings_source_external_collected_date", "raw_listings", type_="unique"
    )
    op.drop_index("ix_raw_listings_external_id", table_name="raw_listings")
    op.drop_column("raw_listings", "collected_date")
    op.drop_column("raw_listings", "external_id")
