r"""Phase 3 STEP 6 — build the annotation queue from STEP 2's own top-20 candidates.

    uv run python scripts/build_annotation_queue.py

Cross-shop only (different `sample_source`): the matching problem this project solves is "does
this competitor listing correspond to the same purchasable unit as this one", not within-shop
deduplication.

**Two candidate sources, not one — found necessary this session, not assumed.** A first version
of this script drew every candidate purely from pgvector top-20 retrieval and got 120 hard-tier
pairs out of 6,241 (1.9%) — nowhere near CLAUDE.md §7's >=40% floor. The cause is the same one
STEP 2's own recall measurement diagnosed: top-20 neighbours are dominated by a listing's OWN
shop's same-brand-different-weight siblings (the Hill's SP Canine case, DECISIONS.md ADR-0028 —
all 20 nearest neighbours were petmax's own catalogue, zero cross-shop), so genuine CROSS-SHOP
hard cases are structurally crowded out of any one listing's top-20 almost every time. Retrieval
alone cannot supply them at the volume the gate needs.

So the hard tier is drawn two ways, same "deliberate hard-case inclusion" discipline Phase 2's own
gate sample used (STEP 2 of that session: hard-case forms drawn first, by a targeted query, then
the remainder filled by proportional random draw — not invented for this script):

1. **A targeted SQL query** — cross-shop pairs sharing `brand_blocking_key` (STEP 3) and identical
   `product_line` text, where capacity (`net_weight_g`/`net_volume_ml`/`pack_count`/
   `bonus_weight_g`) or `flavour` differs. This is exactly CLAUDE.md's "same model different
   capacity"/"single vs multipack" shape, found directly from `norm_listings` attributes, not from
   embeddings — 444 such pairs exist in the current population, checked before relying on it.
2. **pgvector top-20 retrieval** (same query shape as `scripts/measure_recall_at_20.py`) over a
   random sample of anchor listings — supplies the `easy` tier, and whatever `hard`/`trivial`
   shapes retrieval happens to surface on its own (deduplicated against the targeted set, never
   double-counted).

**`trivial`.** Defined per instruction as identical `brand`, `product_line`, and capacity
(`net_weight_g` AND `net_volume_ml`, checked as plain equality — see the real bug this caught
below). Genuinely rare for a cross-shop pair (two listings whose title normalizes byte-identically
across shops already collapse to ONE `norm_listings` row, ADR-0026's global content_hash key — a
trivial pair can only exist when Phase 2's *further* cleaning, not raw normalization, happens to
erase the remaining wording difference between two still-distinct rows), but not impossible: 37
such pairs exist in the current population, checked directly rather than assumed. All 37 are
auto-labelled `M` and re-inserted into the human queue as a spot-check (below the 50-pair target
because only 37 exist — reported exactly, not padded).

**A real classification bug caught while building this.** An early version's `same_capacity`
check required "at least one side states a value" before treating equal `net_volume_ml` as a
match — which silently made EVERY weight-only product (the overwhelming majority: `net_weight_g`
stated, `net_volume_ml` correctly `NULL` on both sides per ADR-0026's mass-XOR-volume invariant)
register as "different capacity", corrupting the trivial/hard split for nearly the whole catalog.
Found by tracing one specific misclassified pair (two identical Applaws 70g listings, wrongly
tagged `hard`) rather than trusting the aggregate tier counts — fixed to plain equality
(`None == None` is a legitimate match: neither side stating a volume is not evidence they differ).

**Hard-case floor.** CLAUDE.md §7 asks for >=40% hard cases. The targeted query supplies enough on
its own (444 available, comfortably over the 400-pair floor for a 1,000-pair queue) — every
available hard-tier pair is included (the floor is a minimum, not a cap), reported exactly, never
padded.

Output: `docs/learned/phase3-annotation-queue.json` (consumed by `tools/annotate.html`) and a
console report — tier sizes, auto-label count and the fraction of the queue it removes, estimated
wall-clock at 200 pairs/hour. Writes nothing to the database and starts no annotation.
"""

from __future__ import annotations

import io
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402

OUTPUT_JSON = ROOT / "docs" / "learned" / "phase3-annotation-queue.json"

TOP_K = 20
QUEUE_SIZE_TARGET = 1000
HARD_CASE_FLOOR = 0.40
SPOT_CHECK_TRIVIAL_COUNT = 50
SHUFFLE_SEED = 20260915
ANCHOR_SAMPLE_SEED = 20260915
# Retrieval-drawn anchors, oversampled relative to what's needed for the `easy` tier and trimmed
# down later — most anchors' top-20 won't contribute a cross-shop candidate at all.
ANCHOR_SAMPLE_SIZE = 900

ATTR_FIELDS = (
    "brand",
    "product_line",
    "net_weight_g",
    "net_volume_ml",
    "pack_count",
    "bonus_weight_g",
    "breed_size_code",
    "life_stage",
    "flavour",
    "food_form",
    "sample_source",
    "sample_title",
    "brand_blocking_key",
)

_TARGETED_HARD_SQL = text(
    """
    select a.content_hash as a_hash, b.content_hash as b_hash
    from norm_listings a
    join norm_listings b
      on a.brand_blocking_key = b.brand_blocking_key
     and a.brand_blocking_key is not null
     and lower(trim(a.product_line)) = lower(trim(b.product_line))
     and a.product_line is not null
     and a.sample_source < b.sample_source
     and a.content_hash != b.content_hash
     and (
           a.net_weight_g is distinct from b.net_weight_g
        or a.net_volume_ml is distinct from b.net_volume_ml
        or a.pack_count is distinct from b.pack_count
        or a.bonus_weight_g is distinct from b.bonus_weight_g
        or a.flavour is distinct from b.flavour
     )
    """
)
_ANCHOR_SQL = text(
    "select content_hash from norm_listings where embedding is not null order by random() limit :n"
)
_CANDIDATES_SQL = text(
    """
    select content_hash
    from norm_listings
    where embedding is not null and content_hash != :self_hash
    order by embedding <=> (select embedding from norm_listings where content_hash = :self_hash)
    limit :k
    """
)
_ATTRS_SQL = text(
    f"select content_hash, {', '.join(ATTR_FIELDS)} from norm_listings where content_hash = any(:hashes)"
)


@dataclass(frozen=True)
class Listing:
    content_hash: str
    brand: str | None
    product_line: str | None
    net_weight_g: int | None
    net_volume_ml: int | None
    pack_count: int | None
    bonus_weight_g: int | None
    breed_size_code: str | None
    life_stage: str | None
    flavour: str | None
    food_form: str | None
    source: str
    title: str
    brand_blocking_key: str | None


def _norm_line(s: str | None) -> str | None:
    return s.strip().lower() if s else None


def classify_tier(left: Listing, right: Listing) -> str:
    same_brand = left.brand == right.brand and left.brand is not None
    same_block_key = (
        left.brand_blocking_key == right.brand_blocking_key and left.brand_blocking_key is not None
    )
    same_line = bool(left.product_line) and _norm_line(left.product_line) == _norm_line(
        right.product_line
    )
    # Plain equality on both fields — including None == None. A REAL bug lived here first: a
    # "both sides must state something" guard on net_volume_ml made every weight-only product
    # (net_volume_ml legitimately None on both sides, ADR-0026's mass-XOR-volume invariant) read
    # as "not the same capacity" by construction, since the guard fired on the volume field that
    # doesn't apply to a weight-based product at all — corrupting the trivial/hard split for the
    # overwhelming majority of the catalog. Caught by tracing one specific misclassified pair
    # (an Applaws Ton și Creveți 70g listing against its own identical cross-shop twin, wrongly
    # tagged "hard") rather than trusting the aggregate counts.
    same_capacity = (
        left.net_weight_g == right.net_weight_g and left.net_volume_ml == right.net_volume_ml
    )
    same_pack = left.pack_count == right.pack_count
    same_bonus = left.bonus_weight_g == right.bonus_weight_g
    same_flavour = left.flavour == right.flavour

    if same_brand and same_line and same_capacity and same_pack and same_bonus:
        return "trivial"
    if same_block_key and same_line and not (same_capacity and same_pack and same_bonus):
        return "hard"  # same model, different capacity/pack/bonus
    if (not same_block_key) and same_line and same_capacity:
        return "hard"  # same title/line, different brand string
    if same_block_key and same_line and same_capacity and same_pack and not same_flavour:
        return "hard"  # same model, different flavour
    return "easy"


def _fetch_listings(session, hashes: set[str]) -> dict[str, Listing]:  # type: ignore[no-untyped-def]
    rows = session.execute(_ATTRS_SQL, {"hashes": list(hashes)}).all()
    return {
        row.content_hash: Listing(
            content_hash=row.content_hash,
            brand=row.brand,
            product_line=row.product_line,
            net_weight_g=row.net_weight_g,
            net_volume_ml=row.net_volume_ml,
            pack_count=row.pack_count,
            bonus_weight_g=row.bonus_weight_g,
            breed_size_code=row.breed_size_code,
            life_stage=row.life_stage,
            flavour=row.flavour,
            food_form=row.food_form,
            source=row.sample_source,
            title=row.sample_title,
            brand_blocking_key=row.brand_blocking_key,
        )
        for row in rows
    }


def main() -> int:
    if not check_database():
        print("database UNREACHABLE", file=sys.stderr)
        return 2

    rng = random.Random(ANCHOR_SAMPLE_SEED)
    seen_pairs: set[tuple[str, str]] = set()

    with session_scope() as session:
        # --- Source 1: targeted hard-case query ---
        targeted_rows = session.execute(_TARGETED_HARD_SQL).all()
        targeted_hash_pairs: list[tuple[str, str]] = []
        for a_hash, b_hash in targeted_rows:
            key = tuple(sorted((a_hash, b_hash)))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            targeted_hash_pairs.append((a_hash, b_hash))
        print(f"targeted hard-case pairs found: {len(targeted_hash_pairs)}")

        # --- Source 2: pgvector top-20 retrieval over random anchors ---
        anchor_hashes = [r[0] for r in session.execute(_ANCHOR_SQL, {"n": ANCHOR_SAMPLE_SIZE})]
        print(f"anchors drawn: {len(anchor_hashes)}")

        retrieved_hash_pairs: list[tuple[str, str]] = []
        for anchor in anchor_hashes:
            candidates = session.execute(_CANDIDATES_SQL, {"self_hash": anchor, "k": TOP_K}).all()
            for (cand,) in candidates:
                key = tuple(sorted((anchor, cand)))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                retrieved_hash_pairs.append((anchor, cand))
        print(f"retrieval-drawn candidate pairs (deduped vs targeted): {len(retrieved_hash_pairs)}")

        needed_hashes: set[str] = set()
        for a, b in targeted_hash_pairs + retrieved_hash_pairs:
            needed_hashes.add(a)
            needed_hashes.add(b)
        listings = _fetch_listings(session, needed_hashes)

    def cross_shop(pairs: list[tuple[str, str]]) -> list[tuple[Listing, Listing]]:
        out = []
        for a, b in pairs:
            left, right = listings[a], listings[b]
            if left.source != right.source:
                out.append((left, right))
        return out

    targeted_pairs = cross_shop(targeted_hash_pairs)
    retrieved_pairs = cross_shop(retrieved_hash_pairs)
    print(f"targeted pairs, cross-shop: {len(targeted_pairs)}")
    print(f"retrieved pairs, cross-shop: {len(retrieved_pairs)}")

    tiered: dict[str, list[tuple[Listing, Listing]]] = {"trivial": [], "hard": [], "easy": []}
    for left, right in targeted_pairs + retrieved_pairs:
        tiered[classify_tier(left, right)].append((left, right))

    print(
        f"combined pool tiers: trivial={len(tiered['trivial'])}  hard={len(tiered['hard'])}  "
        f"easy={len(tiered['easy'])}"
    )

    # --- Trivial: auto-label, spot-check a random subset ---
    rng.shuffle(tiered["trivial"])
    auto_labelled = tiered["trivial"]
    spot_check = auto_labelled[:SPOT_CHECK_TRIVIAL_COUNT]

    # --- Build the human queue: ALL available hard-tier pairs (the floor is a minimum, not a
    # cap — every genuine hard case the targeted query found is worth including), easy tier
    # fills the rest ---
    non_trivial_target = QUEUE_SIZE_TARGET - len(spot_check)
    hard_target = max(int(non_trivial_target * HARD_CASE_FLOOR), 0)

    rng.shuffle(tiered["hard"])
    rng.shuffle(tiered["easy"])

    hard_selected = tiered["hard"][:non_trivial_target]  # take all available, bounded by queue size
    easy_needed = non_trivial_target - len(hard_selected)
    easy_selected = tiered["easy"][:easy_needed]
    shortfall = non_trivial_target - len(hard_selected) - len(easy_selected)
    if shortfall > 0:
        extra_easy = tiered["easy"][len(easy_selected) : len(easy_selected) + shortfall]
        easy_selected = easy_selected + extra_easy

    human_pairs = hard_selected + easy_selected + spot_check
    tier_labels = (
        ["hard"] * len(hard_selected)
        + ["easy"] * len(easy_selected)
        + ["trivial"] * len(spot_check)
    )

    def listing_dict(listing: Listing) -> dict[str, object]:
        return {
            "content_hash": listing.content_hash,
            "source": listing.source,
            "title": listing.title,
            "brand": listing.brand,
            "product_line": listing.product_line,
            "net_weight_g": listing.net_weight_g,
            "net_volume_ml": listing.net_volume_ml,
            "pack_count": listing.pack_count,
            "bonus_weight_g": listing.bonus_weight_g,
            "breed_size_code": listing.breed_size_code,
            "life_stage": listing.life_stage,
            "flavour": listing.flavour,
            "food_form": listing.food_form,
        }

    pairs_out = []
    for (left, right), tier in zip(human_pairs, tier_labels, strict=True):
        pair_id = f"{left.content_hash[:12]}_{right.content_hash[:12]}"
        pairs_out.append(
            {
                "pair_id": pair_id,
                "occurrence_id": f"{pair_id}_0",
                "tier": tier,
                "left": listing_dict(left),
                "right": listing_dict(right),
            }
        )

    queue_json = {
        "shuffle_seed": SHUFFLE_SEED,
        "built_from": "scripts/build_annotation_queue.py",
        "auto_labelled_count": len(auto_labelled),
        "pairs": pairs_out,
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(queue_json, ensure_ascii=False, indent=1), encoding="utf-8")

    total_drawn = len(human_pairs) + len(auto_labelled) - len(spot_check)
    print("\n" + "=" * 78)
    print("QUEUE REPORT")
    print("=" * 78)
    print(f"trivial-tier pairs found (auto-labelled M): {len(auto_labelled)}")
    print(f"  of which re-inserted as human spot-check: {len(spot_check)}")
    print(f"human queue size: {len(human_pairs)}")
    if human_pairs:
        print(
            f"  hard:    {len(hard_selected)} ({len(hard_selected) / len(human_pairs) * 100:.1f}%)"
        )
        print(
            f"  easy:    {len(easy_selected)} ({len(easy_selected) / len(human_pairs) * 100:.1f}%)"
        )
        print(
            f"  trivial (spot-check): {len(spot_check)} "
            f"({len(spot_check) / len(human_pairs) * 100:.1f}%)"
        )
    if shortfall > 0:
        print(
            f"  NOTE: hard-tier pool ({len(tiered['hard'])}) was short of the {hard_target}-pair "
            f"floor by {hard_target - len(hard_selected)}; topped up from easy to hit queue size."
        )
    fraction_removed = len(auto_labelled) / total_drawn if total_drawn else 0.0
    print(
        f"\nfraction of the {total_drawn}-pair draw auto-labelled away from the human queue: "
        f"{fraction_removed * 100:.1f}%"
    )
    est_hours = len(human_pairs) / 200
    print(f"estimated wall-clock for the human queue at 200 pairs/hour: {est_hours:.1f} hours")
    print(f"\nwritten: {OUTPUT_JSON.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
