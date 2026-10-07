"""Phase 3 STEP 7 (ADR-0028 addendum #11) — structural checks on the COMMITTED annotation split
artifacts (`phase3-annotation-queue.json`, FROZEN, plus the derived
`phase3-annotation-split.json`/`phase3-test-split-reference-predictions.json`), read directly from
disk. No database, no re-running the optimizer — these tests exist to catch the file drifting out
of sync with itself or with the frozen queue, not to re-derive the split.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUEUE_JSON = ROOT / "docs" / "learned" / "phase3-annotation-queue.json"
SPLIT_JSON = ROOT / "docs" / "learned" / "phase3-annotation-split.json"
TEST_REFERENCE_JSON = ROOT / "docs" / "learned" / "phase3-test-split-reference-predictions.json"
REPEAT_FIRST_OCCURRENCE_JSON = ROOT / "docs" / "learned" / "phase3-repeat-first-occurrence.json"

# Recorded the moment the queue was frozen (ADR-0028 addendum #9). If this ever fails, the
# "frozen" file has been edited -- CLAUDE.md §7's own discipline (never re-score a frozen gate
# figure against edited data) applies here just as much as it did to the Phase 2 gate sample.
# LF-normalised hash (same convention as scripts/check_label_rule_consistency.py and
# tests/test_labels_frozen.py): .gitattributes stores the file as LF, so a raw-byte hash taken on a
# Windows CRLF checkout (the original 696e9833...) can never match on Linux CI. Same content.
FROZEN_QUEUE_SHA256 = "7da125e1856bc65514234d516e17d0a12363ee6ada9b324b3f00ca8bfa146d2a"
# What the derived split/lookup files recorded when they were generated on the CRLF checkout.
FROZEN_QUEUE_SHA256_RAW_CRLF = "696e983392628b868c4becd92db400735a52498a4994b5b7c8651b160a087011"

TIER_GAP_LIMIT_PP = 4.5
TEST_MIN_PER_TIER = 14


def _derive_occurrence_ids(pairs: list[dict]) -> list[str]:
    """Same rule as `scripts/split_annotation_queue.py::derive_occurrence_ids()` and
    `tools/annotate.html::deriveOccurrenceIds()` -- duplicated here deliberately (not imported)
    so this test does not depend on either implementation to prove they agree; it recomputes the
    rule from CLAUDE.md/ADR-0028's own description of it (pair_id + 0-based ordinal, in file
    order) independently."""
    counts: dict[str, int] = {}
    ids = []
    for p in pairs:
        pid = p["pair_id"]
        k = counts.get(pid, 0)
        ids.append(f"{pid}_{k}")
        counts[pid] = k + 1
    return ids


def _load_queue() -> dict:
    return json.loads(QUEUE_JSON.read_text(encoding="utf-8"))


def _load_split() -> dict:
    return json.loads(SPLIT_JSON.read_text(encoding="utf-8"))


def _load_repeat_first_occurrence() -> dict:
    return json.loads(REPEAT_FIRST_OCCURRENCE_JSON.read_text(encoding="utf-8"))


def test_frozen_queue_hash_unchanged() -> None:
    actual = hashlib.sha256(QUEUE_JSON.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert actual == FROZEN_QUEUE_SHA256, (
        "the FROZEN annotation queue file has changed since it was frozen (ADR-0028 addendum "
        "#9) -- any change needs a stated reason in STATE.md first, and this constant must be "
        "updated deliberately, not silently"
    )


def test_queue_row_count_is_997() -> None:
    queue = _load_queue()
    assert len(queue["pairs"]) == 997


def test_split_has_exactly_997_assignment_keys() -> None:
    split = _load_split()
    assert len(split["assignments"]) == 997


def test_every_derived_occurrence_id_has_an_assignment() -> None:
    queue = _load_queue()
    split = _load_split()
    derived_ids = _derive_occurrence_ids(queue["pairs"])
    assert len(derived_ids) == len(set(derived_ids)), "derived occurrence_ids are not all unique"
    missing = [occ_id for occ_id in derived_ids if occ_id not in split["assignments"]]
    assert not missing, f"{len(missing)} derived occurrence_id(s) missing from split assignments"


def test_derived_ids_resolve_the_38_known_collisions() -> None:
    """Facts this test pins down, verified against the frozen file's own pair_id field (not
    against occurrence_id, which is exactly the field that collides): 997 rows, 959 distinct
    pair_ids, 38 pair_ids appearing exactly twice."""
    queue = _load_queue()
    pair_ids = [p["pair_id"] for p in queue["pairs"]]
    distinct = set(pair_ids)
    assert len(pair_ids) == 997
    assert len(distinct) == 959
    counts: dict[str, int] = {}
    for pid in pair_ids:
        counts[pid] = counts.get(pid, 0) + 1
    repeated = [pid for pid, n in counts.items() if n > 1]
    assert len(repeated) == 38
    assert all(counts[pid] == 2 for pid in repeated)


def test_no_test_entry_carries_an_engine_prediction() -> None:
    split = _load_split()
    leaks = [
        occ_id
        for occ_id, entry in split["assignments"].items()
        if entry["split"] == "test" and "engine_prediction" in entry
    ]
    assert not leaks, f"{len(leaks)} TEST entries carry an engine_prediction key: {leaks[:5]}"


def test_every_train_val_entry_carries_an_engine_prediction() -> None:
    split = _load_split()
    missing = [
        occ_id
        for occ_id, entry in split["assignments"].items()
        if entry["split"] == "train_val" and "engine_prediction" not in entry
    ]
    assert not missing


def test_test_reference_file_never_overlaps_train_val_occurrence_ids() -> None:
    """The held-out reference-prediction file (never fetched by tools/annotate.html) must only
    ever name TEST occurrence_ids -- if a TRAIN_VAL id leaked in, that would be harmless on its
    own, but it would signal the two files were built from different splits."""
    split = _load_split()
    reference = json.loads(TEST_REFERENCE_JSON.read_text(encoding="utf-8"))
    test_ids = {
        occ_id for occ_id, entry in split["assignments"].items() if entry["split"] == "test"
    }
    reference_ids = set(reference["predictions"].keys())
    assert reference_ids == test_ids


def test_test_row_count_and_target() -> None:
    split = _load_split()
    assert split["test_row_count"] == 300


def test_zero_listing_overlap_between_splits() -> None:
    queue = _load_queue()
    split = _load_split()
    test_ids = {
        occ_id for occ_id, entry in split["assignments"].items() if entry["split"] == "test"
    }
    train_val_ids = {
        occ_id for occ_id, entry in split["assignments"].items() if entry["split"] == "train_val"
    }
    derived_ids = _derive_occurrence_ids(queue["pairs"])
    id_to_row = dict(zip(derived_ids, queue["pairs"], strict=True))

    test_hashes = {
        h
        for occ_id in test_ids
        for h in (
            id_to_row[occ_id]["left"]["content_hash"],
            id_to_row[occ_id]["right"]["content_hash"],
        )
    }
    train_val_hashes = {
        h
        for occ_id in train_val_ids
        for h in (
            id_to_row[occ_id]["left"]["content_hash"],
            id_to_row[occ_id]["right"]["content_hash"],
        )
    }
    assert not (test_hashes & train_val_hashes)


def test_acceptance_gate_recorded_as_passed() -> None:
    split = _load_split()
    assert split["acceptance_gate_passed"] is True
    assert split["acceptance_gate_failures"] == []


def test_per_tier_gap_within_threshold() -> None:
    """Recomputed independently from `assignments`, not read from the split file's own
    `per_tier_counts` summary -- this is the test that would catch the summary itself being
    stale or wrong, not just echo it back."""
    split = _load_split()
    test_tier_counts: dict[str, int] = {}
    train_val_tier_counts: dict[str, int] = {}
    for entry in split["assignments"].values():
        bucket = test_tier_counts if entry["split"] == "test" else train_val_tier_counts
        bucket[entry["tier"]] = bucket.get(entry["tier"], 0) + 1

    test_total = sum(test_tier_counts.values())
    train_val_total = sum(train_val_tier_counts.values())
    all_tiers = set(test_tier_counts) | set(train_val_tier_counts)
    assert all_tiers, "no tiers found in the split assignments"

    for tier in all_tiers:
        t_n = test_tier_counts.get(tier, 0)
        tv_n = train_val_tier_counts.get(tier, 0)
        t_pct = t_n / test_total * 100 if test_total else 0.0
        tv_pct = tv_n / train_val_total * 100 if train_val_total else 0.0
        gap = abs(t_pct - tv_pct)
        assert gap <= TIER_GAP_LIMIT_PP, (
            f"tier {tier!r}: gap {gap:.1f}pp exceeds {TIER_GAP_LIMIT_PP}pp"
        )
        assert t_n >= TEST_MIN_PER_TIER, (
            f"tier {tier!r}: TEST count {t_n} below {TEST_MIN_PER_TIER}"
        )


# --- ADR-0028 addendum #12 (TASK 2) -- evaluation rules, checked structurally --------------------


def test_headline_test_set_is_287_distinct_pair_ids() -> None:
    """Recomputed from `assignments` directly, not read from the split file's own
    `test_distinct_pair_ids` summary field -- this is the test that would catch that summary
    itself going stale."""
    split = _load_split()
    test_pair_ids = {
        entry["pair_id"] for entry in split["assignments"].values() if entry["split"] == "test"
    }
    assert len(test_pair_ids) == 287


def test_every_repeated_pair_has_both_occurrences_in_the_same_split() -> None:
    """Every one of the 38 pair_ids that appear twice in the frozen queue (once as
    proxy_key_collision, once as trivial_spot_check) must land entirely in TEST or entirely in
    TRAIN_VAL -- never split across the boundary. Guaranteed by construction (a connected
    component is assigned whole to one split), verified here directly against `assignments`."""
    split = _load_split()
    pair_id_to_splits: dict[str, set[str]] = {}
    for entry in split["assignments"].values():
        pair_id_to_splits.setdefault(entry["pair_id"], set()).add(entry["split"])

    # A pair_id repeated in the frozen queue produces TWO assignment entries under the SAME
    # pair_id key (different occurrence_ids) -- count occurrences, not just distinct splits.
    queue = _load_queue()
    pair_id_occurrence_count: dict[str, int] = {}
    for p in queue["pairs"]:
        pair_id_occurrence_count[p["pair_id"]] = pair_id_occurrence_count.get(p["pair_id"], 0) + 1
    repeated_pair_ids = {pid for pid, n in pair_id_occurrence_count.items() if n > 1}
    assert len(repeated_pair_ids) == 38

    cross_split = [pid for pid in repeated_pair_ids if len(pair_id_to_splits.get(pid, set())) != 1]
    assert not cross_split, (
        f"{len(cross_split)} repeated pair(s) split across TEST/TRAIN_VAL: {cross_split}"
    )


def test_repeat_first_occurrence_lookup_covers_exactly_38_pairs() -> None:
    lookup = _load_repeat_first_occurrence()["lookup"]
    assert len(lookup) == 38


def test_repeat_first_occurrence_entries_reference_real_queue_occurrences() -> None:
    queue = _load_queue()
    derived_ids = set(_derive_occurrence_ids(queue["pairs"]))
    lookup = _load_repeat_first_occurrence()["lookup"]
    for pair_id, entry in lookup.items():
        assert entry["first_occurrence_id"] in derived_ids, (
            f"{pair_id}: first_occurrence_id {entry['first_occurrence_id']!r} not in the frozen "
            "queue's derived occurrence_ids"
        )
        assert entry["second_occurrence_id"] in derived_ids, (
            f"{pair_id}: second_occurrence_id {entry['second_occurrence_id']!r} not in the frozen "
            "queue's derived occurrence_ids"
        )
        assert entry["first_occurrence_id"] != entry["second_occurrence_id"]


def test_repeat_first_occurrence_hashes_match_current_files() -> None:
    """The lookup file records the queue/split SHA-256 it was built against -- if either file
    changes without regenerating the lookup, this catches the drift."""
    lookup_file = _load_repeat_first_occurrence()
    # The lookup file was generated (and is itself frozen) with the raw CRLF-checkout hash.
    assert lookup_file["queue_sha256"] == FROZEN_QUEUE_SHA256_RAW_CRLF
    actual_split_sha256 = hashlib.sha256(SPLIT_JSON.read_bytes()).hexdigest()
    assert lookup_file["split_sha256"] == actual_split_sha256, (
        "phase3-repeat-first-occurrence.json was built against a different "
        "phase3-annotation-split.json than the one currently committed -- re-run "
        "scripts/compute_repeat_first_occurrence.js"
    )


# --- ADR-0028 addendum #12 defect fix -- every repeat's gap must be >= 100 -----------------------
# (found by the architect re-running buildOrder()/enforceRepeatSpacing() in Node against the
# committed files: enforceRepeatSpacing()'s clamp let 4 of 38 repeats land short -- TEST gaps
# 99/77/48, TRAIN_VAL gap 66 -- while STATE.md and ADR-0028 addendum #11 claimed "min 100".
# ensureRepeatFirstOccurrencesFit() (tools/annotate.html) now guarantees this before spacing runs;
# these tests lock the guarantee against the regenerated lookup file, not just the algorithm.)


def test_repeat_first_occurrence_gaps_all_at_least_100() -> None:
    lookup = _load_repeat_first_occurrence()["lookup"]
    assert len(lookup) == 38
    for pair_id, entry in lookup.items():
        recomputed_gap = entry["second_position"] - entry["first_position"]
        assert entry["gap"] == recomputed_gap, (
            f"{pair_id}: recorded gap {entry['gap']} != second_position - first_position "
            f"({recomputed_gap})"
        )
        assert entry["gap"] >= 100, f"{pair_id}: gap {entry['gap']} < 100"


def test_repeat_first_occurrence_first_position_before_second() -> None:
    lookup = _load_repeat_first_occurrence()["lookup"]
    for pair_id, entry in lookup.items():
        assert entry["first_position"] < entry["second_position"], (
            f"{pair_id}: first_position {entry['first_position']} is not before "
            f"second_position {entry['second_position']}"
        )


def test_repeat_first_occurrence_both_occurrences_share_a_split() -> None:
    split = _load_split()
    lookup = _load_repeat_first_occurrence()["lookup"]
    for pair_id, entry in lookup.items():
        first_split = split["assignments"][entry["first_occurrence_id"]]["split"]
        second_split = split["assignments"][entry["second_occurrence_id"]]["split"]
        assert first_split == second_split, (
            f"{pair_id}: first occurrence in split {first_split!r}, second in {second_split!r}"
        )
        assert entry["split"] == first_split


def test_repeat_first_occurrence_gap_stats_header_matches_recomputed() -> None:
    """The header's per-split min/median/max is a summary of the same `lookup` entries -- this is
    the test that would catch the header going stale relative to the entries it summarizes."""
    data = _load_repeat_first_occurrence()
    lookup = data["lookup"]
    by_split: dict[str, list[int]] = {"test": [], "train_val": []}
    for entry in lookup.values():
        by_split[entry["split"]].append(entry["gap"])

    for split_name, gaps in by_split.items():
        gaps_sorted = sorted(gaps)
        n = len(gaps_sorted)
        assert n > 0, f"no repeats recorded for split {split_name!r}"
        median = (
            gaps_sorted[n // 2] if n % 2 else (gaps_sorted[n // 2 - 1] + gaps_sorted[n // 2]) / 2
        )
        stats = data["gap_stats"][split_name]
        assert stats["count"] == n
        assert stats["min"] == gaps_sorted[0]
        assert stats["median"] == median
        assert stats["max"] == gaps_sorted[-1]


def test_split_file_carries_evaluation_rules_block() -> None:
    split = _load_split()
    rules = split["evaluation_rules"]
    assert rules["headline_test_distinct_pair_ids"] == 287
    assert rules["repeat_reporting_tier"] == "proxy_key_collision"
    assert rules["trivial_spot_check_test_standalone_pair_ids"] == 2
    assert rules["predicted_label_forecast_by_split"]["test"] == {
        # conventions revision 4 / ADR-0028 addendum #13 -- rule 3b (food form) flips one pair's
        # forecast from M to N (previously M:103/N:164).
        "M": 102,
        "N": 165,
        "S": 33,
        "of_rows": 300,
    }
    assert rules["predicted_label_forecast_by_split"]["train_val"] == {
        "M": 203,
        "N": 390,
        "S": 104,
        "of_rows": 697,
    }
