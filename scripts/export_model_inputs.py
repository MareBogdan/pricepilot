r"""Phase 3 item 5 harness: export model inputs for a hosted notebook (CLAUDE.md §7 item 5;
ADR-0028 addendum #19).

    uv run python scripts/export_model_inputs.py

Writes two files under `docs/learned/model-inputs/`:

  phase3-inputs-test.json      287 pairs: pair_id, text_a, text_b. NO label. NO tier. NOTHING
                                from which a label could be recovered -- this file is meant to
                                leave this machine and be uploaded to a hosted notebook, and it
                                must be IMPOSSIBLE for a TEST label to travel with it, not merely
                                unintended.
  phase3-inputs-train-val.json 672 pairs: pair_id, text_a, text_b, label, scored, train_or_val.
                                This file never leaves scoring's trust boundary in the same way --
                                TRAIN_VAL labels are meant to train/tune the model, so they belong
                                here. `scored` carries build_eval_view.py's own rule 4 forward: it
                                is false for the 6 `S`-labelled pairs (never dropped silently,
                                never usable as a training example), so nothing downstream has to
                                rediscover S rows by string-matching `label == "S"`.

Both `text_a`/`text_b` come from exactly one place, `pricepilot.matching.pair_text.build_pair_text`
-- see that module for the leakage rules it itself enforces (title + ten fixed normalised
attributes only, never label/tier/split/pair_id/source). Both files record `frozen_labels_sha256`
and `pair_text_version` so a later comparison can prove which frozen dataset and which text format
produced them.

**Leakage guard, enforced here in code, not only documented:** before writing the TEST file,
`_assert_test_payload_has_no_leakage` walks the ENTIRE written structure recursively and refuses
(non-zero exit) if any dict key matches a label-shaped name (`label`, `tier`, `split`, `y`,
`target`, case-insensitively) or any leaf value is exactly the string `"M"`, `"N"` or `"S"`.
"""

from __future__ import annotations

import json
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
from pricepilot.matching.pair_text import PAIR_TEXT_VERSION, build_pair_text  # noqa: E402

OUTPUT_DIR = ROOT / "docs" / "learned" / "model-inputs"
TEST_OUTPUT = OUTPUT_DIR / "phase3-inputs-test.json"
TRAIN_VAL_OUTPUT = OUTPUT_DIR / "phase3-inputs-train-val.json"
TRAIN_VAL_SPLIT_JSON = ROOT / "docs" / "learned" / "phase3-train-val-split.json"

_FORBIDDEN_KEY_NAMES = {"label", "tier", "split", "y", "target"}
_FORBIDDEN_VALUES = {"M", "N", "S"}


def _assert_test_payload_has_no_leakage(payload: Any, path: str = "$") -> None:
    """Walks the whole JSON-shaped structure recursively. Raises SystemExit, not a soft warning,
    because this is the one guard standing between the TEST labels and a file meant to leave this
    machine."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in _FORBIDDEN_KEY_NAMES:
                raise SystemExit(
                    f"REFUSING TO WRITE TEST FILE: forbidden key {key!r} found at {path}.{key} "
                    "-- a TEST export must never carry a label-shaped field."
                )
            _assert_test_payload_has_no_leakage(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            _assert_test_payload_has_no_leakage(item, f"{path}[{i}]")
    elif isinstance(payload, str) and payload in _FORBIDDEN_VALUES:
        raise SystemExit(
            f"REFUSING TO WRITE TEST FILE: value {payload!r} at {path} is exactly a label "
            "letter (M/N/S) -- refusing even though it may be an innocent coincidence, "
            "because this check cannot tell the difference and must not guess."
        )


def _listings_by_occurrence_id() -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    queue = json.loads(clc.QUEUE_JSON.read_text(encoding="utf-8"))["pairs"]
    queue_sha256_lf = clc.sha256_lf(clc.QUEUE_JSON.read_bytes())
    if queue_sha256_lf != clc.FROZEN_QUEUE_SHA256:
        raise SystemExit(
            f"REFUSING TO RUN: frozen queue hash (LF) {queue_sha256_lf} does not match "
            f"{clc.FROZEN_QUEUE_SHA256}."
        )
    occ_ids = clc.derive_occurrence_ids(queue)
    return {
        occ_id: (pair["left"], pair["right"]) for occ_id, pair in zip(occ_ids, queue, strict=True)
    }


def _load_eval_view() -> dict[str, Any]:
    view = json.loads(EVAL_VIEW_JSON.read_text(encoding="utf-8"))
    live_marker = _frozen_marker()
    if view.get("frozen_labels_sha256") != live_marker:
        raise SystemExit(
            "REFUSING TO RUN: docs/learned/phase3-eval-view.json's frozen_labels_sha256 "
            f"({view.get('frozen_labels_sha256')!r}) does not match the live "
            f"FROZEN_LABELS_SHA256 ({live_marker!r}). Re-run scripts/build_eval_view.py first."
        )
    if not view.get("frozen"):
        raise SystemExit("REFUSING TO RUN: the label dataset is not frozen yet.")
    return view  # type: ignore[no-any-return]


def build_test_payload(view: dict[str, Any]) -> dict[str, Any]:
    listings = _listings_by_occurrence_id()
    entries = sorted(
        (e for e in view["entries"] if e["split"] == "test"), key=lambda e: e["pair_id"]
    )
    if len(entries) != 287:
        raise SystemExit(f"REFUSING TO RUN: expected 287 TEST pairs, found {len(entries)}.")
    pairs = []
    for e in entries:
        left, right = listings[e["first_occurrence_id"]]
        text_a, text_b = build_pair_text(left, right)
        pairs.append({"pair_id": e["pair_id"], "text_a": text_a, "text_b": text_b})
    return {
        "built_from": "scripts/export_model_inputs.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "frozen_labels_sha256": view["frozen_labels_sha256"],
        "pair_text_version": PAIR_TEXT_VERSION,
        "pairs": pairs,
    }


def build_train_val_payload(view: dict[str, Any]) -> dict[str, Any]:
    listings = _listings_by_occurrence_id()
    split = json.loads(TRAIN_VAL_SPLIT_JSON.read_text(encoding="utf-8"))
    if split.get("frozen_labels_sha256") != view["frozen_labels_sha256"]:
        raise SystemExit(
            "REFUSING TO RUN: docs/learned/phase3-train-val-split.json's frozen_labels_sha256 "
            "does not match the eval view's -- re-run scripts/split_train_val.py first."
        )
    if split.get("pair_text_version") != PAIR_TEXT_VERSION:
        raise SystemExit(
            "REFUSING TO RUN: docs/learned/phase3-train-val-split.json's pair_text_version "
            f"({split.get('pair_text_version')!r}) does not match the live PAIR_TEXT_VERSION "
            f"({PAIR_TEXT_VERSION!r}) -- re-run scripts/split_train_val.py first."
        )
    train_ids = set(split["train"]["pair_ids"])
    val_ids = set(split["val"]["pair_ids"])

    entries = sorted(
        (e for e in view["entries"] if e["split"] == "train_val"), key=lambda e: e["pair_id"]
    )
    if len(entries) != 672:
        raise SystemExit(f"REFUSING TO RUN: expected 672 TRAIN_VAL pairs, found {len(entries)}.")
    pairs = []
    for e in entries:
        pair_id = e["pair_id"]
        if pair_id in train_ids:
            train_or_val = "train"
        elif pair_id in val_ids:
            train_or_val = "val"
        else:
            raise SystemExit(
                f"REFUSING TO RUN: {pair_id!r} is a TRAIN_VAL pair not assigned to either side "
                "by phase3-train-val-split.json (data drift between the two files)."
            )
        left, right = listings[e["first_occurrence_id"]]
        text_a, text_b = build_pair_text(left, right)
        pairs.append(
            {
                "pair_id": pair_id,
                "text_a": text_a,
                "text_b": text_b,
                "label": e["label"],
                "scored": e["scored"],
                "train_or_val": train_or_val,
            }
        )
    return {
        "built_from": "scripts/export_model_inputs.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "frozen_labels_sha256": view["frozen_labels_sha256"],
        "pair_text_version": PAIR_TEXT_VERSION,
        "train_val_split_seed": split["seed"],
        "pairs": pairs,
    }


def main() -> int:
    view = _load_eval_view()

    test_payload = build_test_payload(view)
    _assert_test_payload_has_no_leakage(test_payload)

    train_val_payload = build_train_val_payload(view)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEST_OUTPUT.write_text(json.dumps(test_payload, indent=1, ensure_ascii=False), encoding="utf-8")
    TRAIN_VAL_OUTPUT.write_text(
        json.dumps(train_val_payload, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"written: {TEST_OUTPUT.relative_to(ROOT)} ({len(test_payload['pairs'])} pairs)")
    print(
        f"written: {TRAIN_VAL_OUTPUT.relative_to(ROOT)} ({len(train_val_payload['pairs'])} pairs)"
    )
    train_count = sum(1 for p in train_val_payload["pairs"] if p["train_or_val"] == "train")
    val_count = sum(1 for p in train_val_payload["pairs"] if p["train_or_val"] == "val")
    print(f"  train: {train_count}, val: {val_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
