"""raw_listings.excluded_reason: quarantine, never delete (ADR-0025).

2026-09-14 diagnostic + implementation session: 118 already-collected rows were found to be
veterinary/prescription-diet products that CLAUDE.md §7 says never belonged in scope, caught by
the tightened `is_regulated()` (ADR-0025) and animax's `product_type` cross-check. Deleting them
would destroy two real days of price history that CLAUDE.md §7 Phase 4 says cannot be recovered,
for a filtering rule that could still turn out to need another correction. NULL = in scope,
non-NULL names the signal that fired — reversible, inspectable, no data lost either way.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("raw_listings", sa.Column("excluded_reason", sa.Text(), nullable=True))
    op.create_index("ix_raw_listings_excluded_reason", "raw_listings", ["excluded_reason"])


def downgrade() -> None:
    op.drop_index("ix_raw_listings_excluded_reason", table_name="raw_listings")
    op.drop_column("raw_listings", "excluded_reason")
