r"""Phase 3 canonical evaluation view (DECISIONS.md ADR-0028 addendum #16).

Materialises the ADR-0028 addendum #12 evaluation rules -- until this script existed they lived
only in prose (`docs/learned/phase3-test-eval-denominators.md`,
`phase3-annotation-split.json`'s own `evaluation_rules` block) -- into
`docs/learned/phase3-eval-view.json`, so scoring the Phase 3 item 5 baseline never has to
re-derive them by hand:

  1. one entry per DISTINCT `pair_id` per split, never per decision row;
  2. for a repeated pair the label is the FIRST decision in DISPLAY order
     (`docs/learned/phase3-repeat-first-occurrence.json`), never file order;
  3. a repeated pair is attributed to tier "proxy_key_collision" (the split file's own
     `evaluation_rules.repeat_reporting_note`) -- NOT to the tier of its first occurrence;
  4. `S` labels stay in the file with label "S" and `scored: false` -- never dropped silently,
     never counted in a metric;
  5. each entry carries `pair_id`, `split`, `tier`, `label`, `scored`, `first_occurrence_id`,
     `is_repeat`.

    uv run python scripts/build_eval_view.py
    uv run python scripts/build_eval_view.py --assert-pre-review

`--assert-pre-review` exits non-zero unless the view reproduces the architect's independently
computed per-tier table (DECISIONS.md ADR-0028 addendum #16) exactly. On a mismatch it prints the
pair_ids currently attributed to the offending split+tier bucket rather than silently continuing
-- two independent derivations disagreeing is a finding, never adjust the expected numbers to make
it pass.

Reads `docs/learned/phase3-labels.json` and `phase3-repeat-first-occurrence.json` only for the
per-pair data (never `phase3-annotation-queue.json`'s own tier field for a repeat -- rule 3 above
overrides it). Does NOT read `phase3-annotation-split.json`'s `per_tier_counts` block: its
`test_pair_ids`/`train_val_pair_ids` fields hold ROW counts, not distinct-pair counts (ADR-0028
addendum #16) -- a known trap in that frozen file, documented rather than "fixed" (the file is
frozen and hashed in three other places). This eval view is the only source of per-tier pair-count
denominators from here on.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_label_rule_consistency as clc  # noqa: E402

LABELS_JSON = ROOT / "docs" / "learned" / "phase3-labels.json"
REPEAT_FIRST_OCCURRENCE_JSON = ROOT / "docs" / "learned" / "phase3-repeat-first-occurrence.json"
SPLIT_JSON = ROOT / "docs" / "learned" / "phase3-annotation-split.json"
OUTPUT_JSON = ROOT / "docs" / "learned" / "phase3-eval-view.json"
TEST_LABELS_FROZEN_FILE = ROOT / "tests" / "test_labels_frozen.py"

REPEAT_REPORTING_TIER = "proxy_key_collision"

TIER_ORDER = [
    "proxy_key_collision",
    "capacity_differs_cross_shop",
    "blocked_retrieval_candidate",
    "same_capacity_diff_flavour",
    "capacity_differs_within_shop",
    "same_capacity_diff_lifestage",
    "diff_brand_similar_title",
    "same_capacity_diff_breedsize",
    "trivial_spot_check",
]

# The architect's independently computed pre-review table (DECISIONS.md ADR-0028 addendum #16),
# reproduced here verbatim as the parity target for --assert-pre-review. (tier -> (pairs, M, N, S))
EXPECTED_PRE_REVIEW: dict[str, dict[str, tuple[int, int, int, int]]] = {
    "test": {
        "proxy_key_collision": (86, 74, 12, 0),
        "capacity_differs_cross_shop": (63, 1, 62, 0),
        "blocked_retrieval_candidate": (37, 15, 21, 1),
        "same_capacity_diff_flavour": (26, 0, 26, 0),
        "capacity_differs_within_shop": (23, 0, 22, 1),
        "same_capacity_diff_lifestage": (20, 1, 18, 1),
        "diff_brand_similar_title": (16, 0, 16, 0),
        "same_capacity_diff_breedsize": (14, 4, 10, 0),
        "trivial_spot_check": (2, 2, 0, 0),
    },
    "train_val": {
        "proxy_key_collision": (200, 166, 31, 3),
        "capacity_differs_cross_shop": (146, 2, 144, 0),
        "blocked_retrieval_candidate": (86, 39, 43, 4),
        "same_capacity_diff_flavour": (59, 0, 59, 0),
        "capacity_differs_within_shop": (53, 0, 53, 0),
        "same_capacity_diff_lifestage": (46, 1, 45, 0),
        "diff_brand_similar_title": (39, 4, 35, 0),
        "same_capacity_diff_breedsize": (33, 5, 28, 0),
        "trivial_spot_check": (10, 9, 1, 0),
    },
}
EXPECTED_TOTALS = {
    "test": (287, 97, 187, 3, 284),
    "train_val": (672, 226, 439, 7, 665),
}


def _frozen_state() -> bool:
    text = TEST_LABELS_FROZEN_FILE.read_text(encoding="utf-8")
    m = re.search(r'FROZEN_LABELS_SHA256\s*=\s*"([^"]*)"', text)
    if m is None:
        raise SystemExit(f"FROZEN_LABELS_SHA256 not found in {TEST_LABELS_FROZEN_FILE}")
    return m.group(1) != "UNFROZEN"


def build_entries() -> list[dict[str, Any]]:
    queue_sha256_lf = clc.sha256_lf(clc.QUEUE_JSON.read_bytes())
    if queue_sha256_lf != clc.FROZEN_QUEUE_SHA256:
        raise SystemExit(
            f"REFUSING TO RUN: frozen queue hash (LF) {queue_sha256_lf} does not match "
            f"{clc.FROZEN_QUEUE_SHA256}."
        )

    labels_data = json.loads(LABELS_JSON.read_text(encoding="utf-8"))
    decisions: dict[str, dict[str, Any]] = labels_data["decisions"]
    repeat_lookup = json.loads(REPEAT_FIRST_OCCURRENCE_JSON.read_text(encoding="utf-8"))["lookup"]

    queue = json.loads(clc.QUEUE_JSON.read_text(encoding="utf-8"))["pairs"]
    known_occurrence_ids = set(clc.derive_occurrence_ids(queue))
    unknown = [occ_id for occ_id in decisions if occ_id not in known_occurrence_ids]
    if unknown:
        raise SystemExit(
            f"REFUSING TO RUN: {len(unknown)} decision(s) reference an occurrence_id the frozen "
            f"queue does not have (data drift): {unknown[:5]}"
        )

    by_pair: dict[str, list[str]] = {}
    for occ_id, dec in decisions.items():
        by_pair.setdefault(dec["pair_id"], []).append(occ_id)

    entries: list[dict[str, Any]] = []
    for pair_id, occ_ids in by_pair.items():
        is_repeat = pair_id in repeat_lookup
        if is_repeat:
            first_occ = repeat_lookup[pair_id]["first_occurrence_id"]
            if first_occ not in occ_ids:
                raise SystemExit(
                    f"{pair_id}: repeat lookup's first_occurrence_id {first_occ!r} has no "
                    f"decision in phase3-labels.json (pre-review data drift)"
                )
            splits = {decisions[o]["split"] for o in occ_ids}
            if len(splits) != 1:
                raise SystemExit(
                    f"{pair_id}: repeated pair's occurrences disagree on split: {splits}"
                )
            dec = decisions[first_occ]
            tier = REPEAT_REPORTING_TIER
        else:
            if len(occ_ids) != 1:
                raise SystemExit(
                    f"{pair_id}: {len(occ_ids)} decisions but not in the 38-pair repeat lookup"
                )
            first_occ = occ_ids[0]
            dec = decisions[first_occ]
            tier = dec["tier"]
        label = dec["label"]
        entries.append(
            {
                "pair_id": pair_id,
                "split": dec["split"],
                "tier": tier,
                "label": label,
                "scored": label != "S",
                "first_occurrence_id": first_occ,
                "is_repeat": is_repeat,
            }
        )
    entries.sort(key=lambda e: (e["split"], e["pair_id"]))
    return entries


def per_tier_table(
    entries: list[dict[str, Any]], split: str
) -> dict[str, tuple[int, int, int, int]]:
    counts: dict[str, list[int]] = {t: [0, 0, 0, 0] for t in TIER_ORDER}
    for e in entries:
        if e["split"] != split:
            continue
        bucket = counts[e["tier"]]
        bucket[0] += 1
        bucket[1 if e["label"] == "M" else 2 if e["label"] == "N" else 3] += 1
    return {t: tuple(v) for t, v in counts.items()}  # type: ignore[misc]


def print_table(entries: list[dict[str, Any]], split: str, label: str) -> None:
    table = per_tier_table(entries, split)
    split_entries = [e for e in entries if e["split"] == split]
    total_pairs = len(split_entries)
    total_m = sum(1 for e in split_entries if e["label"] == "M")
    total_n = sum(1 for e in split_entries if e["label"] == "N")
    total_s = sum(1 for e in split_entries if e["label"] == "S")
    scored = total_m + total_n
    print(f"{label}, {total_pairs} pairs, {total_m} M / {total_n} N / {total_s} S, {scored} scored")
    for tier in TIER_ORDER:
        pairs, m, n, s = table[tier]
        print(f"  {tier:<30} {pairs:>4}  {m:>4} M  {n:>4} N  {s:>4} S")


def check_pre_review_parity(entries: list[dict[str, Any]]) -> bool:
    ok = True
    for split in ("test", "train_val"):
        table = per_tier_table(entries, split)
        for tier, expected in EXPECTED_PRE_REVIEW[split].items():
            actual = table[tier]
            if actual != expected:
                ok = False
                offending = [
                    e["pair_id"] for e in entries if e["split"] == split and e["tier"] == tier
                ]
                print(
                    f"MISMATCH {split}/{tier}: expected (pairs,M,N,S)={expected}, "
                    f"got {actual}. pair_ids currently in this bucket: {offending}",
                    file=sys.stderr,
                )
        split_entries = [e for e in entries if e["split"] == split]
        actual_totals = (
            len(split_entries),
            sum(1 for e in split_entries if e["label"] == "M"),
            sum(1 for e in split_entries if e["label"] == "N"),
            sum(1 for e in split_entries if e["label"] == "S"),
            sum(1 for e in split_entries if e["scored"]),
        )
        if actual_totals != EXPECTED_TOTALS[split]:
            ok = False
            print(
                f"MISMATCH {split} TOTAL: expected {EXPECTED_TOTALS[split]}, got {actual_totals}",
                file=sys.stderr,
            )
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument(
        "--assert-pre-review",
        action="store_true",
        help="exit non-zero unless the view matches the architect's pre-review table exactly",
    )
    args = ap.parse_args()

    entries = build_entries()

    print_table(entries, "test", "TEST")
    print()
    print_table(entries, "train_val", "TRAIN_VAL")

    if args.assert_pre_review:
        if not check_pre_review_parity(entries):
            print("\n--assert-pre-review: MISMATCH against the architect's table.", file=sys.stderr)
            return 1
        print("\n--assert-pre-review: matches the architect's table exactly.")

    view = {
        "built_from": "scripts/build_eval_view.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "labels_sha256_lf": clc.sha256_lf(LABELS_JSON.read_bytes()),
        "queue_sha256_lf": clc.sha256_lf(clc.QUEUE_JSON.read_bytes()),
        "split_sha256_lf": clc.sha256_lf(SPLIT_JSON.read_bytes()),
        "frozen": _frozen_state(),
        "entries": entries,
    }
    OUTPUT_JSON.write_text(json.dumps(view, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nwritten: {OUTPUT_JSON.relative_to(ROOT)} ({len(entries)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
