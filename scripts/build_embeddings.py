r"""Phase 3 STEP 2 — compute embeddings for `norm_listings` (candidate retrieval).

    uv run python scripts/build_embeddings.py [--limit N] [--dry-run]

Model: `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers, local, free — CLAUDE.md
§6, zero API spend, no `SPEND:` line needed). 384-dim, chosen for the same reason the matching
model itself will eventually need to be small and CPU-servable (CLAUDE.md §6's benchmark
commitment) — this retrieval step should not depend on a model that could never run on the same
VPS the final system deploys to.

**Text embedded**: `f"{brand} {product_line or sample_title}"` — `brand` prepended because
`product_line` (STEP 1, this session's prior work) already had the brand text stripped out of it
by design, and brand is a strong identity signal an embedding model should not have to infer from
context alone. Falls back to `sample_title` on the ~0.1% of rows with no `product_line` (STEP 1's
own reported gap) rather than embedding an empty/near-empty string.

**Idempotent, cached like everything else in this pipeline**: only rows with `embedding IS NULL`
are processed, matching `scripts/normalize.py`'s own `content_hash`-cache discipline. Re-run after
`norm_listings` gains new rows (re-extraction, new scraped titles) and only the new rows are
embedded — never a full recompute.

Runs `REINDEX INDEX ix_norm_listings_embedding_ivfflat` after a real (non-dry-run, non-empty)
backfill — IVFFlat's own documentation recommends this: an index built (migration 0006) before
any data existed clusters poorly against an empty table, so the first substantial backfill should
refresh it.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.models import NormListing  # noqa: E402

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
BATCH_SIZE = 256


def embedding_text(row: NormListing) -> str:
    body = row.product_line or row.sample_title
    return f"{row.brand or ''} {body}".strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="cap rows processed (testing)")
    parser.add_argument("--dry-run", action="store_true", help="compute, don't write")
    args = parser.parse_args(argv)

    if not check_database():
        print("database UNREACHABLE", file=sys.stderr)
        return 2

    with session_scope() as session:
        query = select(NormListing).where(NormListing.embedding.is_(None))
        if args.limit:
            query = query.limit(args.limit)
        rows = session.execute(query).scalars().all()
        print(f"rows needing embedding: {len(rows)}")
        if not rows:
            return 0

        print(f"loading model {MODEL_NAME} ...")
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(MODEL_NAME)

        texts = [embedding_text(r) for r in rows]
        embeddings = model.encode(
            texts, batch_size=BATCH_SIZE, show_progress_bar=True, normalize_embeddings=True
        )

        if args.dry_run:
            print(f"\n--dry-run: computed {len(embeddings)} embeddings, wrote nothing.")
            return 0

        for row, emb in zip(rows, embeddings, strict=True):
            row.embedding = emb.tolist()
        session.flush()
        print(f"\nAPPLIED: {len(rows)} embeddings written.")

    if not args.dry_run and not args.limit:
        with session_scope() as session:
            from sqlalchemy import text as sql_text

            session.execute(sql_text("REINDEX INDEX ix_norm_listings_embedding_ivfflat"))
        print("REINDEX ix_norm_listings_embedding_ivfflat done.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
