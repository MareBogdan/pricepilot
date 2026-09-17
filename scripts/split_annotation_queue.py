r"""Phase 3 STEP 7 — product-level TEST / TRAIN_VAL split of the FROZEN annotation queue, plus the
deterministic-engine predictions the assisted flow shows for TRAIN_VAL pairs only.

    uv run python scripts/split_annotation_queue.py

**Why a separate script, not a rebuild of the queue itself.** `docs/learned/phase3-annotation-
queue.json` is FROZEN (DECISIONS.md ADR-0028 addendum #9) — no further rebuild without a stated
reason recorded in STATE.md first. Splitting it into TEST/TRAIN_VAL is a read-only, additive step:
this script reads the frozen queue and writes two NEW files, never touching the queue itself.

**FIX 1 — occurrence_id collisions (ADR-0028 addendum #11).** The frozen queue has 997 rows but
only 959 distinct `occurrence_id` values: `build_annotation_queue.py` hardcodes
`occurrence_id = f"{pair_id}_0"`, and 38 pair_ids appear TWICE in the frozen file — always as one
`proxy_key_collision` row and one `trivial_spot_check` row, the source query's own dedup missing
this specific cross-tier duplication (the trivial-tier pass scans already-selected pairs for
byte-identical attributes and can re-select one that a category query already placed elsewhere).
Both rows then collide on `occurrence_id`, which breaks two things: the split file can only have
959 keys where it needs 997, and `tools/annotate.html`'s own `state` dict (keyed by
`occurrence_id`) treats the second showing as already-decided the instant the first is, so it is
never actually shown to the annotator. **Fixed here by deriving the id deterministically from
frozen-file ROW ORDER, never trusting the file's own (colliding) field**:
`occurrence_id = f"{pair_id}_{k}"`, `k` = 0-based ordinal of that `pair_id` among the queue file's
rows, in file order. `tools/annotate.html` derives the identical id the identical way before
merging the split file, so the two can never disagree.

**Why product-level, not pair-level (CLAUDE.md §7 item 4).** A pair-level random split lets the
same listing appear on both sides of the TEST/TRAIN boundary — e.g. listing A paired with B in
TEST and the same listing A paired with C in TRAIN — which leaks identity-specific cues the model
can memorize (a specific title's quirks, not the matching task) across the boundary. The fix:
treat the queue's own pairs as edges of a graph over `content_hash` nodes, take CONNECTED
COMPONENTS (union-find), and assign a whole component to one split — every listing's component
goes entirely to TEST or entirely to TRAIN_VAL, so a listing is structurally unable to appear in
both. There is no ground-truth "real product id" in this dataset (that's the whole reason matching
is hard); a connected component of the queue's own pairs is the strongest defensible proxy
available, since two listings connected by any queue pair are, by construction, being compared as
candidates for the same product identity.

**One-component-dominates guard.** The real component-size distribution has one component of 281
pairs (28.2% of the 997-pair queue) — almost certainly one popular, many-variant product family
chained together through several capacity_differs/proxy_key comparisons. Assigning it whole to a
~300-pair TEST split would make ~94% of the headline test set describe ONE product family, which
defeats the purpose of a product-level split (avoiding any one product dominating a metric).
**Policy, applied uniformly, not hand-picked for this one case**: a component may not contribute
more than 30% of the TEST target size (target 300 -> cap 90 pairs) to TEST; anything larger is
routed to TRAIN_VAL instead, where it is one of many pairs among ~700 rather than the entire
signal.

**Filling TEST to ~300.** After removing the one over-cap component, a seeded shuffle + best-fit
walk over the remaining components (382 total, most of them singletons or pairs — see the size
histogram this script prints) assembles TEST as close to the 300 target as the available component
sizes allow, without any single remaining component exceeding the 90-pair cap.

**TRAIN_VAL predictions.** For every TRAIN_VAL pair, this script also computes the deterministic
rules engine's prediction (`predict_label()`, ported from `build_annotation_queue.py` — same
ladder, same conventions.md revision 3) and writes it into the split file next to that pair's
`occurrence_id`. **TEST pairs get NO prediction field in this file, full stop** — not `null`, not
present at all — so `tools/annotate.html` has no field to accidentally render even by a future bug.
A second, separate file (`phase3-test-split-reference-predictions.json`) holds the TEST pairs'
predictions for later offline evaluation ONLY; it is never fetched by `tools/annotate.html` and is
named to make that obvious.

Writes nothing to the database. Does not touch the frozen queue file. Starts no annotation.
"""

from __future__ import annotations

import io
import json
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from pricepilot.normalize.attributes import breed_size_overlaps  # noqa: E402

QUEUE_JSON = ROOT / "docs" / "learned" / "phase3-annotation-queue.json"
SPLIT_JSON = ROOT / "docs" / "learned" / "phase3-annotation-split.json"
TEST_REFERENCE_JSON = ROOT / "docs" / "learned" / "phase3-test-split-reference-predictions.json"

TEST_TARGET = 300
COMPONENT_CAP_FRACTION = 0.30  # a component may not supply more than this share of TEST_TARGET
SPLIT_SEED = 20260917

_LIFE_STAGE_GROUP = {"puppy": "young", "junior": "young", "adult": "adult", "senior": "senior"}


# --- predict_label(), ported verbatim from build_annotation_queue.py (same ladder, same
# conventions.md revision 3) so the TRAIN_VAL suggestion and the frozen queue's own
# `predicted_label_forecast` can never disagree on what the rules engine says for a given pair. ---
def _quantity_tuple(listing: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    pack = listing["pack_count"] if listing["pack_count"] is not None else 1
    bonus = listing["bonus_weight_g"] if listing["bonus_weight_g"] is not None else 0
    return (listing["net_weight_g"], listing["net_volume_ml"], pack, bonus)


def _has_quantity(listing: dict[str, Any]) -> bool:
    return listing["net_weight_g"] is not None or listing["net_volume_ml"] is not None


def predict_label(left: dict[str, Any], right: dict[str, Any]) -> tuple[str, str]:
    # Rule 0 (out-of-scope category) is skipped here, deliberately, not reconstructed: the frozen
    # queue's `listing_dict()` never persisted `category` per-pair (checked directly, not assumed
    # — a real gap in that file, unrelated to this script), and `build_annotation_queue.py`'s own
    # `main()` already applies `in_scope_only()` (category in food/litter, both sides) to every
    # pool before writing the frozen file. Every pair reaching this function is therefore
    # already known in-scope by construction; rule 0 cannot fire on this data regardless.
    if left.get("species") and right.get("species") and left["species"] != right["species"]:
        return "N", "rule1_species_differs"

    if not _has_quantity(left) or not _has_quantity(right):
        return "S", "rule7_no_quantity_stated"

    if _quantity_tuple(left) != _quantity_tuple(right):
        return "N", "rule2_quantity_differs"

    if left["life_stage"] and right["life_stage"]:
        lg = _LIFE_STAGE_GROUP.get(left["life_stage"], left["life_stage"])
        rg = _LIFE_STAGE_GROUP.get(right["life_stage"], right["life_stage"])
        if lg != rg:
            return "N", "rule3_lifestage_differs"

    if breed_size_overlaps(left["breed_size_code"], right["breed_size_code"]) is False:
        return "N", "rule4_breedsize_differs"

    if left["flavour"] and right["flavour"] and left["flavour"] != right["flavour"]:
        return "N", "rule5_flavour_differs"

    one_sided = (
        (left["flavour"] is None) != (right["flavour"] is None)
        or (left["life_stage"] is None) != (right["life_stage"] is None)
        or (left["breed_size_code"] is None) != (right["breed_size_code"] is None)
    )
    if one_sided:
        return "S", "one_sided_attribute"

    if left["brand"] != right["brand"]:
        return "S", "ambiguous_brand_rule6"

    return "M", "default_M"


def derive_occurrence_ids(pairs: list[dict[str, Any]]) -> list[str]:
    """FIX 1 — `occurrence_id = f"{pair_id}_{k}"`, k = 0-based ordinal of that pair_id among the
    frozen file's rows, IN FILE ORDER. Never reads the file's own (colliding) `occurrence_id`
    field. `tools/annotate.html` derives the identical id from the identical rule."""
    counts: dict[str, int] = {}
    ids = []
    for p in pairs:
        pid = p["pair_id"]
        k = counts.get(pid, 0)
        ids.append(f"{pid}_{k}")
        counts[pid] = k + 1
    return ids


# --- union-find over content_hash, edges = the frozen queue's own pairs ---
class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def main() -> int:
    if not QUEUE_JSON.exists():
        print(f"frozen queue not found: {QUEUE_JSON}", file=sys.stderr)
        return 2

    queue = json.loads(QUEUE_JSON.read_text(encoding="utf-8"))
    pairs = queue["pairs"]
    print(f"frozen queue: {len(pairs)} pairs (read-only, not modified by this script)")

    # FIX 1 — derive occurrence_ids from row order, never trust the file's own field.
    occurrence_ids = derive_occurrence_ids(pairs)
    distinct_pair_ids = len({p["pair_id"] for p in pairs})
    print(
        f"distinct pair_ids: {distinct_pair_ids}, rows with a repeated pair_id: "
        f"{len(pairs) - distinct_pair_ids} (each now gets a unique derived occurrence_id)"
    )
    assert len(set(occurrence_ids)) == len(pairs), "derived occurrence_ids are not all unique!"

    uf = UnionFind()
    for p in pairs:
        uf.union(p["left"]["content_hash"], p["right"]["content_hash"])

    component_pairs: dict[str, list[int]] = {}
    for i, p in enumerate(pairs):
        root = uf.find(p["left"]["content_hash"])
        component_pairs.setdefault(root, []).append(i)

    sizes = sorted((len(v) for v in component_pairs.values()), reverse=True)
    print(f"connected components: {len(component_pairs)}")
    print(f"largest 10 component sizes (pairs): {sizes[:10]}")

    cap = int(TEST_TARGET * COMPONENT_CAP_FRACTION)
    eligible = {root: idxs for root, idxs in component_pairs.items() if len(idxs) <= cap}
    excluded = {root: idxs for root, idxs in component_pairs.items() if len(idxs) > cap}
    if excluded:
        print(
            f"\n{len(excluded)} component(s) exceed the {cap}-pair TEST cap "
            f"({COMPONENT_CAP_FRACTION * 100:.0f}% of target {TEST_TARGET}) and are routed "
            f"straight to TRAIN_VAL: sizes {sorted((len(v) for v in excluded.values()), reverse=True)}"
        )

    # Seeded shuffle + best-fit walk to assemble TEST as close to TEST_TARGET as the available
    # component sizes allow, never exceeding the per-component cap (already enforced above by
    # exclusion) and never exceeding TEST_TARGET by more than one component's worth.
    rng = random.Random(SPLIT_SEED)
    eligible_roots = list(eligible.keys())
    rng.shuffle(eligible_roots)
    eligible_roots.sort(
        key=lambda r: -len(eligible[r])
    )  # best-fit-decreasing on top of the shuffle

    test_roots: set[str] = set()
    test_count = 0
    for root in eligible_roots:
        size = len(eligible[root])
        if test_count + size <= TEST_TARGET:
            test_roots.add(root)
            test_count += size
        if test_count >= TEST_TARGET:
            break

    train_val_roots = set(component_pairs.keys()) - test_roots

    test_indices = sorted(i for r in test_roots for i in component_pairs[r])
    train_val_indices = sorted(i for r in train_val_roots for i in component_pairs[r])

    print(
        f"\nTEST split: {len(test_indices)} pairs (target {TEST_TARGET}), "
        f"from {len(test_roots)} components"
    )
    print(
        f"TRAIN_VAL split: {len(train_val_indices)} pairs, from {len(train_val_roots)} components"
    )

    # Product-level integrity check, not just assumed from the construction.
    test_hashes = {
        h
        for i in test_indices
        for h in (pairs[i]["left"]["content_hash"], pairs[i]["right"]["content_hash"])
    }
    train_val_hashes = {
        h
        for i in train_val_indices
        for h in (pairs[i]["left"]["content_hash"], pairs[i]["right"]["content_hash"])
    }
    overlap = test_hashes & train_val_hashes
    if overlap:
        print(f"INTEGRITY FAILURE: {len(overlap)} content_hash values appear in BOTH splits!")
        return 1
    print(
        f"integrity check: {len(test_hashes)} distinct listings in TEST, "
        f"{len(train_val_hashes)} in TRAIN_VAL, 0 overlap (verified, not assumed)"
    )

    # --- predictions: TRAIN_VAL only, in the split file the tool actually loads ---
    assignments: dict[str, dict[str, Any]] = {}
    tier_counts_test: dict[str, int] = {}
    tier_counts_trainval: dict[str, int] = {}
    label_forecast_trainval: dict[str, int] = {"M": 0, "N": 0, "S": 0}
    label_forecast_test_hidden: dict[str, int] = {"M": 0, "N": 0, "S": 0}
    test_reference: dict[str, dict[str, Any]] = {}

    for i in test_indices:
        p = pairs[i]
        occ_id = occurrence_ids[i]
        assignments[occ_id] = {"split": "test", "tier": p["tier"]}
        tier_counts_test[p["tier"]] = tier_counts_test.get(p["tier"], 0) + 1
        label, rule = predict_label(p["left"], p["right"])
        label_forecast_test_hidden[label] += 1
        test_reference[occ_id] = {
            "pair_id": p["pair_id"],
            "engine_prediction": {"label": label, "rule": rule},
        }

    for i in train_val_indices:
        p = pairs[i]
        occ_id = occurrence_ids[i]
        label, rule = predict_label(p["left"], p["right"])
        assignments[occ_id] = {
            "split": "train_val",
            "tier": p["tier"],
            "engine_prediction": {"label": label, "rule": rule},
        }
        tier_counts_trainval[p["tier"]] = tier_counts_trainval.get(p["tier"], 0) + 1
        label_forecast_trainval[label] += 1

    assert len(assignments) == len(pairs), (
        f"assignments has {len(assignments)} keys, expected {len(pairs)} "
        "(occurrence_id derivation produced a collision)"
    )

    print("\nTEST tier composition:")
    for tier, n in sorted(tier_counts_test.items(), key=lambda x: -x[1]):
        print(f"  {tier:32s} {n:4d} ({n / len(test_indices) * 100:5.1f}%)")
    print("\nTRAIN_VAL tier composition:")
    for tier, n in sorted(tier_counts_trainval.items(), key=lambda x: -x[1]):
        print(f"  {tier:32s} {n:4d} ({n / len(train_val_indices) * 100:5.1f}%)")

    print(
        f"\nTEST predicted-label forecast (hidden from the tool, reference file only): "
        f"{label_forecast_test_hidden}"
    )
    print(f"TRAIN_VAL predicted-label forecast (shown as suggestions): {label_forecast_trainval}")

    split_json = {
        "built_from": "scripts/split_annotation_queue.py, reading the FROZEN "
        "phase3-annotation-queue.json (never modifies it)",
        "split_seed": SPLIT_SEED,
        "queue_source_pair_count": len(pairs),
        "test_target": TEST_TARGET,
        "component_cap_fraction": COMPONENT_CAP_FRACTION,
        "component_cap_pairs": cap,
        "excluded_oversized_components": sorted((len(v) for v in excluded.values()), reverse=True),
        "test_pair_count": len(test_indices),
        "train_val_pair_count": len(train_val_indices),
        "test_distinct_listings": len(test_hashes),
        "train_val_distinct_listings": len(train_val_hashes),
        # Deliberately NOT included: any per-pair prediction for TEST occurrence_ids. Only
        # TRAIN_VAL entries in `assignments` carry an "engine_prediction" key.
        "assignments": assignments,
    }
    SPLIT_JSON.write_text(json.dumps(split_json, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwritten: {SPLIT_JSON.relative_to(ROOT)}")

    TEST_REFERENCE_JSON.write_text(
        json.dumps(
            {
                "WARNING": "Reference predictions for the TEST split, for POST-HOC evaluation "
                "only. tools/annotate.html never fetches this file. Do not open this file while "
                "labelling the TEST split -- it defeats the blind design.",
                "predictions": test_reference,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"written: {TEST_REFERENCE_JSON.relative_to(ROOT)} (NOT loaded by the annotation tool)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
