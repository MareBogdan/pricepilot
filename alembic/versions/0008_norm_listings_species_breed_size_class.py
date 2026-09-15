"""norm_listings: species, breed_size_class.

Phase 3 finding 4/5 (2026-09-15 session, 100-pair reference labelling pass). `species` follows
the same backfill pattern as `category`/`brand_blocking_key`/`brand_is_distributor_code`
(migration 0007) — `scripts/backfill_phase3_signals.py` populates it, needs `url`/`raw_payload`,
never `extract()`. `breed_size_class` is derived from `breed_size_code` alone (title-only) and is
backfilled in the same script for one consistent run, even though it could in principle live in
`extract()`.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("norm_listings", sa.Column("species", sa.String(length=8), nullable=True))
    op.add_column(
        "norm_listings", sa.Column("breed_size_class", sa.String(length=8), nullable=True)
    )
    op.create_index("ix_norm_listings_species", "norm_listings", ["species"])
    op.create_index("ix_norm_listings_breed_size_class", "norm_listings", ["breed_size_class"])


def downgrade() -> None:
    op.drop_index("ix_norm_listings_breed_size_class", table_name="norm_listings")
    op.drop_index("ix_norm_listings_species", table_name="norm_listings")
    op.drop_column("norm_listings", "breed_size_class")
    op.drop_column("norm_listings", "species")
