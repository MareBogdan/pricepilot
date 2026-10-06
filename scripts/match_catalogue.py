r"""Phase 5 session 3b -- match OUR 30 products to competitor listings -> `product_matches` (ADR-0039).

    $env:PRICEPILOT_DB_DRIVER = "pg8000"      # if psycopg is blocked (ADR-0038)
    .venv\Scripts\python scripts/match_catalogue.py [--dry-run] [--audit-truncation]

Pipeline:
  0. Faithfulness gate: the locally loaded cross-encoder must reproduce the committed PyTorch-fp32
     predictions (`check_ce_faithfulness.run`) or this script stops before scoring anything.
  1. Each `products` row -> a listing record via the SAME `extract()` competitors went through.
  2. Candidates = `norm_listings` sharing our `brand_blocking_key`. A block of <= 300 is scored in
     full (ADR-0030's K=100 was for the 10k-vs-10k competitor re-match); a block > 300 is cut to
     the top-100 by embedding cosine, and every cut is reported. `--audit-truncation` additionally
     scores the cut-off remainder and reports how many >= threshold matches the cut would have
     lost -- a diagnostic only; it never changes what is persisted.
  3. Score (our, competitor) with the cross-encoder, keep score >= 0.89, REJECT pairs the
     attribute-consistency guard calls inconsistent (ADR-0041: category / life stage / flavour),
     expand each kept listing to the shops currently selling it (latest `raw_listings` price per
     shop), then at most ONE link per (product, shop): highest score wins.
  4. `product_matches` is rebuilt (delete + insert in one transaction): idempotent.
  5. Write the BLIND verification worksheet -- no score, no label (ADR-0038). Precision / gate is
     NOT computed here; it is scored only after the human labels are committed.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import delete, func, select  # noqa: E402

import check_ce_faithfulness  # noqa: E402
from build_embeddings import embedding_text  # noqa: E402
from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.embeddings import embed  # noqa: E402
from pricepilot.matching.consistency import ListingFacts, conflicts  # noqa: E402
from pricepilot.matching.pair_text import build_pair_text  # noqa: E402
from pricepilot.matching.serve import (  # noqa: E402
    LARGE_BLOCK_THRESHOLD,
    MATCH_THRESHOLD,
    PRICE_MAX_AGE_DAYS,
    TOP_K_BY_COSINE,
    CrossEncoderScorer,
    ScoredLink,
    norm_row_to_record,
    product_to_listing,
    score_to_decimal,
    select_best_per_shop,
    select_current_prices,
)
from pricepilot.models import NormListing, Product, ProductMatch, RawListing  # noqa: E402

QUEUE_DIR = ROOT / "docs" / "learned" / "results" / "phase5"
QUEUE_CSV = QUEUE_DIR / "match-verification-queue.csv"
SAMPLE_CSV = QUEUE_DIR / "match-verification-sample.csv"
RUN_JSON = QUEUE_DIR / "match-run.json"
GUARD_CSV = QUEUE_DIR / "guard-effect.csv"
GUARD_COLUMNS = ["change", "link_key", "score", "competitor_title", "reasons"]
# ADR-0038: verify ALL links if <= 120, else a seeded random sample of 120.
VERIFY_ALL_UP_TO = 120
SAMPLE_SEED = 20261004
WORKSHEET_COLUMNS = [
    "link_key",
    "our_title",
    "our_brand",
    "our_size",
    "competitor_title",
    "competitor_brand",
    "competitor_size",
    "shop",
    "competitor_price_ron",
    "competitor_url",
]


def link_key(product_id: int, source: str) -> str:
    """Stable worksheet key. `(product_id, source)` is UNIQUE in `product_matches`, so unlike the
    SERIAL `id` (which a delete + insert re-run advances) it survives a re-run."""
    return f"{product_id}:{source}"


def size_text(weight_g: int | None, volume_ml: int | None) -> str:
    if weight_g is not None:
        return f"{weight_g} g"
    if volume_ml is not None:
        return f"{volume_ml} ml"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models" / "ce-ft-best")
    parser.add_argument("--dry-run", action="store_true", help="score and report; write nothing")
    parser.add_argument("--product-ids", help="debug: comma-separated ids; implies --dry-run")
    parser.add_argument("--audit-truncation", action="store_true", help="see module docstring")
    args = parser.parse_args()

    if args.product_ids:
        args.dry_run = True
    if not check_database():
        print("database unreachable (if psycopg is blocked, set PRICEPILOT_DB_DRIVER=pg8000)")
        return 1

    # --- 0. faithfulness gate -----------------------------------------------------------------
    scorer = CrossEncoderScorer(args.model_dir)
    repro = check_ce_faithfulness.run(args.model_dir, scorer)
    print(
        f"faithfulness: max|diff|={repro['max_abs_diff']:.2e} flips={repro['flips_at_threshold']} "
        f"reproduced={repro['reproduced']}"
    )
    if not repro["reproduced"]:
        print("STOP: the loaded model does not reproduce the benchmarked predictions.")
        return 1

    # --- 1-2. our products, candidates --------------------------------------------------------
    with session_scope() as session:
        products = list(session.scalars(select(Product).order_by(Product.id)))
        if args.product_ids:
            wanted = {int(x) for x in args.product_ids.split(",")}
            products = [p for p in products if p.id in wanted]
        latest_rows = session.execute(
            select(RawListing.source, func.max(RawListing.collected_date)).group_by(
                RawListing.source
            )
        ).all()
        source_latest: dict[str, date] = {src: day for src, day in latest_rows}
        ours = {p.id: product_to_listing(p.title, p.brand, p.net_weight_g) for p in products}
        our_vectors = embed(
            [
                embedding_text(SimpleNamespace(**ours[p.id].embedding_fields))  # type: ignore[arg-type]
                for p in products
            ]
        )

        stats: list[dict[str, Any]] = []
        scored: dict[tuple[int, int], float] = {}  # (product_id, norm_listing_id) -> score
        norm_rows: dict[int, NormListing] = {}
        beyond_top_k: dict[int, set[int]] = {}  # product_id -> listing ids cut by the top-K rule
        for product, vec in zip(products, our_vectors, strict=True):
            key = ours[product.id].blocking_key
            block: list[NormListing] = []
            if key is not None:
                block = list(
                    session.scalars(
                        select(NormListing)
                        .where(NormListing.brand_blocking_key == key)
                        .order_by(NormListing.embedding.cosine_distance(vec), NormListing.id)
                    )
                )
            truncated = len(block) > LARGE_BLOCK_THRESHOLD
            kept = block[:TOP_K_BY_COSINE] if truncated else block
            cut = block[TOP_K_BY_COSINE:] if truncated else []
            to_score = kept + (cut if args.audit_truncation else [])
            beyond_top_k[product.id] = {r.id for r in cut}
            stats.append(
                {
                    "product_id": product.id,
                    "title": product.title,
                    "blocking_key": key,
                    "block_size": len(block),
                    "truncated_to_top_k": truncated,
                    "scored_for_matching": len(kept),
                    "scored_audit_only": len(cut) if args.audit_truncation else 0,
                    # NULL embeddings sort last in the cosine ORDER BY, so in a truncated block
                    # they are always cut; counted so that is visible, not silent.
                    "block_rows_without_embedding": sum(1 for r in block if r.embedding is None),
                }
            )
            pairs = [
                build_pair_text(ours[product.id].record, norm_row_to_record(r)) for r in to_score
            ]
            for row, sc in zip(to_score, scorer.score(pairs), strict=True):
                scored[(product.id, row.id)] = sc
                norm_rows[row.id] = row
            print(f"  product {product.id:>2} block={len(block):>4} scored={len(to_score):>4}")

        # --- 3. threshold, expand to shops, one per (product, shop) ---------------------------
        audit_lost = sum(
            1
            for (pid, nid), sc in scored.items()
            if nid in beyond_top_k[pid] and sc >= MATCH_THRESHOLD
        )
        eligible_all = {
            k: sc
            for k, sc in scored.items()
            if sc >= MATCH_THRESHOLD and k[1] not in beyond_top_k[k[0]]
        }
        # ADR-0041: deterministic attribute guard, after the model and before persistence.
        facts_ours = {
            p.id: ListingFacts(
                category=p.category,
                title=p.title,
                life_stage=ours[p.id].record.get("life_stage"),
                flavour=ours[p.id].record.get("flavour"),
            )
            for p in products
        }
        guard_reasons: dict[tuple[int, int], list[str]] = {}
        for pid, nid in eligible_all:
            n = norm_rows[nid]
            reasons = conflicts(
                facts_ours[pid],
                ListingFacts(n.category, n.sample_title, n.life_stage, n.flavour),
            )
            if reasons:
                guard_reasons[(pid, nid)] = reasons
        eligible = {k: sc for k, sc in eligible_all.items() if k not in guard_reasons}
        hashes = {norm_rows[nid].content_hash for _, nid in eligible_all}
        oldest = min(source_latest.values()) - timedelta(days=PRICE_MAX_AGE_DAYS)
        raw = (
            session.scalars(
                select(RawListing).where(
                    RawListing.content_hash.in_(hashes),
                    RawListing.excluded_reason.is_(None),
                    RawListing.collected_date >= oldest,
                )
            ).all()
            if hashes
            else []
        )
        by_hash: dict[str, list[dict[str, Any]]] = {}
        for r in raw:
            by_hash.setdefault(r.content_hash, []).append(
                {
                    "source": r.source,
                    "external_id": r.external_id,
                    "collected_date": r.collected_date,
                    "price": r.price,
                    "in_stock": r.in_stock,
                    "url": r.url,
                    "title": r.title,
                }
            )

        def choose(candidates: dict[tuple[int, int], float]) -> tuple[list[ScoredLink], int]:
            links: list[ScoredLink] = []
            dropped = 0
            for (pid, nid), sc in candidates.items():
                nrow = norm_rows[nid]
                current = select_current_prices(
                    by_hash.get(nrow.content_hash, []), source_latest, PRICE_MAX_AGE_DAYS
                )
                if not current:
                    dropped += 1
                for src, obs in current.items():
                    links.append(
                        ScoredLink(pid, src, sc, obs["external_id"], {"norm": nrow, "obs": obs})
                    )
            return select_best_per_shop(links, MATCH_THRESHOLD), dropped

        chosen_unguarded, _ = choose(eligible_all)
        chosen, dropped_no_current_price = choose(eligible)

        def ident(link: ScoredLink) -> tuple[int, str, int, str]:
            return (link.product_id, link.source, link.payload["norm"].id, link.external_id)

        kept_ids = {ident(link) for link in chosen}
        before_ids = {ident(link) for link in chosen_unguarded}
        guard_effect = [
            {
                "change": "removed",
                "link_key": link_key(link.product_id, link.source),
                "score": f"{link.score:.4f}",
                "competitor_title": link.payload["obs"]["title"],
                "reasons": ";".join(guard_reasons[(link.product_id, link.payload["norm"].id)]),
            }
            for link in chosen_unguarded
            if ident(link) not in kept_ids
        ] + [
            {
                # a lower-scoring listing >= 0.89 that took the (product, shop) slot once the
                # guard removed the better-scoring but inconsistent one -- NOT in the labelled 28
                "change": "newly_surfaced",
                "link_key": link_key(link.product_id, link.source),
                "score": f"{link.score:.4f}",
                "competitor_title": link.payload["obs"]["title"],
                "reasons": "",
            }
            for link in chosen
            if ident(link) not in before_ids
        ]

        # --- 4. persist -------------------------------------------------------------------------
        by_pid = {p.id: p for p in products}
        rows = [
            ProductMatch(
                product_id=link.product_id,
                source=link.source,
                norm_listing_id=link.payload["norm"].id,
                content_hash=link.payload["norm"].content_hash,
                external_id=link.external_id,
                url=link.payload["obs"]["url"],
                competitor_title=link.payload["obs"]["title"],
                score=score_to_decimal(link.score),
                threshold=score_to_decimal(MATCH_THRESHOLD),
                model_sha256=scorer.weights_sha256,
                competitor_price=link.payload["obs"]["price"],
                price_date=link.payload["obs"]["collected_date"],
                in_stock=link.payload["obs"]["in_stock"],
            )
            for link in chosen
        ]
        covered = {link.product_id for link in chosen}
        # Reporting only (not changing the choice): a shop SKU retitled after the matched title
        # leaves its old title's last price "current" for up to PRICE_MAX_AGE_DAYS. Count chosen
        # links whose (shop, external_id) has a newer observation under any other title.
        newest_by_sku = {
            (src, ext): day
            for src, ext, day in session.execute(
                select(
                    RawListing.source,
                    RawListing.external_id,
                    func.max(RawListing.collected_date),
                )
                .where(
                    RawListing.excluded_reason.is_(None),
                    RawListing.external_id.in_({link.external_id for link in chosen}),
                )
                .group_by(RawListing.source, RawListing.external_id)
            )
        }
        superseded = [
            link_key(link.product_id, link.source)
            for link in chosen
            if newest_by_sku.get((link.source, link.external_id), date.min)
            > link.payload["obs"]["collected_date"]
        ]
        today = date.today()
        stale_shops = {
            src: str(day) for src, day in source_latest.items() if (today - day).days > 2
        }
        if stale_shops:
            print(f"WARNING: shops whose newest scrape is > 2 days old: {stale_shops}")
        summary = {
            "model_sha256": scorer.weights_sha256,
            "faithfulness": repro,
            "threshold": MATCH_THRESHOLD,
            "price_max_age_days": PRICE_MAX_AGE_DAYS,
            "run_date": str(today),
            "shop_newest_scrape": {k: str(v) for k, v in source_latest.items()},
            "shops_newest_scrape_older_than_2_days": stale_shops,
            "links_with_newer_observation_under_another_title": superseded,
            "products": len(products),
            "products_with_a_match": len(covered),
            "links": len(chosen),
            "listings_at_or_above_threshold": len(eligible_all),
            "listings_rejected_by_consistency_guard": len(guard_reasons),
            "links_before_guard": len(chosen_unguarded),
            "links_removed_by_guard": sum(1 for g in guard_effect if g["change"] == "removed"),
            "links_newly_surfaced_by_guard": sum(
                1 for g in guard_effect if g["change"] == "newly_surfaced"
            ),
            "listings_dropped_no_current_price": dropped_no_current_price,
            "truncated_products": [s["product_id"] for s in stats if s["truncated_to_top_k"]],
            "truncation_audit_ran": args.audit_truncation,
            "truncation_audit_matches_beyond_top_k": audit_lost if args.audit_truncation else None,
            "per_product": stats,
        }
        print(json.dumps({k: v for k, v in summary.items() if k != "per_product"}, indent=2))
        if args.dry_run:
            print("dry-run: nothing written")
            return 0

        session.execute(delete(ProductMatch))
        session.add_all(rows)
        session.flush()

        # --- 5. blind worksheet (NO score, NO label) ------------------------------------------
        ws_rows = []
        for m, link in zip(rows, chosen, strict=True):
            nrow = link.payload["norm"]
            p = by_pid[m.product_id]
            ws_rows.append(
                {
                    "link_key": link_key(m.product_id, m.source),
                    "our_title": p.title,
                    "our_brand": p.brand,
                    "our_size": size_text(p.net_weight_g, ours[p.id].record["net_volume_ml"]),
                    "competitor_title": m.competitor_title,
                    "competitor_brand": nrow.brand or "",
                    "competitor_size": size_text(nrow.net_weight_g, nrow.net_volume_ml),
                    "shop": m.source,
                    "competitor_price_ron": f"{m.competitor_price:.2f}",
                    "competitor_url": m.url,
                }
            )
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(QUEUE_CSV, ws_rows)
    summary["worksheet"] = str(QUEUE_CSV.relative_to(ROOT)).replace("\\", "/")
    if len(ws_rows) > VERIFY_ALL_UP_TO:
        sample = random.Random(SAMPLE_SEED).sample(ws_rows, VERIFY_ALL_UP_TO)
        write_csv(SAMPLE_CSV, sorted(sample, key=lambda r: r["link_key"]))
        summary["sample_worksheet"] = str(SAMPLE_CSV.relative_to(ROOT)).replace("\\", "/")
    with GUARD_CSV.open("w", encoding="utf-8", newline="") as f:
        gw = csv.DictWriter(f, fieldnames=GUARD_COLUMNS)
        gw.writeheader()
        gw.writerows(guard_effect)
    RUN_JSON.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"persisted {len(rows)} links; coverage {len(covered)}/{len(products)} products")
    print(f"worksheet: {QUEUE_CSV}")
    return 0


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=WORKSHEET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
