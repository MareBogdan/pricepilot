"""recommendations: Phase 5 session 4 -- the full trace of one price recommendation (ADR-0042).

One row per recommendation: the input snapshot (SQL / TOML numbers only), the retrieved policy
sections, the prompt, the raw LLM reply, the parsed proposal, latency and cost, and the
deterministic guard's verdict. `is_mock` marks rows written by the mock proposer ($0, no
`llm_calls` row) so they can never be counted toward the Phase 5 gate (50 real recommendations,
session 5). `guard_final_price` is set exactly when the guard APPROVEd (CHECK).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("run_label", sa.String(64), nullable=False),
        sa.Column("is_mock", sa.Boolean(), nullable=False),
        sa.Column("scenario", sa.String(64), nullable=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("current_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("competitor_prices", sa.JSON(), nullable=False),
        sa.Column("price_7d_ago", sa.Numeric(12, 2), nullable=True),
        sa.Column("price_7d_ago_source", sa.String(64), nullable=False),
        sa.Column("elasticity_placeholder", sa.JSON(), nullable=False),
        sa.Column("rag_sections", sa.JSON(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("llm_model", sa.String(64), nullable=False),
        sa.Column("llm_raw_reply", sa.Text(), nullable=False),
        sa.Column("llm_proposed_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("llm_rationale", sa.Text(), nullable=True),
        sa.Column("llm_cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("llm_latency_ms", sa.Integer(), nullable=True),
        sa.Column("guard_status", sa.String(16), nullable=False),
        sa.Column("guard_final_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("guard_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "guard_status IN ('APPROVE', 'REJECT', 'FLAG')", name="ck_recommendations_guard_status"
        ),
        sa.CheckConstraint(
            "(guard_status = 'APPROVE') = (guard_final_price IS NOT NULL)",
            name="ck_recommendations_final_price_iff_approve",
        ),
    )
    op.create_index("ix_recommendations_product_id", "recommendations", ["product_id"])
    op.create_index("ix_recommendations_run_label", "recommendations", ["run_label"])


def downgrade() -> None:
    op.drop_index("ix_recommendations_run_label", table_name="recommendations")
    op.drop_index("ix_recommendations_product_id", table_name="recommendations")
    op.drop_table("recommendations")
