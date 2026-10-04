"""product_matches: Phase 5 session 3b -- OUR products matched to competitor listings (ADR-0039).

Grain: one row per (our product, competitor SHOP), enforcing "at most one match per (product,
shop), highest score wins" (ADR-0030) in the database, not just in code. `norm_listings` is keyed
on `content_hash` (title only, shared across shops), so the shop and the price come from
`raw_listings`: `source` + `external_id` name the exact shop listing the price was read from, and
`competitor_price`/`price_date` are that listing's latest observation (never a number invented or
retrieved by similarity -- CLAUDE.md section 6 rule 1).

`score` is the cross-encoder probability, stored rounded DOWN to 6 places so a persisted score is
never rounded UP across the threshold; `threshold` is stored per row so each link is
self-describing and `score >= threshold` is enforced by a CHECK. `model_sha256` pins which weights
produced it. The table is rebuilt (delete + insert in one transaction) by
`scripts/match_catalogue.py`, so a re-run is idempotent.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column(
            "norm_listing_id",
            sa.Integer(),
            sa.ForeignKey("norm_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("competitor_title", sa.Text(), nullable=False),
        sa.Column("score", sa.Numeric(7, 6), nullable=False),
        sa.Column("threshold", sa.Numeric(7, 6), nullable=False),
        sa.Column("model_sha256", sa.String(64), nullable=False),
        sa.Column("competitor_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("in_stock", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("product_id", "source", name="uq_product_matches_product_source"),
        sa.CheckConstraint("score >= threshold", name="ck_product_matches_score_ge_threshold"),
    )
    op.create_index("ix_product_matches_product_id", "product_matches", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_product_matches_product_id", table_name="product_matches")
    op.drop_table("product_matches")
