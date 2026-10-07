"""action_log: Phase 6 -- every action taken on a recommendation, durable and reversible (ADR-0047).

One row per action: `update_price` (a guard-APPROVEd price written to the store), `flag_for_review`,
`do_nothing` (a no-change, a REJECT, a stale or declined apply), or `rollback` (reverts an earlier
`update_price`). `previous_price` is the price before the action (for a non-update, the price the
recommendation was made against); `new_price` is set exactly for `update_price` and `rollback`.
`mock_store_audit_ref` ties a write to the store's in-memory `/audit-log` entry. `reverted_by` points
at the `rollback` row that undid this row. A partial unique index allows at most ONE live
(`reverted_by IS NULL`) `update_price` per recommendation, so a double apply is refused by the
database even if two processes race.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "action_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "recommendation_id",
            sa.Integer(),
            sa.ForeignKey("recommendations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("previous_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("new_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("mock_store_audit_ref", sa.String(64), nullable=True),
        sa.Column(
            "reverted_by",
            sa.Integer(),
            sa.ForeignKey("action_log.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "action IN ('update_price', 'flag_for_review', 'do_nothing', 'rollback')",
            name="ck_action_log_action",
        ),
        sa.CheckConstraint(
            "(action IN ('update_price', 'rollback')) = (new_price IS NOT NULL)",
            name="ck_action_log_new_price_iff_write",
        ),
        sa.CheckConstraint(
            "reverted_by IS NULL OR action = 'update_price'",
            name="ck_action_log_reverted_is_update",
        ),
    )
    op.create_index("ix_action_log_recommendation_id", "action_log", ["recommendation_id"])
    op.create_index("ix_action_log_product_id", "action_log", ["product_id"])
    op.create_index(
        "uq_action_log_one_live_update",
        "action_log",
        ["recommendation_id"],
        unique=True,
        postgresql_where=sa.text("action = 'update_price' AND reverted_by IS NULL"),
        sqlite_where=sa.text("action = 'update_price' AND reverted_by IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_action_log_one_live_update", table_name="action_log")
    op.drop_index("ix_action_log_product_id", table_name="action_log")
    op.drop_index("ix_action_log_recommendation_id", table_name="action_log")
    op.drop_table("action_log")
