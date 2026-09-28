"""policy_chunks: Phase 5 session 2 — RAG index over the pricing-policy prose (ADR-0036).

CLAUDE.md section 6, hard architectural rule 1: RAG is only for policy TEXT. Every number a
recommendation acts on -- cost, price, margin, stock, competitor prices, thresholds -- comes from
SQL or `config/pricing-policy.toml`, never retrieved by similarity from this table. This table
holds prose only: `section_ref`/`heading`/`text` for display and citation, plus provenance
(`source_doc`, `doc_version`, `source_sha256`) so a caller can tell which version of the policy
document is indexed. No threshold value is ever stored here.

Co-located with `norm_listings.embedding` in the same database on purpose: ADR-0014's two-database
split is Neon (collected data, `DATABASE_URL`) vs. the local docker Postgres used only for tests
(`TEST_DATABASE_URL`) -- there is exactly one production database, and it already holds pgvector
embeddings for `norm_listings`, so `policy_chunks` belongs there too, not in a third database.

Same embedding model as `norm_listings` (`paraphrase-multilingual-MiniLM-L12-v2`, 384-dim,
`scripts/build_embeddings.py`) -- the index and the query must use the same model, or cosine
similarity is comparing two different vector spaces. `embedding` is NOT NULL here (unlike
`norm_listings.embedding`, computed in a separate later batch step): `scripts/build_policy_index.py`
always sets it in the same write that creates or updates a row, since the whole table only ever
holds ~7 rows drawn from one small source document.

No ANN index (IVFFlat/HNSW) is created, unlike migration 0006's `norm_listings` index. pgvector's
own rule of thumb for `lists` (rows / 1000) does not apply at ~7 rows, and a full sequential scan
over 7 rows is effectively instant -- an IVFFlat index would add tuning complexity for zero
measurable benefit at this size, and pgvector does not build one well with so few training vectors.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 384


def upgrade() -> None:
    op.create_table(
        "policy_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        # The upsert key: one row per policy section, not per (section, version) -- re-indexing
        # replaces a section's row in place rather than accumulating history.
        sa.Column("section_ref", sa.String(16), nullable=False, unique=True),
        sa.Column("heading", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("source_doc", sa.String(255), nullable=False),
        sa.Column("doc_version", sa.String(32), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
    )
    op.create_index("ix_policy_chunks_section_ref", "policy_chunks", ["section_ref"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_policy_chunks_section_ref", table_name="policy_chunks")
    op.drop_table("policy_chunks")
