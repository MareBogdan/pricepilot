r"""Phase 3 STEP 1 — build a retrieval evaluation set INDEPENDENT of the embedding retriever.

    uv run python scripts/build_retrieval_eval_set.py

Measuring recall@20 against pairs the embedding retriever itself found is circular and worthless
(100% by construction). This script assembles known-positive cross-shop pairs from two sources
that never touch embeddings:

(a) The 26 browser-verified genuine matches in `docs/learned/q3-verification.md` Table 1 (27
    rows drawn; ADR-0023 records row #13 as rejected — a petmax slug collision — leaving 26
    confirmed genuine matches). Matched back to today's `raw_listings` by URL **and** the exact
    weight `q3-verification.md` recorded (`_resolve_variant`, never URL alone) — found the hard
    way this session: pentruanimale.ro groups every size variant under one shared product URL
    (CLAUDE.md §7's own documented note), so a naive "latest row at this url" lookup can silently
    resolve to a different weight variant than the one ADR-0023 actually verified.

(b) A random sample of the proxy key's (`overlap.py`) *current* cross-shop collisions. The proxy
    key is a cheap, independent (non-embedding, non-LLM) heuristic — `(brand, line tokens, net
    weight)` — so its output is a legitimate second source of known positives, distinct in kind
    from (a): (a) is human-eyes-verified by live browsing; (b) is only title-plausibility-checked
    here (read, not re-browsed) — that distinction is preserved in the output's `verification`
    column, never blurred into one undifferentiated "verified" label.

Output: `docs/learned/phase3-retrieval-eval-set.csv` — one row per known-positive pair, with
listing ids on both sides, source label, and verification method. Never touches embeddings,
pgvector, or any matching model.
"""

from __future__ import annotations

import csv
import io
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.models import RawListing  # noqa: E402
from pricepilot.overlap import OverlapKey, net_weight_grams, overlap_key  # noqa: E402

Q3_DOC = ROOT / "docs" / "learned" / "q3-verification.md"
OUTPUT_CSV = ROOT / "docs" / "learned" / "phase3-retrieval-eval-set.csv"

# ADR-0023: "26/50 confirmed genuine, 1 rejected (#13, a petmax slug collision)". Table 1 lists
# 27 drawn rows; #13 is the one ADR-0023 names as rejected.
Q3_REJECTED_ROW = 13

PROXY_SAMPLE_SEED = 20260915
PROXY_SAMPLE_SIZE = 120  # oversample; some will be dropped on plausibility check


def parse_q3_table1() -> list[dict[str, str]]:
    text = Q3_DOC.read_text(encoding="utf-8")
    match = re.search(r"## Table 1.*?\n\n(.*?)\n\n## Table 2", text, re.S)
    if match is None:
        raise RuntimeError("Table 1 not found in q3-verification.md")
    lines = [line for line in match.group(1).splitlines() if line.startswith("| ")]
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[1:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        row = dict(zip(header, cells, strict=True))
        rows.append(row)
    return rows


def _resolve_variant(  # type: ignore[no-untyped-def]
    session, source: str, url: str, expected_weight_g: int
) -> tuple[int, str, str] | None:
    """A URL alone is not enough to identify a row: pentruanimale.ro groups every size variant
    under ONE product URL (CLAUDE.md §7's own documented structural note), so multiple
    `raw_listings` rows — different `source_product_id`, different title, different weight — can
    share the identical `url`. Found the hard way this session: naively taking "the latest row at
    this url" silently picked whichever variant happened to have the highest `id`, not the one
    ADR-0023 actually verified — e.g. a Hill's 6kg row verified 2026-09-13 resolved to its own
    1.5kg sibling variant instead, purely because that row was inserted later. Disambiguates by
    the exact weight `q3-verification.md` recorded for that row (`net_weight_grams`, the same
    parser `overlap.py`'s own key already trusts) — never by recency."""
    candidates = session.execute(
        select(RawListing.id, RawListing.title, RawListing.content_hash)
        .where(RawListing.source == source, RawListing.url == url)
        .order_by(RawListing.id.desc())
    ).all()
    matches = [c for c in candidates if net_weight_grams(c.title) == expected_weight_g]
    if not matches:
        return None  # no row at this url carries the expected weight — never guess
    # Multiple matches are the SAME listing re-scraped across collection days (same title, same
    # weight) — not a genuine ambiguity, since the weight filter above already ruled out a
    # different variant sharing this url. Taking the most recent (id desc, already the sort
    # order) is the same "latest observation" convention `overlap.compute_overlap` uses.
    best = matches[0]
    return best.id, best.title, best.content_hash


def build_q3_pairs(session) -> list[dict[str, object]]:  # type: ignore[no-untyped-def]
    rows = parse_q3_table1()
    pairs: list[dict[str, object]] = []
    missing: list[tuple[str, str, str]] = []
    for row in rows:
        row_num = int(row["#"])
        if row_num == Q3_REJECTED_ROW:
            continue  # ADR-0023: rejected, a petmax slug collision, not a genuine match
        petmax_url = row["petmax_url"]
        pa_url = row["pa_url"]
        petmax_weight = int(row["petmax_weight"])
        pa_weight = int(row["pa_weight"])
        petmax_match = _resolve_variant(session, "petmax_ro", petmax_url, petmax_weight)
        pa_match = _resolve_variant(session, "pentruanimale_ro", pa_url, pa_weight)
        if petmax_match is None or pa_match is None:
            missing.append((f"#{row_num}", petmax_url, pa_url))
            continue
        petmax_id, petmax_title, petmax_hash = petmax_match
        pa_id, pa_title, pa_hash = pa_match
        pairs.append(
            {
                "left_id": petmax_id,
                "left_source": "petmax_ro",
                "left_title": petmax_title,
                "left_content_hash": petmax_hash,
                "right_id": pa_id,
                "right_source": "pentruanimale_ro",
                "right_title": pa_title,
                "right_content_hash": pa_hash,
                "eval_source": "q3_browser_verified",
                "verification": "human_browser_verified_2026-09-13",
            }
        )
    if missing:
        print(
            f"WARNING: {len(missing)} q3 pairs could not be resolved to a unique, weight-matched "
            f"raw_listings row (zero or ambiguous matches at that url/weight):"
        )
        for row_label, petmax_url, pa_url in missing:
            print(f"  {row_label}  petmax={petmax_url}  pa={pa_url}")
    return pairs


def build_proxy_key_pairs(session) -> tuple[list[dict[str, object]], int]:  # type: ignore[no-untyped-def]
    """Recomputes the proxy key live (same logic as `overlap.compute_overlap`, but keeping the
    actual listing ids per key instead of just counting), samples a random subset of the
    multi-shop collisions, and returns one representative pair per sampled key."""
    from sqlalchemy import func

    in_scope = select(RawListing).where(RawListing.excluded_reason.is_(None)).subquery()
    latest = (
        select(
            in_scope.c.source,
            in_scope.c.source_product_id,
            func.max(in_scope.c.scraped_at).label("scraped_at"),
        )
        .group_by(in_scope.c.source, in_scope.c.source_product_id)
        .subquery()
    )
    rows = session.execute(
        select(
            in_scope.c.id,
            in_scope.c.source,
            in_scope.c.title,
            in_scope.c.raw_payload,
            in_scope.c.content_hash,
        ).join(
            latest,
            (in_scope.c.source == latest.c.source)
            & (in_scope.c.source_product_id == latest.c.source_product_id)
            & (in_scope.c.scraped_at == latest.c.scraped_at),
        )
    ).all()

    by_key: dict[OverlapKey, dict[str, tuple[int, str, str]]] = {}
    for listing_id, source, title, payload, content_hash in rows:
        brand = (payload or {}).get("brand") if isinstance(payload, dict) else None
        key = overlap_key(title, brand if isinstance(brand, str) else None)
        if key is None:
            continue
        by_key.setdefault(key, {})[source] = (listing_id, title, content_hash)

    multi_shop_keys = [k for k, shops in by_key.items() if len(shops) >= 2]
    total_collisions = len(multi_shop_keys)

    rng = random.Random(PROXY_SAMPLE_SEED)
    sample_keys = rng.sample(multi_shop_keys, min(PROXY_SAMPLE_SIZE, len(multi_shop_keys)))

    pairs: list[dict[str, object]] = []
    for key in sample_keys:
        shops = by_key[key]
        source_names = sorted(shops.keys())
        left_source, right_source = source_names[0], source_names[1]
        left_id, left_title, left_hash = shops[left_source]
        right_id, right_title, right_hash = shops[right_source]
        pairs.append(
            {
                "left_id": left_id,
                "left_source": left_source,
                "left_title": left_title,
                "left_content_hash": left_hash,
                "right_id": right_id,
                "right_source": right_source,
                "right_title": right_title,
                "right_content_hash": right_hash,
                "eval_source": "proxy_key_collision",
                "verification": "title_plausibility_only",
                "proxy_key": str(key),
            }
        )
    return pairs, total_collisions


def main() -> int:
    if not check_database():
        print("database UNREACHABLE — run `docker compose up -d db`", file=sys.stderr)
        return 2

    with session_scope() as session:
        q3_pairs = build_q3_pairs(session)
        proxy_pairs, total_collisions = build_proxy_key_pairs(session)

    print(f"q3 browser-verified pairs matched: {len(q3_pairs)} (of 26 expected)")
    print(f"proxy key collisions live in DB (all 3 sources): {total_collisions}")
    print(f"proxy key pairs sampled for plausibility check: {len(proxy_pairs)}")

    fieldnames = [
        "left_id",
        "left_source",
        "left_title",
        "left_content_hash",
        "right_id",
        "right_source",
        "right_title",
        "right_content_hash",
        "eval_source",
        "verification",
        "proxy_key",
        "plausible",
        "rejection_reason",
    ]
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for pair in q3_pairs + proxy_pairs:
            row = {name: pair.get(name, "") for name in fieldnames}
            writer.writerow(row)

    print(f"\nwritten: {OUTPUT_CSV.relative_to(ROOT)} ({len(q3_pairs) + len(proxy_pairs)} rows)")
    print("`plausible`/`rejection_reason` are empty — fill in by the manual plausibility pass,")
    print("never auto-filled by this script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
