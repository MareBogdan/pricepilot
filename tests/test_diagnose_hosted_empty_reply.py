"""Phase 3 item 8 session 2, task 4: guards the ONE thing that must never go wrong in
`scripts/diagnose_hosted_empty_reply.py` -- the diagnostic call target is a VALIDATION pair,
never a TEST one. A second TEST touch for a diagnostic call would violate
docs/phase3-baseline-model-choice.md rule 3 for no reason (the diagnosis doesn't need TEST data)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import diagnose_hosted_empty_reply as diag  # noqa: E402


def test_first_validation_pair_is_never_a_test_pair_id() -> None:
    test_ids = {
        r["pair_id"] for r in json.loads(diag.INPUTS_TEST.read_text(encoding="utf-8"))["pairs"]
    }
    pair_id, text_a, text_b = diag._first_validation_pair()
    assert pair_id not in test_ids
    assert isinstance(text_a, str) and isinstance(text_b, str)


def test_first_validation_pair_is_in_the_frozen_val_split() -> None:
    split = json.loads(diag.SPLIT_JSON.read_text(encoding="utf-8"))
    val_ids = set(split["val"]["pair_ids"])
    pair_id, _, _ = diag._first_validation_pair()
    assert pair_id in val_ids
    assert pair_id == min(val_ids)  # "first, by pair_id order" -- pinned, not just asserted


def test_free_part_reads_no_test_label() -> None:
    """free_part() only reads latency-hosted.json (scores, not labels) and the TEST inputs file
    -- which itself carries no label field, guarded the same way run_hosted_baseline.py guards
    its own TEST read."""
    test_rows = json.loads(diag.INPUTS_TEST.read_text(encoding="utf-8"))["pairs"]
    assert not any(k in r for r in test_rows for k in ("label", "tier", "split"))
