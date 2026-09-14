r"""Phase 3 STEP 2 — measure candidate-retrieval recall@20 against an embedding-INDEPENDENT
known-positive set.

    uv run python scripts/measure_recall_at_20.py

**TASK 2 (ADR-0028 addendum).** Reports recall@20 in TWO modes in one run, so (a) and (b) are each
visible on their own:

- **unblocked** — global top-20 by cosine distance, same query as before. Measures embedding-text
  change (a) alone, given the embeddings in the database were rebuilt with `--force` after (a).
- **blocked** — candidates restricted to the query row's own `brand_blocking_key` (STEP 3), ranked
  by cosine distance inside that block; falls back to the unblocked query when the row's own
  `brand_blocking_key` is `NULL` or it is flagged `brand_is_distributor_code` (blocking on a code
  that doesn't identify the real manufacturer would silently exclude the true cross-shop match,
  not just narrow the search). Measures (a)+(b) together.

Both modes read whatever embeddings are currently in `norm_listings.embedding` — this script never
recomputes them; run `build_embeddings.py --force` first after any embedding_text() change.

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
different-source listings sharing an identical normalized title collapse to the SAME
`norm_listings` row. There is no second row to retrieve, so the pair cannot be tested at all and
is excluded from the denominator rather than counted either way.

**This is not a hypothetical.** It happens 6 times in the 142-pair eval set (all 6 are cross-shop
pairs whose normalized titles are byte-identical — see ADR-0028's TASK 1 addendum for the list and
what it means), which is why the reported recall denominator is 136, not 142. An earlier version
of this docstring claimed "this never happens in practice" — that claim was wrong and is corrected
here rather than left standing.

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

# TASK 2b: candidates restricted to the query row's own brand_blocking_key, ranked by cosine
# distance inside the block only.
_TOP_K_BLOCKED_SQL = text(
    """
    select content_hash
    from norm_listings
    where embedding is not null
      and content_hash != :self_hash
      and brand_blocking_key = :brand_key
    order by embedding <=> (select embedding from norm_listings where content_hash = :self_hash)
    limit :k
    """
)

_BLOCK_INFO_SQL = text(
    "select brand_blocking_key, brand_is_distributor_code from norm_listings"
    " where content_hash = :self_hash"
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


def top_k_hashes_blocked(session, content_hash: str) -> set[str]:  # type: ignore[no-untyped-def]
    """TASK 2b: block on the query row's own brand_blocking_key, then rank by embedding distance
    inside the block. Falls back to the unblocked global search when the row has no usable block
    key (NULL brand_blocking_key, or flagged brand_is_distributor_code — a distributor/private-
    label code does not reliably identify the real manufacturer, so blocking on it risks silently
    excluding the true cross-shop match rather than just narrowing the search, per instruction)."""
    info = session.execute(_BLOCK_INFO_SQL, {"self_hash": content_hash}).one_or_none()
    if info is None:
        return set()
    brand_key, is_distributor = info
    if brand_key is None or is_distributor:
        return top_k_hashes(session, content_hash)
    return {
        r[0]
        for r in session.execute(
            _TOP_K_BLOCKED_SQL, {"self_hash": content_hash, "brand_key": brand_key, "k": TOP_K}
        )
    }


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

    same_hash_skipped = sum(1 for r in pairs if r["left_content_hash"] == r["right_content_hash"])
    testable_pairs = [r for r in pairs if r["left_content_hash"] != r["right_content_hash"]]
    print(
        f"\nsame-content_hash pairs skipped (not testable — see ADR-0028 TASK 1): {same_hash_skipped}"
    )

    def measure(  # type: ignore[no-untyped-def]
        session, retrieval_fn, label: str
    ) -> list[dict[str, str]]:
        hits = 0
        misses: list[dict[str, str]] = []
        by_source: Counter[str] = Counter()
        hits_by_source: Counter[str] = Counter()

        for row in testable_pairs:
            left_hash = row["left_content_hash"]
            right_hash = row["right_content_hash"]
            eval_source = row["eval_source"]
            by_source[eval_source] += 1
            left_top20 = retrieval_fn(session, left_hash)
            right_top20 = retrieval_fn(session, right_hash)
            hit = right_hash in left_top20 or left_hash in right_top20
            if hit:
                hits += 1
                hits_by_source[eval_source] += 1
            else:
                misses.append(row)

        n = sum(by_source.values())
        p_hat, lo, hi = wilson_ci(hits, n)
        print("\n" + "=" * 78)
        print(f"RECALL@20 — {label}")
        print("=" * 78)
        print(
            f"  overall (pooled, biased — never the headline number): {hits}/{n} = "
            f"{p_hat * 100:.1f}%   95% CI [{lo * 100:.1f}%, {hi * 100:.1f}%]"
        )
        for source in sorted(by_source):
            s_n = by_source[source]
            s_hits = hits_by_source[source]
            s_p, s_lo, s_hi = wilson_ci(s_hits, s_n)
            headline = "  <- HEADLINE" if source == "q3_browser_verified" else ""
            print(
                f"  {source:24s} {s_hits}/{s_n} = {s_p * 100:.1f}%   "
                f"95% CI [{s_lo * 100:.1f}%, {s_hi * 100:.1f}%]{headline}"
            )
        return misses

    with session_scope() as session:
        _ = measure(session, top_k_hashes, "(a) alone — new embedding text, unblocked")
        misses_blocked = measure(
            session,
            top_k_hashes_blocked,
            "(a)+(b) — new embedding text, blocked by brand_blocking_key",
        )

    print("\n" + "=" * 78)
    print(
        f"MISSES, (a)+(b) blocked run ({len(misses_blocked)} total) — for failure-shape analysis, not tuning"
    )
    print("=" * 78)
    for row in misses_blocked:
        print(f"\n[{row['eval_source']}]")
        print(f"  L ({row['left_source']}): {row['left_title']}")
        print(f"  R ({row['right_source']}): {row['right_title']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
