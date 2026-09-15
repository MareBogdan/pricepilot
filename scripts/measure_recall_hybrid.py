r"""Phase 3 item 1, BLOCK 2(d) — hybrid (lexical + dense) candidate retrieval, measured against
the same embedding-independent eval set `measure_recall_at_20.py` uses.

    uv run python scripts/measure_recall_hybrid.py

**Why.** ADR-0028 attributed roughly half its remaining recall@20 misses to "weaker cross-shop
discrimination even without weight-crowding — a general-purpose multilingual model not separating
brand identity from generic flavour-word overlap." A failure-shape re-analysis on the grown eval
set (n=50, 2026-09-16) found the single largest remaining miss category is EN/RO flavour-word
crossing (Salmon/Somon, Lamb/Miel, Turkey/Curcan — 5 of 17 misses) and retailer-specific line
naming divergence (Optiderma vs Sensitive Skin — 4 of 17) — both are lexical-token problems a
dense embedding is not guaranteed to resolve for rare, domain-specific vocabulary, and both are
exactly what a keyword-overlap signal is good at IF the two sides share vocabulary at all (which
EN/RO pairs and reworded line names often don't either — measured, not assumed, below).

**Method.** A lexical channel over the SAME text `build_embeddings.py::embedding_text()` embeds
(brand + product_line + quantity/pack/life_stage/breed_size tail) — not a different, hand-picked
text — so the dense-vs-lexical comparison isolates the RANKING METHOD, not a text change. Postgres
full-text search (`to_tsvector('simple', ...)`, `ts_rank_cd`) computed ad-hoc per query (no
persisted tsvector column — this is a measurement pass, not a production index; a real deployment
would add a generated column + GIN index, not shown here). Fused via **Reciprocal Rank Fusion**
(`score = sum(1 / (k + rank))` per channel, `k=60`, the standard RRF constant from the original
paper — simple, parameter-light, and does not require calibrating the two channels' raw score
scales against each other, which cosine distance and `ts_rank_cd` do not share).

Reports four numbers, never just one, on the unbiased subset:
1. Dense alone, unblocked (same as `measure_recall_at_20.py`'s "(a) alone")
2. Lexical alone, unblocked
3. RRF-fused, unblocked (dense + lexical)
4. RRF-fused, blocked by `brand_blocking_key` (the best-of-all-worlds candidate config)

Nothing here writes to the database or tunes the extractor — pure measurement.
"""

from __future__ import annotations

import csv
import io
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402

EVAL_SET_CSV = ROOT / "docs" / "learned" / "phase3-retrieval-eval-set.csv"
TOP_K = 20
RRF_K = 60
LEXICAL_POOL = 200  # candidates fetched per channel before fusion -- must be >= TOP_K by a wide
# margin so RRF has enough of each ranking to combine meaningfully.

_EMBEDDING_TEXT_SQL = text(
    """
    select coalesce(brand,'') || ' ' || coalesce(product_line, sample_title, '') || ' ' ||
           coalesce(net_weight_g::text || 'g', net_volume_ml::text || 'ml', '') || ' ' ||
           case when pack_count is not null and pack_count <> 1 then 'x' || pack_count::text else '' end || ' ' ||
           coalesce(life_stage, '') || ' ' || coalesce(breed_size_code, '') as txt
    from norm_listings where content_hash = :h
    """
)

_DENSE_TOP_SQL = text(
    """
    select content_hash
    from norm_listings
    where embedding is not null and content_hash != :self_hash
    order by embedding <=> (select embedding from norm_listings where content_hash = :self_hash)
    limit :k
    """
)

_LEXICAL_TOP_SQL = text(
    """
    select content_hash, rank
    from (
        select content_hash,
               ts_rank_cd(
                   to_tsvector('simple',
                       coalesce(brand,'') || ' ' || coalesce(product_line, sample_title, '') || ' ' ||
                       coalesce(net_weight_g::text || 'g', net_volume_ml::text || 'ml', '') || ' ' ||
                       case when pack_count is not null and pack_count <> 1 then 'x' || pack_count::text else '' end || ' ' ||
                       coalesce(life_stage, '') || ' ' || coalesce(breed_size_code, '')
                   ),
                   plainto_tsquery('simple', :qtext)
               ) as rank
        from norm_listings
        where content_hash != :self_hash and embedding is not null
    ) ranked
    where rank > 0
    order by rank desc
    limit :k
    """
)

_BLOCK_INFO_SQL = text(
    "select brand_blocking_key, brand_is_distributor_code from norm_listings where content_hash = :self_hash"
)

_DENSE_TOP_BLOCKED_SQL = text(
    """
    select content_hash
    from norm_listings
    where embedding is not null and content_hash != :self_hash and brand_blocking_key = :brand_key
    order by embedding <=> (select embedding from norm_listings where content_hash = :self_hash)
    limit :k
    """
)

_LEXICAL_TOP_BLOCKED_SQL = text(
    """
    select content_hash, rank
    from (
        select content_hash,
               ts_rank_cd(
                   to_tsvector('simple',
                       coalesce(brand,'') || ' ' || coalesce(product_line, sample_title, '') || ' ' ||
                       coalesce(net_weight_g::text || 'g', net_volume_ml::text || 'ml', '') || ' ' ||
                       case when pack_count is not null and pack_count <> 1 then 'x' || pack_count::text else '' end || ' ' ||
                       coalesce(life_stage, '') || ' ' || coalesce(breed_size_code, '')
                   ),
                   plainto_tsquery('simple', :qtext)
               ) as rank
        from norm_listings
        where content_hash != :self_hash and embedding is not null and brand_blocking_key = :brand_key
    ) ranked
    where rank > 0
    order by rank desc
    limit :k
    """
)


def wilson_ci(x: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = x / n
    denom = 1 + z**2 / n
    centre = p_hat + z**2 / (2 * n)
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2))
    return p_hat, (centre - margin) / denom, (centre + margin) / denom


def query_text(session, content_hash: str) -> str:  # type: ignore[no-untyped-def]
    row = session.execute(_EMBEDDING_TEXT_SQL, {"h": content_hash}).one_or_none()
    return row.txt if row is not None else ""


def dense_ranked(session, content_hash: str, blocked: bool, brand_key: str | None) -> list[str]:  # type: ignore[no-untyped-def]
    if blocked and brand_key is not None:
        rows = session.execute(
            _DENSE_TOP_BLOCKED_SQL,
            {"self_hash": content_hash, "brand_key": brand_key, "k": LEXICAL_POOL},
        ).all()
    else:
        rows = session.execute(_DENSE_TOP_SQL, {"self_hash": content_hash, "k": LEXICAL_POOL}).all()
    return [r[0] for r in rows]


def lexical_ranked(  # type: ignore[no-untyped-def]
    session, content_hash: str, qtext: str, blocked: bool, brand_key: str | None
) -> list[str]:
    if not qtext.strip():
        return []
    if blocked and brand_key is not None:
        rows = session.execute(
            _LEXICAL_TOP_BLOCKED_SQL,
            {"self_hash": content_hash, "qtext": qtext, "brand_key": brand_key, "k": LEXICAL_POOL},
        ).all()
    else:
        rows = session.execute(
            _LEXICAL_TOP_SQL, {"self_hash": content_hash, "qtext": qtext, "k": LEXICAL_POOL}
        ).all()
    return [r[0] for r in rows]


def rrf_fuse(*ranked_lists: list[str], k: int = RRF_K, top_k: int = TOP_K) -> set[str]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for i, h in enumerate(ranked):
            scores[h] = scores.get(h, 0.0) + 1.0 / (k + i + 1)
    return {h for h, _ in sorted(scores.items(), key=lambda x: -x[1])[:top_k]}


def main() -> int:
    if not EVAL_SET_CSV.exists():
        print(f"eval set not found: {EVAL_SET_CSV}", file=sys.stderr)
        return 2
    if not check_database():
        print("database UNREACHABLE", file=sys.stderr)
        return 2

    with EVAL_SET_CSV.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    pairs = [
        r
        for r in rows
        if not (r["eval_source"] == "proxy_key_collision" and r.get("plausible") == "false")
    ]

    def eval_bucket(row: dict[str, str]) -> str:
        if row["eval_source"] != "q3_browser_verified":
            return row["eval_source"]
        clean_tags = (
            "human_browser_verified_2026-09-13",
            "api_verified_2026-09-16_brand_weight_query",
        )
        if any(tag in row.get("verification", "") for tag in clean_tags):
            return "q3_browser_verified_ORIGINAL (clean)"
        return "q3_browser_verified_EXTENDED (CONTAMINATED)"

    testable = [r for r in pairs if r["left_content_hash"] != r["right_content_hash"]]
    headline_pairs = [
        r for r in testable if eval_bucket(r) == "q3_browser_verified_ORIGINAL (clean)"
    ]
    print(f"headline (clean, unbiased) pairs: {len(headline_pairs)}")

    results: dict[str, tuple[int, int]] = {}

    with session_scope() as session:

        def measure(label: str, top_k_fn) -> None:  # type: ignore[no-untyped-def]
            hits = 0
            for row in headline_pairs:
                lh, rh = row["left_content_hash"], row["right_content_hash"]
                l_top = top_k_fn(lh)
                r_top = top_k_fn(rh)
                if rh in l_top or lh in r_top:
                    hits += 1
            n = len(headline_pairs)
            results[label] = (hits, n)
            p, lo, hi = wilson_ci(hits, n)
            print(
                f"  {label:45s} {hits}/{n} = {p * 100:.1f}%  95% CI [{lo * 100:.1f}%, {hi * 100:.1f}%]"
            )

        def brand_key_of(content_hash: str) -> tuple[str | None, bool]:
            info = session.execute(_BLOCK_INFO_SQL, {"self_hash": content_hash}).one_or_none()
            if info is None:
                return None, False
            return info[0], bool(info[1])

        print("\n" + "=" * 78)
        print("RECALL@20, headline subset -- dense / lexical / fused (unblocked)")
        print("=" * 78)

        measure(
            "1. dense alone (unblocked)",
            lambda h: set(dense_ranked(session, h, False, None)[:TOP_K]),
        )

        qtext_cache: dict[str, str] = {}

        def qtext_of(h: str) -> str:
            if h not in qtext_cache:
                qtext_cache[h] = query_text(session, h)
            return qtext_cache[h]

        measure(
            "2. lexical alone (unblocked)",
            lambda h: set(lexical_ranked(session, h, qtext_of(h), False, None)[:TOP_K]),
        )
        measure(
            "3. RRF fused, dense+lexical (unblocked)",
            lambda h: rrf_fuse(
                dense_ranked(session, h, False, None),
                lexical_ranked(session, h, qtext_of(h), False, None),
            ),
        )

        def fused_blocked(h: str) -> set[str]:
            brand_key, is_distributor = brand_key_of(h)
            blocked = brand_key is not None and not is_distributor
            return rrf_fuse(
                dense_ranked(session, h, blocked, brand_key),
                lexical_ranked(session, h, qtext_of(h), blocked, brand_key),
            )

        measure("4. RRF fused, blocked by brand_blocking_key", fused_blocked)

    print("\nDone. Nothing tuned, nothing written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
