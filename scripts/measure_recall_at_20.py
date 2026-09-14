r"""Phase 3 STEP 2 — measure candidate-retrieval recall@20 against an embedding-INDEPENDENT
known-positive set.

    uv run python scripts/measure_recall_at_20.py

Reads `docs/learned/phase3-retrieval-eval-set.csv` (STEP 1, `scripts/build_retrieval_eval_set.py`
— built from browser-verified matches and proxy-key collisions, neither of which ever touches an
embedding) and `norm_listings.embedding` (STEP 2, `scripts/build_embeddings.py`).

**For each known-positive pair (L, R)**: query pgvector for L's top-20 nearest neighbours by
cosine distance across the WHOLE `norm_listings` population (excluding L itself, all sources
mixed — candidate retrieval doesn't know in advance which shop holds the match), and separately
R's top-20. The pair counts as a hit if R appears in L's top-20 OR L appears in R's top-20 —
either direction is a legitimate query Phase 3's candidate generation could run, and a pair only
needs to surface once to reach the annotation queue.

**Recall@20 is reported with a Wilson 95% CI**, same methodology as ADR-0023's overlap-gate
sample — a bare percentage with no interval invites treating n=142 as if it had the precision of
a much larger sample.

**Rows on the same content_hash on both sides of a known-positive pair are skipped**, not
counted as trivial hits — `norm_listings` is keyed on content_hash globally (ADR-0026), so two
different-source listings sharing an identical normalized title would trivially "match" without
testing retrieval at all; this never happens in practice for the two known-positive sources here
(cross-shop titles differ by construction) but the guard costs nothing and documents the
assumption rather than leaving it silently relied upon.

Nothing here writes to the database or tunes anything — pure measurement.
"""

from __future__ import annotations

import csv
import io
import math
import sys
from collections import Counter
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

_TOP_K_SQL = text(
    """
    select content_hash
    from norm_listings
    where embedding is not null and content_hash != :self_hash
    order by embedding <=> (select embedding from norm_listings where content_hash = :self_hash)
    limit :k
    """
)


def wilson_ci(x: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Wilson score interval — same formula and z as ADR-0023's overlap-gate sample."""
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = x / n
    denom = 1 + z**2 / n
    centre = p_hat + z**2 / (2 * n)
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2))
    return p_hat, (centre - margin) / denom, (centre + margin) / denom


def top_k_hashes(session, content_hash: str) -> set[str]:  # type: ignore[no-untyped-def]
    return {r[0] for r in session.execute(_TOP_K_SQL, {"self_hash": content_hash, "k": TOP_K})}


def main() -> int:
    if not EVAL_SET_CSV.exists():
        print(
            f"eval set not found: {EVAL_SET_CSV} — run build_retrieval_eval_set.py first",
            file=sys.stderr,
        )
        return 2
    if not check_database():
        print("database UNREACHABLE", file=sys.stderr)
        return 2

    with EVAL_SET_CSV.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    # Drop proxy-key pairs marked implausible on manual review (STEP 1) — they are not known
    # positives and would corrupt the recall figure, not just be noise in it.
    pairs = [
        r
        for r in rows
        if not (r["eval_source"] == "proxy_key_collision" and r.get("plausible") == "false")
    ]
    print(f"known-positive pairs loaded: {len(pairs)} (of {len(rows)} rows in the eval set)")

    same_hash_skipped = 0
    hits = 0
    misses: list[dict[str, str]] = []
    by_source: Counter[str] = Counter()
    hits_by_source: Counter[str] = Counter()

    with session_scope() as session:
        for row in pairs:
            left_hash = row["left_content_hash"]
            right_hash = row["right_content_hash"]
            eval_source = row["eval_source"]
            if left_hash == right_hash:
                same_hash_skipped += 1
                continue

            by_source[eval_source] += 1
            left_top20 = top_k_hashes(session, left_hash)
            right_top20 = top_k_hashes(session, right_hash)
            hit = right_hash in left_top20 or left_hash in right_top20
            if hit:
                hits += 1
                hits_by_source[eval_source] += 1
            else:
                misses.append(row)

    n = sum(by_source.values())
    p_hat, lo, hi = wilson_ci(hits, n)

    print(f"\nsame-content_hash pairs skipped (trivial by construction): {same_hash_skipped}")
    print("\n" + "=" * 78)
    print("RECALL@20")
    print("=" * 78)
    print(f"  overall: {hits}/{n} = {p_hat * 100:.1f}%   95% CI [{lo * 100:.1f}%, {hi * 100:.1f}%]")
    for source in sorted(by_source):
        s_n = by_source[source]
        s_hits = hits_by_source[source]
        s_p, s_lo, s_hi = wilson_ci(s_hits, s_n)
        print(
            f"  {source:24s} {s_hits}/{s_n} = {s_p * 100:.1f}%   "
            f"95% CI [{s_lo * 100:.1f}%, {s_hi * 100:.1f}%]"
        )

    print("\n" + "=" * 78)
    print(f"MISSES ({len(misses)} total) — for failure-shape analysis, not tuning")
    print("=" * 78)
    for row in misses:
        print(f"\n[{row['eval_source']}]")
        print(f"  L ({row['left_source']}): {row['left_title']}")
        print(f"  R ({row['right_source']}): {row['right_title']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
