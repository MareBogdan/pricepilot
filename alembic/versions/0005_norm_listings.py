"""norm_listings: Phase 2 normalized attribute layer (ADR-0026).

Reads from raw_listings WHERE excluded_reason IS NULL, never writes back to it — raw_listings
stays append-only. Keyed on content_hash (verified this session to be sha256(normalize_title
(title)) only — no price, no stock, no source — so it is safe to reuse as the cache key CLAUDE.md
§5.1/§9 require: one row per unique normalized title, not per listing-day, and deliberately global
across sources, not scoped per (source, content_hash) — see ADR-0026).

Every extracted field is nullable. `extraction_status`/`extraction_errors` keep "not stated in the
title" (a null field, no entry in extraction_errors) distinguishable from "extraction failed" (a
null field named in extraction_errors) — CLAUDE.md's explicit requirement for this schema.

`ck_norm_listings_weight_xor_volume` enforces net_weight_g and net_volume_ml are never both set —
a listing's quantity is mass-based or volume-based, never both. Written in plain boolean SQL
rather than Postgres's `num_nonnulls()` so the same constraint works (and is tested) against
SQLite in-memory too.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "norm_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("sample_source", sa.String(64), nullable=False),
        sa.Column("sample_title", sa.Text(), nullable=False),
        sa.Column("brand", sa.String(128), nullable=True),
        sa.Column("product_line", sa.Text(), nullable=True),
        sa.Column("net_weight_g", sa.Integer(), nullable=True),
        sa.Column("net_volume_ml", sa.Integer(), nullable=True),
        sa.Column("pack_count", sa.Integer(), nullable=True),
        sa.Column("bonus_weight_g", sa.Integer(), nullable=True),
        sa.Column("breed_size_code", sa.String(16), nullable=True),
        sa.Column("life_stage", sa.String(16), nullable=True),
        sa.Column("flavour", sa.String(64), nullable=True),
        sa.Column("food_form", sa.String(16), nullable=True),
        sa.Column("dosage_band", sa.String(32), nullable=True),
        sa.Column("extraction_status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("extraction_errors", sa.JSON(), nullable=True),
        sa.Column("extractor_version", sa.String(32), nullable=False),
        sa.Column(
            "extracted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "NOT (net_weight_g IS NOT NULL AND net_volume_ml IS NOT NULL)",
            name="ck_norm_listings_weight_xor_volume",
        ),
    )
    op.create_index("ix_norm_listings_content_hash", "norm_listings", ["content_hash"], unique=True)
    op.create_index("ix_norm_listings_brand", "norm_listings", ["brand"])


def downgrade() -> None:
    op.drop_index("ix_norm_listings_brand", table_name="norm_listings")
    op.drop_index("ix_norm_listings_content_hash", table_name="norm_listings")
    op.drop_table("norm_listings")
