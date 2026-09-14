"""norm_listings: Phase 3 STEP 3 signals — category, brand_blocking_key,
brand_is_distributor_code.

Three columns STATE.md's own "What Phase 3 will need from Phase 2's output" list named, added
now (not computed on the fly) so candidate blocking can filter/join on them cheaply and
indexed, the same reasoning `brand` was already indexed for (ADR-0026). All three are derived
purely from data already in `norm_listings`/`raw_listings` — `scripts/backfill_phase3_signals.py`
populates them, never a scraper or the deterministic `extract()` pipeline (`category` needs `url`
and `raw_payload`, which `extract()` deliberately never reads — title-only, per ADR-0026).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("norm_listings", sa.Column("category", sa.String(length=16), nullable=True))
    op.add_column(
        "norm_listings", sa.Column("brand_blocking_key", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "norm_listings",
        sa.Column(
            "brand_is_distributor_code", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index("ix_norm_listings_category", "norm_listings", ["category"])
    op.create_index("ix_norm_listings_brand_blocking_key", "norm_listings", ["brand_blocking_key"])


def downgrade() -> None:
    op.drop_index("ix_norm_listings_brand_blocking_key", table_name="norm_listings")
    op.drop_index("ix_norm_listings_category", table_name="norm_listings")
    op.drop_column("norm_listings", "brand_is_distributor_code")
    op.drop_column("norm_listings", "brand_blocking_key")
    op.drop_column("norm_listings", "category")
