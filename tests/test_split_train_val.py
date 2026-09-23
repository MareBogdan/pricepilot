"""Tests for scripts/split_train_val.py's committed output,
docs/learned/phase3-train-val-split.json (ADR-0028 addendum #19), plus direct tests of the
component-building/assignment functions and the leakage guard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_label_rule_consistency as clc  # noqa: E402
import split_train_val as stv  # noqa: E402

SPLIT_JSON = ROOT / "docs" / "learned" / "phase3-train-val-split.json"
QUEUE_JSON = ROOT / "docs" / "learned" / "phase3-annotation-queue.json"


def _load() -> dict:
    return json.loads(SPLIT_JSON.read_text(encoding="utf-8"))


def test_train_and_val_pair_counts_sum_to_672_with_no_overlap() -> None:
    d = _load()
    train_ids = set(d["train"]["pair_ids"])
    val_ids = set(d["val"]["pair_ids"])
    assert len(train_ids) == d["train"]["pair_count"]
    assert len(val_ids) == d["val"]["pair_count"]
    assert d["train"]["pair_count"] + d["val"]["pair_count"] == 672
    assert not (train_ids & val_ids)


def test_roughly_80_20_by_pair_count() -> None:
    d = _load()
    fraction = d["train"]["pair_count"] / 672
    assert 0.75 <= fraction <= 0.85, f"train fraction {fraction:.3f} not close to 80%"


def test_label_counts_sum_to_side_totals() -> None:
    d = _load()
    for side in ("train", "val"):
        s = d[side]
        assert sum(s["label_counts"].values()) == s["pair_count"]


def test_frozen_labels_sha256_and_pair_text_version_recorded() -> None:
    d = _load()
    assert d["frozen_labels_sha256"] == stv._frozen_marker()
    from pricepilot.matching.pair_text import PAIR_TEXT_VERSION

    assert d["pair_text_version"] == PAIR_TEXT_VERSION


def test_zero_listing_content_hash_overlap_between_train_and_val_independently_verified() -> None:
    """Cross-checked against the frozen queue directly (an independent source from the split
    file's own claim), the same style test_build_eval_view.py uses for the TEST/TRAIN_VAL split."""
    d = _load()
    queue = json.loads(QUEUE_JSON.read_text(encoding="utf-8"))["pairs"]
    occ_ids = clc.derive_occurrence_ids(queue)
    pairs_by_occ = dict(zip(occ_ids, queue, strict=True))

    # Need pair_id -> occurrence_id; reconstruct via eval view's first_occurrence_id.
    eval_view = json.loads(
        (ROOT / "docs" / "learned" / "phase3-eval-view.json").read_text(encoding="utf-8")
    )
    first_occ_by_pair = {
        e["pair_id"]: e["first_occurrence_id"]
        for e in eval_view["entries"]
        if e["split"] == "train_val"
    }

    def hashes_for(pair_ids: list[str]) -> set[str]:
        result: set[str] = set()
        for pid in pair_ids:
            pair = pairs_by_occ[first_occ_by_pair[pid]]
            result.add(pair["left"]["content_hash"])
            result.add(pair["right"]["content_hash"])
        return result

    train_hashes = hashes_for(d["train"]["pair_ids"])
    val_hashes = hashes_for(d["val"]["pair_ids"])
    assert not (train_hashes & val_hashes)


def test_component_count_matches_committed_value() -> None:
    d = _load()
    entries = stv._load_train_val_entries()
    components = stv.build_components(entries)
    assert len(components) == d["component_count"]


def test_assignment_is_deterministic_for_the_committed_seed() -> None:
    entries = stv._load_train_val_entries()
    components_a = stv.build_components(entries)
    train_a, val_a = stv.assign_components(
        components_a, stv.TRAIN_VAL_SPLIT_SEED, stv.TRAIN_TARGET_FRACTION
    )
    components_b = stv.build_components(entries)
    train_b, val_b = stv.assign_components(
        components_b, stv.TRAIN_VAL_SPLIT_SEED, stv.TRAIN_TARGET_FRACTION
    )
    assert {c.root for c in train_a} == {c.root for c in train_b}
    assert {c.root for c in val_a} == {c.root for c in val_b}


def test_recomputed_assignment_matches_the_committed_file_exactly_pair_id_for_pair_id() -> None:
    """The gap every other test in this file leaves open (a reviewer finding): none of them
    recompute the real assignment and compare it, pair_id for pair_id, against the committed
    docs/learned/phase3-train-val-split.json -- every other check only verifies the FILE is
    internally consistent (counts sum, no overlap, deterministic against itself), which stays
    green even if a code change silently produces a DIFFERENT, equally internally-consistent
    split than the one actually committed (proven: swapping TRAIN_VAL_SPLIT_SEED for a different
    seed changes the assignment but leaves every other test in this file passing). This test
    closes that gap directly, and by construction also regression-pins the two behaviours the
    module docstring says review caught (the component cap and the fractional-deficit rule) --
    reverting either one changes the assignment this test would then catch."""
    d = _load()
    entries = stv._load_train_val_entries()
    components = stv.build_components(entries)
    train_components, val_components = stv.assign_components(
        components, stv.TRAIN_VAL_SPLIT_SEED, stv.TRAIN_TARGET_FRACTION
    )
    recomputed_train = stv._side_summary(train_components)
    recomputed_val = stv._side_summary(val_components)
    assert recomputed_train["pair_ids"] == d["train"]["pair_ids"]
    assert recomputed_val["pair_ids"] == d["val"]["pair_ids"]
    assert recomputed_train["label_counts"] == d["train"]["label_counts"]
    assert recomputed_val["label_counts"] == d["val"]["label_counts"]


def test_component_larger_than_the_cap_always_lands_in_train() -> None:
    """Direct pin on VAL_COMPONENT_CAP_FRACTION (a reviewer finding: the docstring narrates this
    rule at length but nothing tested it directly). A component sized just over the cap must be
    forced to train regardless of the random shuffle seed or of val's remaining deficit."""

    class FakeComponent:
        def __init__(self, root: str, size: int) -> None:
            self.root = root
            self.pair_ids = [f"{root}_{i}" for i in range(size)]
            self.label_counts = {"M": 0, "N": size, "S": 0}

        @property
        def size(self) -> int:
            return len(self.pair_ids)

    total = 100
    val_target = total - round(total * stv.TRAIN_TARGET_FRACTION)  # 20
    cap = max(1, int(val_target * stv.VAL_COMPONENT_CAP_FRACTION))  # 6
    oversized = FakeComponent("oversized", cap + 1)
    filler = [FakeComponent(f"small_{i}", 1) for i in range(total - oversized.size)]
    components = [oversized, *filler]

    for seed in (1, 2, 3, 4, 5):
        _train, val = stv.assign_components(components, seed=seed, train_target_fraction=0.8)  # type: ignore[arg-type]
        val_roots = {c.root for c in val}
        assert "oversized" not in val_roots, f"seed={seed}: oversized component leaked into val"


def test_fractional_deficit_lets_small_components_reach_val_even_after_a_giant_is_excluded() -> (
    None
):
    """Direct pin on the raw-vs-fractional deficit fix (a reviewer finding). With a dominant
    component removed by the cap, several equal-size remaining components must be split across
    BOTH sides by the fractional-deficit rule -- a raw-count deficit comparison (the pre-review
    bug) would send every one of them to train, since train's absolute target stays larger than
    val's for many components in a row regardless of order."""

    class FakeComponent:
        def __init__(self, root: str, size: int) -> None:
            self.root = root
            self.pair_ids = [f"{root}_{i}" for i in range(size)]
            self.label_counts = {"M": 0, "N": size, "S": 0}

        @property
        def size(self) -> int:
            return len(self.pair_ids)

    giant = FakeComponent("giant", 60)  # forced to train by the cap
    mid_sized = [FakeComponent(f"mid_{i}", 4) for i in range(10)]  # 40 pairs, cap-eligible
    components = [giant, *mid_sized]

    _train, val = stv.assign_components(components, seed=7, train_target_fraction=0.8)
    val_roots = {c.root for c in val}
    assert val_roots, "val received nothing but the giant's exclusion should have left room"
    assert "giant" not in val_roots
    assert any(root.startswith("mid_") for root in val_roots), (
        "no mid-sized component reached val -- the raw-deficit bug would produce exactly this"
    )


def test_a_component_never_splits_across_train_and_val() -> None:
    """Adversarial construction: two synthetic components, assign_components must place each
    one ENTIRELY on one side -- there is no code path that could emit half a component to train
    and half to val, since assignment operates on whole Component objects, never their pair_ids
    individually. This test would fail if a future refactor started iterating pair_ids instead."""

    class FakeComponent:
        def __init__(self, root: str, size: int) -> None:
            self.root = root
            self.pair_ids = [f"{root}_{i}" for i in range(size)]
            self.label_counts = {"M": size, "N": 0, "S": 0}

        @property
        def size(self) -> int:
            return len(self.pair_ids)

    components = [FakeComponent("big", 100), FakeComponent("small", 5)]
    train, val = stv.assign_components(components, seed=1, train_target_fraction=0.8)  # type: ignore[arg-type]
    train_pair_ids = {pid for c in train for pid in c.pair_ids}
    val_pair_ids = {pid for c in val for pid in c.pair_ids}
    for c in components:
        component_pair_ids = set(c.pair_ids)
        assert component_pair_ids <= train_pair_ids or component_pair_ids <= val_pair_ids, (
            f"component {c.root!r} was split across train and val"
        )


class _FakeComponent:
    """Minimal stand-in carrying only what main()/_side_summary() actually read (`pair_ids`,
    `label_counts`) -- not a full Component, deliberately, so this test cannot pass by
    accident just because it happens to construct a real Component correctly."""

    def __init__(self, pair_ids: list[str]) -> None:
        self.pair_ids = pair_ids
        self.label_counts = {"M": 0, "N": len(pair_ids), "S": 0}


def test_main_refuses_to_write_if_a_content_hash_overlap_is_ever_produced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The real safety net: even if assign_components ever had a bug that put the SAME listing
    content_hash on both sides, main() must refuse to write the output file rather than trust the
    algorithm. Verified with a SUBTLER mutation than duplicating one whole component (a reviewer
    finding: 100% overlap is the loudest possible signal, not a realistic bug shape): takes the
    REAL, correct assignment, then re-splits ONE real component's pair_ids in half between train
    and val, leaving every other component exactly as the real algorithm placed it -- so this is a
    COMPLETE, non-duplicated partition of all 672 pair_ids (the exact-partition check above cannot
    catch it) that violates only the deeper connectivity constraint. Because the two halves came
    from the same connected component, at least one listing content_hash is structurally
    guaranteed to be shared between them -- for a connected graph, any non-empty split of its
    edges into two groups must share a vertex, or the graph would not have been connected in the
    first place. This exercises the same detection path a genuine assign_components/
    build_components bug would hit, at a much smaller, more realistic signal size than duplicating
    an entire component.

    Also redirects stv.OUTPUT_JSON to a throwaway path (a reviewer finding: without this, a
    regression in the guard being tested would let main() actually WRITE a poisoned split over
    the real committed docs/learned/phase3-train-val-split.json before this test's own assertion
    ever runs)."""
    monkeypatch.setattr(stv, "OUTPUT_JSON", tmp_path / "poisoned-split.json")

    entries = stv._load_train_val_entries()
    components = stv.build_components(entries)
    real_train, real_val = stv.assign_components(
        components, stv.TRAIN_VAL_SPLIT_SEED, stv.TRAIN_TARGET_FRACTION
    )
    splittable = next(c for c in real_train if c.size >= 4)
    half = len(splittable.pair_ids) // 2
    poisoned_train = [c for c in real_train if c is not splittable] + [
        _FakeComponent(splittable.pair_ids[:half])
    ]
    poisoned_val = [*real_val, _FakeComponent(splittable.pair_ids[half:])]

    def fake_assign(components: list, seed: int, train_target_fraction: float):  # type: ignore[no-untyped-def]
        return poisoned_train, poisoned_val

    monkeypatch.setattr(stv, "assign_components", fake_assign)
    with pytest.raises(SystemExit, match="REFUSING TO WRITE"):
        stv.main()
    assert not (tmp_path / "poisoned-split.json").exists()


def test_main_refuses_to_write_if_assign_components_drops_a_component(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The exact-partition guard (a reviewer finding): before this check existed, a bug shape as
    simple as assign_components silently DROPPING a component produced a completely
    normal-looking run -- 671 (not 672) pairs, plausible-looking percentages, and the
    content_hash-overlap check still printing "PROVEN", because that check only ever looks for a
    hash present on BOTH sides, never for a pair_id present on NEITHER."""
    monkeypatch.setattr(stv, "OUTPUT_JSON", tmp_path / "poisoned-split.json")

    entries = stv._load_train_val_entries()
    components = stv.build_components(entries)
    real_train, real_val = stv.assign_components(
        components, stv.TRAIN_VAL_SPLIT_SEED, stv.TRAIN_TARGET_FRACTION
    )
    dropped_train = real_train[1:]  # silently drop the first train component

    def fake_assign(components: list, seed: int, train_target_fraction: float):  # type: ignore[no-untyped-def]
        return dropped_train, real_val

    monkeypatch.setattr(stv, "assign_components", fake_assign)
    with pytest.raises(SystemExit, match="not an exact partition"):
        stv.main()
    assert not (tmp_path / "poisoned-split.json").exists()


def test_refuses_when_eval_view_reports_unfrozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_view = tmp_path / "eval-view.json"
    fake_view.write_text(
        json.dumps(
            {
                "frozen": False,
                "frozen_labels_sha256": stv._frozen_marker(),
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(stv, "EVAL_VIEW_JSON", fake_view)
    with pytest.raises(SystemExit, match="not frozen"):
        stv._load_train_val_entries()


def test_refuses_when_eval_view_hash_does_not_match_live_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_view = tmp_path / "eval-view.json"
    fake_view.write_text(
        json.dumps(
            {
                "frozen": True,
                "frozen_labels_sha256": "deadbeef" * 8,
                "entries": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(stv, "EVAL_VIEW_JSON", fake_view)
    with pytest.raises(SystemExit, match="REFUSING TO RUN"):
        stv._load_train_val_entries()


def test_refuses_when_the_frozen_queue_hash_does_not_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Previously zero coverage (a reviewer finding): _content_hashes_by_occurrence_id() refuses
    if the frozen annotation queue's live hash doesn't match FROZEN_QUEUE_SHA256, but nothing
    exercised that branch. A tampered/corrupted queue file is exactly the case this check exists
    to catch, so it must fail loudly, not silently derive content_hashes from the wrong data."""
    fake_queue = tmp_path / "queue.json"
    fake_queue.write_text(json.dumps({"pairs": [{"pair_id": "x"}]}), encoding="utf-8")
    monkeypatch.setattr(clc, "QUEUE_JSON", fake_queue)
    with pytest.raises(SystemExit, match="frozen queue hash"):
        stv._content_hashes_by_occurrence_id()
