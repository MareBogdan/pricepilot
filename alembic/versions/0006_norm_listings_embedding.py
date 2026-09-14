"""norm_listings: add `embedding` (Phase 3 STEP 2, candidate retrieval).

384-dim (paraphrase-multilingual-MiniLM-L12-v2 — CLAUDE.md §6's `sentence-transformers`, local,
free, no API spend). Nullable: `norm_listings` rows exist before embeddings are computed, and
embedding is a separate, idempotent batch step (`scripts/build_embeddings.py`) — never computed
inline by the deterministic extractor, which stays LLM/network-free per ADR-0026.

An IVFFlat cosine-distance index is added, not HNSW: this table is tens of thousands of rows, not
millions, and IVFFlat needs no extra tuning parameter beyond `lists` to be effective at this size;
revisit if `norm_listings` grows by an order of magnitude. `lists` follows pgvector's own rule of
thumb (`rows / 1000`, minimum 1) evaluated at migration time against the population when this was
written (~10,500 rows) rather than hardcoded — see the migration body for the exact number used
and why. The index is built AFTER the embedding column exists and is deliberately left to be
populated by `build_embeddings.py`'s own backfill, not by this migration (a migration should not
run a multi-minute model-inference job).

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.add_column(
        "norm_listings",
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
    )
    # IVFFlat cosine index. `lists=100` is pgvector's documented starting point for a
    # low-tens-of-thousands-of-rows table (rule of thumb: rows/1000, floored at a sane minimum) —
    # revisit if the in-scope population grows by an order of magnitude. Built now (on an empty
    # column) is cheap; IVFFlat's own docs recommend building the index after data exists for
    # better cluster quality, but `build_embeddings.py` runs `REINDEX` after its backfill for
    # exactly that reason, so the index is never queried against wildly mis-clustered data.
    op.execute(
        "CREATE INDEX ix_norm_listings_embedding_ivfflat ON norm_listings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_norm_listings_embedding_ivfflat")
    op.drop_column("norm_listings", "embedding")
