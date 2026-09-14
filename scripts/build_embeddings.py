r"""Phase 3 STEP 2 — compute embeddings for `norm_listings` (candidate retrieval).

    uv run python scripts/build_embeddings.py [--limit N] [--dry-run]

Model: `paraphrase-multilingual-MiniLM-L12-v2` (sentence-transformers, local, free — CLAUDE.md
§6, zero API spend, no `SPEND:` line needed). 384-dim, chosen for the same reason the matching
model itself will eventually need to be small and CPU-servable (CLAUDE.md §6's benchmark
commitment) — this retrieval step should not depend on a model that could never run on the same
VPS the final system deploys to.

**Text embedded (TASK 2a, ADR-0028 addendum): `f"{brand} {product_line or sample_title} {tail}"`**
where `tail` appends the discriminating fields `product_line` deliberately strips —
`net_weight_g`/`net_volume_ml`, `pack_count`, `life_stage`, `breed_size_code`. Without this,
same-brand-same-line-different-weight siblings embed at cosine distance 0.0 (the root cause
ADR-0028 documented for ~49% of STEP 2's misses) because nothing in the original text ever told
the model two rows were different products. `brand` stays prepended for the same reason as
before — a strong identity signal the model should not have to infer from context alone. Falls
back to `sample_title` on the ~0.1% of rows with no `product_line` rather than embedding an
empty/near-empty string.

**Idempotent, cached like everything else in this pipeline**: only rows with `embedding IS NULL`
are processed by default, matching `scripts/normalize.py`'s own `content_hash`-cache discipline.
Re-run after `norm_listings` gains new rows (re-extraction, new scraped titles) and only the new
rows are embedded — never a full recompute. **`--force` overrides this** and recomputes every row
regardless of whether `embedding` is already set — needed exactly once here, because the embedding
TEXT changed (not just new rows arriving), so the existing vectors are stale, not merely
incomplete.

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
    """`f"{brand} {product_line or sample_title} {tail}"` — see module docstring (TASK 2a). `tail`
    is built from the fields `product_line` strips out by design, so the embedding still carries
    them: quantity (weight OR volume — ADR-0026's own mass-XOR-volume invariant, never both),
    `pack_count` (only when it's a real multipack — `None`/1 are the same purchasable unit per
    the annotation conventions' rule 1, so plain single-unit rows get no pack token at all, not a
    noisy "x1" every row would otherwise share), `life_stage`, `breed_size_code`."""
    body = row.product_line or row.sample_title
    tail_parts: list[str] = []
    if row.net_weight_g is not None:
        tail_parts.append(f"{row.net_weight_g}g")
    elif row.net_volume_ml is not None:
        tail_parts.append(f"{row.net_volume_ml}ml")
    if row.pack_count is not None and row.pack_count != 1:
        tail_parts.append(f"x{row.pack_count}")
    if row.life_stage:
        tail_parts.append(row.life_stage)
    if row.breed_size_code:
        tail_parts.append(row.breed_size_code)
    tail = " ".join(tail_parts)
    return f"{row.brand or ''} {body} {tail}".strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="cap rows processed (testing)")
    parser.add_argument("--dry-run", action="store_true", help="compute, don't write")
    parser.add_argument(
        "--force",
        action="store_true",
        help="recompute every row's embedding, not just embedding IS NULL rows "
        "(needed after an embedding_text() change, not only for new rows)",
    )
    args = parser.parse_args(argv)

    if not check_database():
        print("database UNREACHABLE", file=sys.stderr)
        return 2

    with session_scope() as session:
        query = (
            select(NormListing)
            if args.force
            else select(NormListing).where(NormListing.embedding.is_(None))
        )
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
