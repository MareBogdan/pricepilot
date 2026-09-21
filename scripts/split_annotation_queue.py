r"""Phase 3 STEP 7 (rewritten, ADR-0028 addendum #11) — product-level TEST/TRAIN_VAL split of the
FROZEN annotation queue, tier-STRATIFIED this time, plus the deterministic-engine predictions the
assisted flow shows for TRAIN_VAL pairs only.

    uv run python scripts/split_annotation_queue.py

**Why a separate script, not a rebuild of the queue itself.** `docs/learned/phase3-annotation-
queue.json` is FROZEN (DECISIONS.md ADR-0028 addendum #9) — no further rebuild without a stated
reason recorded in STATE.md first. This script reads the frozen queue READ-ONLY and writes two
files; it never touches the queue itself. Every run SHA-256s the queue file first and refuses to
proceed if it doesn't match `FROZEN_QUEUE_SHA256` below (the value recorded the moment the queue
was frozen), so a future accidental edit to the "frozen" file is caught immediately rather than
silently producing a split of different data than this script's own docstring and the ADR entries
describe.

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

**One-component-dominates guard, unchanged from the first version.** One component has 281 of the
997 rows (28.2%) — checked directly, not assumed: 123 of its rows are `capacity_differs_cross_shop`
(123/209 = 58.9% of that WHOLE tier), the rest split across proxy_key_collision (83),
diff_brand_similar_title (23), trivial_spot_check (18), same_capacity_diff_lifestage (13),
same_capacity_diff_breedsize (11), capacity_differs_within_shop (9), blocked_retrieval_candidate
(1). Assigning it whole to a ~300-pair TEST split would make ~94% of the headline test set describe
one product family. Policy, applied uniformly: a component may not supply more than 30% of the
TEST target (target 300 -> cap 90 rows) to TEST; the 281-row component is the only one that
exceeds this and is routed to TRAIN_VAL. **Direct, measured consequence for
`capacity_differs_cross_shop` specifically**: only 209-123=86 of its 209 rows are even ELIGIBLE for
TEST once the giant component is excluded, against a target of 62.9 — feasible (86 >= 63), but the
tightest margin of any tier, and reported explicitly below rather than left to be discovered from
the output table alone.

**FIX 2 — TEST composition is now TIER-STRATIFIED, not filled by raw component size (ADR-0028
addendum #11).** The prior version's best-fit-decreasing walk optimized only for hitting the
300-row total, with no regard for per-tier balance, and produced a badly skewed TEST split
(e.g. capacity_differs_within_shop 3/300 in TEST vs. 73/697 in TRAIN_VAL) — unusable for CLAUDE.md
§7's required per-category results. Replaced with a seeded local-search optimizer: minimise
`sum_t (test_t - target_t)^2` over the 9 active tiers (`target_t = 300 * tier_totals_997[t] / 997`,
counted over the full 997 ROWS so a collided pair counts once per tier it actually appears under),
subject to the hard constraint `sum(test_t) == 300` and the component-cap exclusion above. Balances
ONLY on `tier` — `engine_prediction` is never a balancing input, reported afterward purely as a
diagnostic. Search: seeded best-fit-decreasing initial fill + exact-gap closing via singleton
components, then hill-climbing local search (equal-size swaps, and general remove-one/add-one
swaps rebalanced with singleton components to keep the row total exactly 300), many random
restarts per seed, best objective kept. Run under 5 different seeds
(`SPLIT_SEED, SPLIT_SEED+1..+4`) purely to report the objective's range across seeds — the
COMMITTED split always uses `SPLIT_SEED` specifically, never "whichever seed scored best" (that
would be tuning the split to a result, not measuring one).

**Acceptance gate, checked and enforced — the script exits non-zero if any of these fail:**
every active tier's `|TEST share - TRAIN_VAL share| <= 4.5` percentage points AND `TEST count >=
14`; 0 `content_hash` overlap between splits; exactly 997 assignment keys; no `engine_prediction`
key on any TEST entry.

**FIX 3 note (not this script).** Label export/import lives in `tools/annotate.html` — unrelated
to the split itself, listed here only so a reader of this docstring knows where the third fix in
this addendum landed.

Writes nothing to the database. Does not touch the frozen queue file. Starts no annotation.
"""

from __future__ import annotations

import hashlib
import io
import json
import random
import sys
from collections import Counter
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

# The frozen queue's own hash, recorded here the moment it was frozen (ADR-0028 addendum #9). If
# this ever disagrees with the file on disk, something edited the "frozen" file -- refuse to
# proceed rather than silently split different data than the one this script's own docstring and
# ADR entries describe.
FROZEN_QUEUE_SHA256 = "696e983392628b868c4becd92db400735a52498a4994b5b7c8651b160a087011"

TEST_TARGET = 300
COMPONENT_CAP_FRACTION = 0.30  # a component may not supply more than this share of TEST_TARGET
SPLIT_SEED = 20260917
REPORT_SEEDS = [SPLIT_SEED, SPLIT_SEED + 1, SPLIT_SEED + 2, SPLIT_SEED + 3, SPLIT_SEED + 4]
RESTARTS_PER_SEED = 12
ITERATIONS_PER_RESTART = 4000
TIER_GAP_LIMIT_PP = 4.5
TEST_MIN_PER_TIER = 14

_LIFE_STAGE_GROUP = {"puppy": "young", "junior": "young", "adult": "adult", "senior": "senior"}


# --- predict_label(), ported verbatim from build_annotation_queue.py (same ladder, same
# conventions.md revision 4) so the TRAIN_VAL suggestion and the frozen queue's own
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

    # Rule 3b — food form (conventions revision 4, 2026-09-21 mechanical rule-consistency pass).
    # dry vs wet/tin/pouch is a product difference (a kibble bag and a pouch/tin are physically
    # different SKUs); wet/tin/pouch are the same food form at different extractor granularity and
    # never a difference on their own. One-sided (either side null) falls through untouched.
    if left["food_form"] and right["food_form"]:
        l_dry = left["food_form"] == "dry"
        r_dry = right["food_form"] == "dry"
        if l_dry != r_dry:
            return "N", "rule3b_foodform_dry_vs_wet"

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


class Component:
    __slots__ = ("indices", "root", "size", "tier_counts")

    def __init__(self, root: str, indices: list[int], row_tiers: list[str]) -> None:
        self.root = root
        self.indices = indices
        self.size = len(indices)
        self.tier_counts: Counter[str] = Counter(row_tiers[i] for i in indices)


def objective(selected_tier_counts: Counter[str], targets: dict[str, float]) -> float:
    return sum((selected_tier_counts.get(t, 0) - target) ** 2 for t, target in targets.items())


def _sum_tier_counts(components: list[Component]) -> Counter[str]:
    total: Counter[str] = Counter()
    for c in components:
        total.update(c.tier_counts)
    return total


def _initial_solution(eligible: list[Component], rng: random.Random, target_total: int) -> set[str]:
    """Seeded best-fit-decreasing fill, then close the exact remaining gap with singleton
    components (there are 286 of them in this population -- always enough headroom)."""
    order = eligible[:]
    rng.shuffle(order)
    order.sort(key=lambda c: -c.size)  # best-fit-decreasing on top of the shuffle
    selected: set[str] = set()
    total = 0
    for c in order:
        if total + c.size <= target_total:
            selected.add(c.root)
            total += c.size
        if total >= target_total:
            break
    if total < target_total:
        remaining = target_total - total
        singles = [c for c in order if c.size == 1 and c.root not in selected]
        rng.shuffle(singles)
        for c in singles[:remaining]:
            selected.add(c.root)
            total += 1
    assert total == target_total, f"initial fill reached {total}, not {target_total}"
    return selected


def _local_search(
    eligible: list[Component],
    targets: dict[str, float],
    seed: int,
    restarts: int,
    iterations: int,
) -> tuple[set[str], float]:
    rng = random.Random(seed)
    by_root = {c.root: c for c in eligible}
    singles = [c.root for c in eligible if c.size == 1]

    best_selected: set[str] = set()
    best_obj = float("inf")

    for _restart in range(restarts):
        selected = _initial_solution(eligible, rng, TEST_TARGET)
        cur_counts = _sum_tier_counts([by_root[r] for r in selected])
        cur_obj = objective(cur_counts, targets)

        for _it in range(iterations):
            move = rng.random()
            unselected_pool = [c.root for c in eligible if c.root not in selected]
            if not unselected_pool:
                break
            if move < 0.6:
                # Equal-size swap: preserves the row total exactly, no rebalancing needed.
                out_root = rng.choice(sorted(selected))
                out_size = by_root[out_root].size
                candidates = [r for r in unselected_pool if by_root[r].size == out_size]
                if not candidates:
                    continue
                in_root = rng.choice(candidates)
            else:
                # General swap: remove one, add one of a DIFFERENT size, then rebalance the
                # row-count difference using singleton components so the total stays exactly
                # TEST_TARGET. Abandoned (skip this iteration) if not enough spare singles exist
                # in the needed direction.
                out_root = rng.choice(sorted(selected))
                out_size = by_root[out_root].size
                in_root = rng.choice(unselected_pool)
                in_size = by_root[in_root].size
                diff = out_size - in_size  # >0: need to add `diff` more rows; <0: remove `-diff`
                trial_selected = (selected - {out_root}) | {in_root}
                if diff > 0:
                    spare_singles = [r for r in singles if r not in trial_selected and r != in_root]
                    if len(spare_singles) < diff:
                        continue
                    rng.shuffle(spare_singles)
                    extra_add = spare_singles[:diff]
                    trial_selected |= set(extra_add)
                elif diff < 0:
                    removable_singles = [r for r in singles if r in trial_selected and r != in_root]
                    if len(removable_singles) < -diff:
                        continue
                    rng.shuffle(removable_singles)
                    extra_remove = removable_singles[:-diff]
                    trial_selected -= set(extra_remove)
                new_counts = _sum_tier_counts([by_root[r] for r in trial_selected])
                new_obj = objective(new_counts, targets)
                if new_obj <= cur_obj:
                    selected = trial_selected
                    cur_obj = new_obj
                continue

            trial_counts = cur_counts.copy()
            trial_counts.subtract(by_root[out_root].tier_counts)
            trial_counts.update(by_root[in_root].tier_counts)
            new_obj = objective(trial_counts, targets)
            if new_obj <= cur_obj:
                selected = (selected - {out_root}) | {in_root}
                cur_counts = trial_counts
                cur_obj = new_obj

        if cur_obj < best_obj:
            best_obj = cur_obj
            best_selected = set(selected)

    return best_selected, best_obj


def main() -> int:
    if not QUEUE_JSON.exists():
        print(f"frozen queue not found: {QUEUE_JSON}", file=sys.stderr)
        return 2

    raw_bytes = QUEUE_JSON.read_bytes()
    actual_hash = hashlib.sha256(raw_bytes).hexdigest()
    print(f"frozen queue SHA-256: {actual_hash}")
    if actual_hash != FROZEN_QUEUE_SHA256:
        print(
            f"REFUSING TO RUN: frozen queue hash does not match the recorded value "
            f"({FROZEN_QUEUE_SHA256}). The 'frozen' file has changed -- investigate before "
            f"splitting data this script was not written against.",
            file=sys.stderr,
        )
        return 1

    queue = json.loads(raw_bytes.decode("utf-8"))
    pairs = queue["pairs"]
    print(f"frozen queue: {len(pairs)} rows (read-only, not modified by this script)")

    # FIX 1 — derive occurrence_ids from row order, never trust the file's own field.
    occurrence_ids = derive_occurrence_ids(pairs)
    distinct_pair_ids = len({p["pair_id"] for p in pairs})
    collided = len(pairs) - distinct_pair_ids
    print(
        f"distinct pair_ids: {distinct_pair_ids}, rows with a repeated pair_id: {collided} "
        f"(each now gets a unique derived occurrence_id: _0, _1, ...)"
    )
    assert len(set(occurrence_ids)) == len(pairs), "derived occurrence_ids are not all unique!"

    row_tiers = [p["tier"] for p in pairs]
    tier_totals_997 = Counter(row_tiers)
    active_tiers = [t for t, n in tier_totals_997.items() if n > 0]
    targets = {t: TEST_TARGET * tier_totals_997[t] / len(pairs) for t in active_tiers}

    uf = UnionFind()
    for p in pairs:
        uf.union(p["left"]["content_hash"], p["right"]["content_hash"])

    component_indices: dict[str, list[int]] = {}
    for i, p in enumerate(pairs):
        root = uf.find(p["left"]["content_hash"])
        component_indices.setdefault(root, []).append(i)

    components = [Component(root, idxs, row_tiers) for root, idxs in component_indices.items()]
    sizes = sorted((c.size for c in components), reverse=True)
    print(f"connected components: {len(components)}")
    print(f"largest 10 component sizes (rows): {sizes[:10]}")

    cap = int(TEST_TARGET * COMPONENT_CAP_FRACTION)
    eligible = [c for c in components if c.size <= cap]
    excluded = [c for c in components if c.size > cap]
    if excluded:
        print(
            f"\n{len(excluded)} component(s) exceed the {cap}-row TEST cap "
            f"({COMPONENT_CAP_FRACTION * 100:.0f}% of target {TEST_TARGET}) and are routed "
            f"straight to TRAIN_VAL: sizes {sorted((c.size for c in excluded), reverse=True)}"
        )
        for c in excluded:
            print(f"  component {c.root[:8]}... tier composition: {dict(c.tier_counts)}")
            for tier, n in c.tier_counts.items():
                print(
                    f"    -> {n}/{tier_totals_997[tier]} of ALL '{tier}' rows sit in this "
                    f"excluded component (structural limit on how close TEST can get to its "
                    f"target for that tier)"
                )

    # --- FIX 2: seeded stratified optimization, 5 seeds for the range report, SPLIT_SEED is the
    # one actually committed. --------------------------------------------------------------------
    seed_objectives: dict[int, float] = {}
    canonical_selected: set[str] | None = None
    for seed in REPORT_SEEDS:
        selected, obj = _local_search(
            eligible, targets, seed, RESTARTS_PER_SEED, ITERATIONS_PER_RESTART
        )
        seed_objectives[seed] = obj
        print(f"seed {seed}: best objective (sum of squared tier-count deviations) = {obj:.3f}")
        if seed == SPLIT_SEED:
            canonical_selected = selected

    assert canonical_selected is not None
    obj_values = list(seed_objectives.values())
    print(
        f"\n5-seed objective range: min={min(obj_values):.3f}, max={max(obj_values):.3f} "
        f"(committed split uses seed {SPLIT_SEED}, objective={seed_objectives[SPLIT_SEED]:.3f} "
        f"-- NOT necessarily the best of the 5, by design: the seed is fixed, not cherry-picked)"
    )

    test_roots = canonical_selected
    train_val_roots = {c.root for c in components} - test_roots

    test_indices = sorted(i for r in test_roots for i in component_indices[r])
    train_val_indices = sorted(i for r in train_val_roots for i in component_indices[r])

    print(
        f"\nTEST split: {len(test_indices)} rows (target {TEST_TARGET}), "
        f"from {len(test_roots)} components"
    )
    print(f"TRAIN_VAL split: {len(train_val_indices)} rows, from {len(train_val_roots)} components")

    # --- acceptance gate ---------------------------------------------------------------------
    test_tier_counts = Counter(row_tiers[i] for i in test_indices)
    train_val_tier_counts = Counter(row_tiers[i] for i in train_val_indices)

    print("\n" + "=" * 96)
    print(
        f"{'tier':32s} {'TEST rows':>10s} {'TEST %':>8s} {'TRAINVAL rows':>14s} "
        f"{'TRAINVAL %':>11s} {'gap pp':>8s}"
    )
    print("=" * 96)
    gate_failures: list[str] = []
    for tier in sorted(active_tiers):
        t_n = test_tier_counts.get(tier, 0)
        tv_n = train_val_tier_counts.get(tier, 0)
        t_pct = t_n / len(test_indices) * 100 if test_indices else 0.0
        tv_pct = tv_n / len(train_val_indices) * 100 if train_val_indices else 0.0
        gap = abs(t_pct - tv_pct)
        flag = ""
        if gap > TIER_GAP_LIMIT_PP:
            flag += f"  GAP>{TIER_GAP_LIMIT_PP}pp"
            gate_failures.append(f"{tier}: gap {gap:.1f}pp exceeds {TIER_GAP_LIMIT_PP}pp")
        if t_n < TEST_MIN_PER_TIER:
            flag += f"  TEST<{TEST_MIN_PER_TIER}"
            gate_failures.append(f"{tier}: TEST count {t_n} below minimum {TEST_MIN_PER_TIER}")
        print(f"{tier:32s} {t_n:10d} {t_pct:7.1f}% {tv_n:14d} {tv_pct:10.1f}% {gap:7.1f}pp{flag}")
    print("=" * 96)

    # Distinct pair_ids per split, reported separately (evaluation note: TEST metrics must be
    # computed over DISTINCT pair_ids -- the repeat is for self-agreement, not a second test
    # point).
    test_pair_ids = {pairs[i]["pair_id"] for i in test_indices}
    train_val_pair_ids = {pairs[i]["pair_id"] for i in train_val_indices}
    print(
        f"\ndistinct pair_ids -- TEST: {len(test_pair_ids)} (of {len(test_indices)} rows), "
        f"TRAIN_VAL: {len(train_val_pair_ids)} (of {len(train_val_indices)} rows)"
    )

    # --- integrity checks (unchanged from the first version, still enforced) -------------------
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
        gate_failures.append(f"{len(overlap)} content_hash values appear in BOTH splits")
    print(
        f"integrity check: {len(test_hashes)} distinct listings in TEST, "
        f"{len(train_val_hashes)} in TRAIN_VAL, {len(overlap)} overlap (verified, not assumed)"
    )

    if len(test_indices) + len(train_val_indices) != len(pairs):
        gate_failures.append("TEST + TRAIN_VAL row count does not equal the queue's row count")

    # --- predictions: TRAIN_VAL only, in the split file the tool actually loads ---
    assignments: dict[str, dict[str, Any]] = {}
    label_forecast_trainval: dict[str, int] = {"M": 0, "N": 0, "S": 0}
    label_forecast_test_hidden: dict[str, int] = {"M": 0, "N": 0, "S": 0}
    test_reference: dict[str, dict[str, Any]] = {}

    for i in test_indices:
        p = pairs[i]
        occ_id = occurrence_ids[i]
        assignments[occ_id] = {"split": "test", "tier": p["tier"], "pair_id": p["pair_id"]}
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
            "pair_id": p["pair_id"],
            "engine_prediction": {"label": label, "rule": rule},
        }
        label_forecast_trainval[label] += 1

    if len(assignments) != len(pairs):
        gate_failures.append(
            f"assignments has {len(assignments)} keys, expected {len(pairs)} "
            "(occurrence_id derivation produced a collision)"
        )
    test_entries_with_prediction = [
        k for k, v in assignments.items() if v["split"] == "test" and "engine_prediction" in v
    ]
    if test_entries_with_prediction:
        gate_failures.append(
            f"{len(test_entries_with_prediction)} TEST entries carry an engine_prediction key"
        )

    print(
        f"\nTEST predicted-label forecast (hidden from the tool, reference file only): "
        f"{label_forecast_test_hidden}"
    )
    print(f"TRAIN_VAL predicted-label forecast (shown as suggestions): {label_forecast_trainval}")

    print("\n" + "=" * 78)
    if gate_failures:
        print("ACCEPTANCE GATE: FAILED")
        for f in gate_failures:
            print(f"  - {f}")
    else:
        print(
            "ACCEPTANCE GATE: PASSED (all tier gaps <=4.5pp, all TEST counts >=14, "
            "0 overlap, 997 keys, no TEST predictions)"
        )
    print("=" * 78)

    split_json = {
        "built_from": "scripts/split_annotation_queue.py (ADR-0028 addendum #11 rewrite), "
        "reading the FROZEN phase3-annotation-queue.json (never modifies it)",
        "frozen_queue_sha256": actual_hash,
        "split_seed": SPLIT_SEED,
        "report_seeds": REPORT_SEEDS,
        "seed_objectives": {str(s): o for s, o in seed_objectives.items()},
        "queue_source_row_count": len(pairs),
        "test_target": TEST_TARGET,
        "component_cap_fraction": COMPONENT_CAP_FRACTION,
        "component_cap_rows": cap,
        "excluded_oversized_components": sorted((c.size for c in excluded), reverse=True),
        "test_row_count": len(test_indices),
        "train_val_row_count": len(train_val_indices),
        "test_distinct_pair_ids": len(test_pair_ids),
        "train_val_distinct_pair_ids": len(train_val_pair_ids),
        "test_distinct_listings": len(test_hashes),
        "train_val_distinct_listings": len(train_val_hashes),
        "acceptance_thresholds": {
            "tier_gap_limit_pp": TIER_GAP_LIMIT_PP,
            "test_min_per_tier": TEST_MIN_PER_TIER,
        },
        "acceptance_gate_passed": not gate_failures,
        "acceptance_gate_failures": gate_failures,
        "per_tier_counts": {
            tier: {
                "test_rows": test_tier_counts.get(tier, 0),
                "train_val_rows": train_val_tier_counts.get(tier, 0),
                "test_pair_ids": len(
                    {pairs[i]["pair_id"] for i in test_indices if row_tiers[i] == tier}
                ),
                "train_val_pair_ids": len(
                    {pairs[i]["pair_id"] for i in train_val_indices if row_tiers[i] == tier}
                ),
            }
            for tier in sorted(active_tiers)
        },
        "evaluation_note": "TEST metrics must be computed over DISTINCT pair_ids -- the repeat "
        "occurrence of a pair_id (proxy_key_collision + trivial_spot_check, same underlying "
        "pair) is for self-agreement measurement, not a second independent test point.",
        # ADR-0028 addendum #12, TASK 2 -- the evaluation rules written down BEFORE any label
        # exists, mirrored here (machine-readable) from DECISIONS.md's own prose statement of
        # them, so a scoring script can read them rather than re-encode the same rules by hand.
        "evaluation_rules": {
            "adr_reference": "DECISIONS.md ADR-0028 addendum #12",
            "headline_test_metric_denominator": "287 DISTINCT pair_ids, not the 300 TEST rows",
            "headline_test_distinct_pair_ids": len(test_pair_ids),
            "repeat_tie_break": (
                "for a repeated pair_id, the evaluation label is the FIRST decision in DISPLAY "
                "order (tools/annotate.html buildOrder(), TASK 1 -- display order, not file "
                "order, decides). Resolved per-pair in "
                "docs/learned/phase3-repeat-first-occurrence.json. The second occurrence is used "
                "only for self-agreement, never as a second independent test point."
            ),
            "repeat_reporting_tier": "proxy_key_collision",
            "repeat_reporting_note": (
                "a repeated pair (drawn once under proxy_key_collision, once under "
                "trivial_spot_check) is attributed to tier proxy_key_collision for per-category "
                "reporting. trivial_spot_check is NOT reported as its own TEST category -- after "
                "excluding the 13 pairs it shares with proxy_key_collision, only 2 distinct "
                "pair_ids remain solely under trivial_spot_check in TEST, too few for a category "
                "line; reported as a footnote with its raw count instead."
            ),
            "trivial_spot_check_test_standalone_pair_ids": 2,
            "per_tier_ci_discipline": (
                "any per-tier figure (TEST counts span 14-86 pairs) must be reported with its "
                "denominator and a Wilson 95% CI, never a bare percentage -- the same discipline "
                "already applied to recall@20's 88% [76.2%, 94.4%]."
            ),
            "predicted_label_forecast_by_split": {
                "test": dict(label_forecast_test_hidden, of_rows=len(test_indices)),
                "train_val": dict(label_forecast_trainval, of_rows=len(train_val_indices)),
            },
            "predicted_label_forecast_note": (
                "the rules-engine forecast differs between splits by construction: the split is "
                "balanced on tier only, deliberately never on predicted label. This difference is "
                "a consequence, reported as a stated limitation for the README, not corrected."
            ),
        },
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

    return 1 if gate_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
