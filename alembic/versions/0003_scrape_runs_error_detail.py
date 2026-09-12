"""scrape_runs.error_detail: persist the actual error strings, not just a count.

Session note (2026-09-12): hit this gap twice — petmax's skipped_out_of_scope reasons and now
pentruanimale's 3 unexplained "parse errors" are both un-diagnosable after the fact, because only
`len(result.errors)` was ever persisted. `error_detail` is a JSON array of the error strings
(capped), so `make status` and any later investigation can see what actually happened without
needing to re-run the source to find out.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scrape_runs", sa.Column("error_detail", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("scrape_runs", "error_detail")
