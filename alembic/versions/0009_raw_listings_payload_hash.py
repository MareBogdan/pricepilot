"""raw_listings.raw_payload_sha256: dedupe an unchanged raw_payload across days (ADR-0032).

Storage fix, going forward only, non-destructive. Additive nullable column: old rows and old
code paths keep working unchanged. From this migration on, ingest (`pricepilot.scrapers.runner`)
stores `raw_payload_sha256` on every row and sets `raw_payload = NULL` when the canonical-JSON
hash of the new payload equals the hash on that listing's most recent row -- the static
per-listing metadata (brand, product_type, ...) essentially never changes day to day, so this
removes the dominant recurring cost in `raw_listings` (ADR-0031: Neon Free 0.5 GB projected to
fill 2026-10-25/2026-11-15). No existing row is modified or deleted by this migration itself; a
one-off backfill nulling already-collected duplicate payloads is a separate, later, destructive
decision (`docs/learned/storage-dedup.md`).

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("raw_listings", sa.Column("raw_payload_sha256", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_listings", "raw_payload_sha256")
