"""products.net_weight_g: Phase 5 session 3 -- the matcher's key signal for OUR catalogue (ADR-0038).

Same brand + product line at a different gramaj is NOT the same product (the dominant hard
negative in Phase 3 matching), so the serve-time matcher needs our products' weight. The mock
store carries it (`Product.net_weight_g`); the DB `products` table did not. Nullable: grooming
and accessory items have no weight.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("net_weight_g", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "net_weight_g")
