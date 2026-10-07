"""recommendations.llm_stop_reason: record why the model stopped (Phase 5 session 5, ADR-0044).

Sonnet 5 thinks by default; with `max_tokens=400` four of the 50 real replies were cut off by the
cap (three had no text at all, one ended mid-sentence). The trace did not say so. Nullable: mock
rows and rows written before this migration have no value (the 50 session-5 rows are backfilled
from the content-addressed response cache by `scripts/backfill_stop_reason.py`).

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("recommendations", sa.Column("llm_stop_reason", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("recommendations", "llm_stop_reason")
