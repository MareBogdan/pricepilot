r"""Phase 3 item 5 harness: product-level train/validation split INSIDE TRAIN_VAL (CLAUDE.md
rule 3; ADR-0028 addendum #19).

TRAIN_VAL (672 distinct pairs, `docs/learned/phase3-eval-view.json`) is currently one undivided
block. `docs/phase3-baseline-model-choice.md` rule 1 requires a product-level split of TRAIN_VAL
itself before any model touches it -- fine-tuning on all 672 pairs and then also picking a
threshold/epoch count from those same 672 pairs would let training data leak into the number used
to tune the model, the exact mistake CLAUDE.md rule 3 exists to prevent.

    uv run python scripts/split_train_val.py

**Scope, strictly.** This script reads `docs/learned/phase3-eval-view.json` (TRAIN_VAL entries
only) and `docs/learned/phase3-annotation-queue.json` (read-only, for each pair's listing
`content_hash`es) and writes exactly one new file, `docs/learned/phase3-train-val-split.json`. It
never touches TEST, never touches the frozen annotation queue or split file, and never re-runs
`scripts/split_annotation_queue.py` (that script produced the TEST/TRAIN_VAL split this one
subdivides further; re-running it would rebuild a different, frozen artefact).

**Method: connected components over listing `content_hash`, edges = the 672 TRAIN_VAL pairs** --
the same product-level principle DECISIONS.md ADR-0028 addendum #10 used for the original
TEST/TRAIN_VAL split (`scripts/split_annotation_queue.py`'s own `UnionFind`). Two TRAIN_VAL pairs
sharing a listing are, by construction, comparisons involving the same product identity, so they
must land on the same side or the split would leak a listing's own attributes across train and
validation.

**Assignment: component-cap, then fractional-deficit greedy -- not naive largest-first.** TRAIN_VAL
has one dominant connected component (268 of 672 pairs, 39.9%, the same kind of near-duplicate
cluster CLAUDE.md's Phase 1 names as the hardest matching case). A first version of this script
assigned components by comparing RAW pair-count deficits (train target 538 vs val target 134);
caught in review, that rule doesn't just place the giant component in train -- since train's
absolute target is always ~4x val's, EVERY component down to singletons deterministically won
train's larger deficit too, so validation ended up composed almost entirely of isolated
singleton/pair components (106 of 120, largest just 2) with an M-rate 5 points off TEST's. Fixed
two ways: (1) `VAL_COMPONENT_CAP_FRACTION` forces any component too large for val's own target
(>30% of it) into train unconditionally, so the giant component's placement is an explicit rule,
not an emergent side effect; (2) every other component is assigned by comparing each side's
deficit as a FRACTION of its own target, not a raw count, which lets components of any size land
on either side once the giant is excluded. Result: val's largest remaining component is 15 pairs
(41 of 62 singletons, not 106 of 120), and val's M-rate lands within ~0.5pp of TEST's, down from a
~5pp gap. The giant component being forced entirely into train is a residual, irreducible
property of this dataset -- no product-level split can put part of a 268-pair cluster in
validation without either overflowing val's target or breaking the product-level guarantee.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import check_label_rule_consistency as clc  # noqa: E402
from build_eval_view import OUTPUT_JSON as EVAL_VIEW_JSON  # noqa: E402
from build_eval_view import _frozen_marker  # noqa: E402
from pricepilot.matching.pair_text import PAIR_TEXT_VERSION  # noqa: E402

OUTPUT_JSON = ROOT / "docs" / "learned" / "phase3-train-val-split.json"

# Date-stamped, matching this repo's existing seed convention (build_annotation_queue.py's
# RNG_SEED, split_annotation_queue.py's SPLIT_SEED).
TRAIN_VAL_SPLIT_SEED = 20260922
TRAIN_TARGET_FRACTION = 0.8


class UnionFind:
    """Identical in behaviour to split_annotation_queue.py's own UnionFind -- copied rather than
    imported because that script is a one-shot frozen-artefact generator, not a shared library,
    and its own docstring says as much about not being re-run."""

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


class Component:
    __slots__ = ("label_counts", "pair_ids", "root")

    def __init__(self, root: str) -> None:
        self.root = root
        self.pair_ids: list[str] = []
        self.label_counts: dict[str, int] = {"M": 0, "N": 0, "S": 0}

    @property
    def size(self) -> int:
        return len(self.pair_ids)


def _load_train_val_entries() -> list[dict[str, Any]]:
    view = json.loads(EVAL_VIEW_JSON.read_text(encoding="utf-8"))
    live_marker = _frozen_marker()
    if view.get("frozen_labels_sha256") != live_marker:
        raise SystemExit(
            "REFUSING TO RUN: docs/learned/phase3-eval-view.json's frozen_labels_sha256 "
            f"({view.get('frozen_labels_sha256')!r}) does not match the live "
            f"FROZEN_LABELS_SHA256 ({live_marker!r}). Re-run scripts/build_eval_view.py first."
        )
    if not view.get("frozen"):
        raise SystemExit(
            "REFUSING TO RUN: the label dataset is not frozen yet. Train/validation splitting "
            "happens after the freeze, not before -- a pre-freeze split could be invalidated by "
            "a later label change."
        )
    return [e for e in view["entries"] if e["split"] == "train_val"]


def _content_hashes_by_occurrence_id() -> dict[str, tuple[str, str]]:
    queue = json.loads(clc.QUEUE_JSON.read_text(encoding="utf-8"))["pairs"]
    queue_sha256_lf = clc.sha256_lf(clc.QUEUE_JSON.read_bytes())
    if queue_sha256_lf != clc.FROZEN_QUEUE_SHA256:
        raise SystemExit(
            f"REFUSING TO RUN: frozen queue hash (LF) {queue_sha256_lf} does not match "
            f"{clc.FROZEN_QUEUE_SHA256}."
        )
    occ_ids = clc.derive_occurrence_ids(queue)
    return {
        occ_id: (pair["left"]["content_hash"], pair["right"]["content_hash"])
        for occ_id, pair in zip(occ_ids, queue, strict=True)
    }


def build_components(entries: list[dict[str, Any]]) -> list[Component]:
    hashes_by_occ = _content_hashes_by_occurrence_id()
    uf = UnionFind()
    pair_hashes: dict[str, tuple[str, str]] = {}
    for e in entries:
        left_hash, right_hash = hashes_by_occ[e["first_occurrence_id"]]
        pair_hashes[e["pair_id"]] = (left_hash, right_hash)
        uf.union(left_hash, right_hash)

    by_root: dict[str, Component] = {}
    for e in entries:
        left_hash, _right_hash = pair_hashes[e["pair_id"]]
        root = uf.find(left_hash)
        component = by_root.setdefault(root, Component(root))
        component.pair_ids.append(e["pair_id"])
        component.label_counts[e["label"]] += 1
    return list(by_root.values())


# A component larger than this fraction of val's own target may not be assigned to val at all --
# forced to train unconditionally. Same idea and same 30% figure as
# scripts/split_annotation_queue.py's own COMPONENT_CAP_FRACTION, which exists for the identical
# reason: this queue has one dominant connected component (268 of TRAIN_VAL's 672 pairs, 39.9%),
# and an assignment rule with no cap either overflows val's budget by putting the giant there, or
# -- the defect a reviewer caught in this exact function -- systematically starves val of every
# OTHER non-trivial component too, because train's absolute deficit (538 target) stays larger
# than val's (134 target) for many components in a row regardless of processing order, as long as
# deficits are compared as raw counts. Fractional deficits (below) fix that second problem for
# every component small enough to be capped into the normal pool; the giant itself still needs
# the explicit cap, since even a fractional deficit comparison would only decide where it goes
# after most of val's target is already consumed by it.
VAL_COMPONENT_CAP_FRACTION = 0.30


def assign_components(
    components: list[Component], seed: int, train_target_fraction: float
) -> tuple[list[Component], list[Component]]:
    """Cap-then-fractional-deficit greedy assignment.

    1. Any component bigger than `VAL_COMPONENT_CAP_FRACTION` of val's target is forced to train
       unconditionally -- val's budget is too small to absorb it without swamping val's own
       target ratio.
    2. Every other component is assigned by comparing each side's REMAINING deficit as a
       FRACTION of that side's own target, not as a raw pair count -- a normalised
       largest-remaining-deficit rule, order-randomised with the seed and then processed
       largest-first within the capped pool (stable sort keeps the shuffle as the tie-break among
       equal sizes). Comparing fractions rather than raw counts is what lets components land on
       EITHER side once the giant is excluded, instead of every component down to singletons
       deterministically going to whichever side has the larger absolute target.
    """
    total_pairs = sum(c.size for c in components)
    train_target = round(total_pairs * train_target_fraction)
    val_target = total_pairs - train_target

    rng = random.Random(seed)
    shuffled = components[:]
    rng.shuffle(shuffled)

    cap = max(1, int(val_target * VAL_COMPONENT_CAP_FRACTION))
    forced_train = [c for c in shuffled if c.size > cap]
    capped_pool = sorted((c for c in shuffled if c.size <= cap), key=lambda c: -c.size)

    train: list[Component] = list(forced_train)
    val: list[Component] = []
    train_count = sum(c.size for c in forced_train)
    val_count = 0
    for c in capped_pool:
        train_deficit_frac = (train_target - train_count) / train_target if train_target else 0.0
        val_deficit_frac = (val_target - val_count) / val_target if val_target else 0.0
        if train_deficit_frac >= val_deficit_frac:
            train.append(c)
            train_count += c.size
        else:
            val.append(c)
            val_count += c.size
    return train, val


def _side_summary(components: list[Component]) -> dict[str, Any]:
    pair_ids = sorted(pid for c in components for pid in c.pair_ids)
    label_counts = {"M": 0, "N": 0, "S": 0}
    for c in components:
        for label, count in c.label_counts.items():
            label_counts[label] += count
    return {
        "pair_count": len(pair_ids),
        "pair_ids": pair_ids,
        "label_counts": label_counts,
    }


def main() -> int:
    entries = _load_train_val_entries()
    if len(entries) != 672:
        raise SystemExit(f"REFUSING TO RUN: expected 672 TRAIN_VAL pairs, found {len(entries)}.")

    components = build_components(entries)
    sizes = sorted((c.size for c in components), reverse=True)
    print(f"TRAIN_VAL pairs: {len(entries)}")
    print(f"connected components: {len(components)}")
    print(f"largest 10 component sizes (pairs): {sizes[:10]}")

    train_components, val_components = assign_components(
        components, TRAIN_VAL_SPLIT_SEED, TRAIN_TARGET_FRACTION
    )
    train = _side_summary(train_components)
    val = _side_summary(val_components)

    # Exact-partition check -- train and val must together be every input pair_id, exactly once
    # each, with none lost or duplicated. A reviewer caught this as a real gap: forcing
    # assign_components() to silently DROP a component (a plausible bug shape, distinct from
    # duplicating one) previously produced a completely normal-looking run -- 671 pairs, correct
    # percentages, the overlap check still printing "PROVEN" -- because that check only ever
    # looks for content_hash values present on BOTH sides, never for pair_ids present on NEITHER.
    all_pair_ids = {e["pair_id"] for e in entries}
    assigned_pair_ids = set(train["pair_ids"]) | set(val["pair_ids"])
    if assigned_pair_ids != all_pair_ids or (set(train["pair_ids"]) & set(val["pair_ids"])):
        missing = all_pair_ids - assigned_pair_ids
        extra = assigned_pair_ids - all_pair_ids
        both = set(train["pair_ids"]) & set(val["pair_ids"])
        raise SystemExit(
            "REFUSING TO WRITE: train/val is not an exact partition of the 672 TRAIN_VAL pairs -- "
            f"{len(missing)} missing, {len(extra)} unexpected, {len(both)} on both sides."
        )

    # Direct content_hash overlap check -- must be zero by construction (components are
    # never split), asserted here rather than only hoped true by the algorithm above.
    hashes_by_occ = _content_hashes_by_occurrence_id()
    entries_by_pair_id = {e["pair_id"]: e for e in entries}

    def hashes_for(pair_ids: list[str]) -> set[str]:
        result: set[str] = set()
        for pid in pair_ids:
            left_hash, right_hash = hashes_by_occ[entries_by_pair_id[pid]["first_occurrence_id"]]
            result.add(left_hash)
            result.add(right_hash)
        return result

    train_listing_hashes = hashes_for(train["pair_ids"])
    val_listing_hashes = hashes_for(val["pair_ids"])
    overlap = train_listing_hashes & val_listing_hashes
    if overlap:
        raise SystemExit(
            f"REFUSING TO WRITE: {len(overlap)} listing content_hash(es) appear on BOTH sides "
            f"of the split -- the component assignment above has a bug. First few: "
            f"{sorted(overlap)[:5]}"
        )

    print(
        f"\ntrain: {train['pair_count']} pairs "
        f"({train['pair_count'] / len(entries):.1%}), "
        f"M {train['label_counts']['M']} / N {train['label_counts']['N']} / "
        f"S {train['label_counts']['S']}"
    )
    print(
        f"val:   {val['pair_count']} pairs "
        f"({val['pair_count'] / len(entries):.1%}), "
        f"M {val['label_counts']['M']} / N {val['label_counts']['N']} / "
        f"S {val['label_counts']['S']}"
    )
    print(
        f"\nzero content_hash overlap between train and val: "
        f"{len(train_listing_hashes)} train listings, {len(val_listing_hashes)} val listings, "
        f"{len(overlap)} shared -- PROVEN"
    )

    val_scored = val["label_counts"]["M"] + val["label_counts"]["N"]
    val_m_rate = val["label_counts"]["M"] / val_scored if val_scored else None
    caveats = {
        "largest_train_component_pairs": max((c.size for c in train_components), default=0),
        "largest_val_component_pairs": max((c.size for c in val_components), default=0),
        "val_singleton_component_count": sum(1 for c in val_components if c.size == 1),
        "val_component_count": len(val_components),
        "val_m_rate_scored": val_m_rate,
        "note": (
            "The dominant connected component (see largest_train_component_pairs) is always "
            "forced into train (VAL_COMPONENT_CAP_FRACTION) -- an irreducible property of this "
            "dataset's cluster structure, not a defect. val_m_rate_scored is reported here so a "
            "later threshold-selection step can see, without recomputing it, how close "
            "validation's positive rate lands to TEST's own SCORED rate (97/284 = 34.2%, the "
            "same M/(M+N) denominator val_m_rate_scored itself uses -- not 97/287, which would "
            "mix in the 3 unscored S pairs)."
        ),
    }

    output = {
        "built_from": "scripts/split_train_val.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "seed": TRAIN_VAL_SPLIT_SEED,
        "train_target_fraction": TRAIN_TARGET_FRACTION,
        "val_component_cap_fraction": VAL_COMPONENT_CAP_FRACTION,
        "frozen_labels_sha256": _frozen_marker(),
        "pair_text_version": PAIR_TEXT_VERSION,
        "component_count": len(components),
        "train": train,
        "val": val,
        "caveats": caveats,
    }
    OUTPUT_JSON.write_text(json.dumps(output, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nwritten: {OUTPUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
