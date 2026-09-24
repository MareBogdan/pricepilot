"""Phase 3 item 8 session 2, task 1: pins G1's pass/fail logic in `scripts/check_serving_gates.py`
-- the one gate that decides whether ANY serving number is reported at all (protocol 5.9: LoRA
export failure means stop and report, no silent fallback). The other gates (G1b, G2) are reported,
not gated, so there is nothing to pin a pass/fail boundary on."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_serving_gates import G1_MAX_ABS_DIFF, compare, g1_passes  # noqa: E402


def test_identical_predictions_pass() -> None:
    a = {"p1": 0.1, "p2": 0.9}
    c = compare(a, dict(a), threshold=0.5, label="identical")
    assert c["max_abs_diff"] == 0.0 and c["flips"] == 0
    assert g1_passes(c) is True


def test_tiny_diff_within_tolerance_and_no_flip_passes() -> None:
    a = {"p1": 0.100000, "p2": 0.900000}
    b = {"p1": 0.100000 + G1_MAX_ABS_DIFF * 0.5, "p2": 0.900000}
    c = compare(a, b, threshold=0.5, label="tiny diff")
    assert c["max_abs_diff"] < G1_MAX_ABS_DIFF
    assert g1_passes(c) is True


def test_diff_over_tolerance_fails_even_with_no_flip() -> None:
    a = {"p1": 0.100000, "p2": 0.900000}
    b = {"p1": 0.100000 + G1_MAX_ABS_DIFF * 10, "p2": 0.900000}
    c = compare(a, b, threshold=0.5, label="over tolerance")
    assert c["flips"] == 0  # same side of the threshold both times
    assert g1_passes(c) is False


def test_single_decision_flip_fails_even_with_a_tiny_diff() -> None:
    """A diff can be well within tolerance and still flip a decision if it straddles the
    threshold -- G1 must fail on the flip regardless of how small the diff is."""
    a = {"p1": 0.499999, "p2": 0.900000}
    b = {"p1": 0.500001, "p2": 0.900000}
    c = compare(a, b, threshold=0.5, label="straddles threshold")
    assert c["max_abs_diff"] < G1_MAX_ABS_DIFF
    assert c["flips"] == 1
    assert g1_passes(c) is False


def test_mismatched_pair_ids_refuses_rather_than_silently_dropping() -> None:
    a = {"p1": 0.1, "p2": 0.9}
    b = {"p1": 0.1, "p3": 0.9}
    with pytest.raises(SystemExit):
        compare(a, b, threshold=0.5, label="mismatched ids")


def test_aggregate_g1_fails_if_any_single_check_fails() -> None:
    """Mirrors main()'s `all(g1_passes(c) for c in g1_checks)` -- one bad check must sink the
    whole gate, not get averaged away by three good ones."""
    good = compare({"p1": 0.1}, {"p1": 0.1}, threshold=0.5, label="good")
    bad = compare({"p1": 0.499999}, {"p1": 0.500001}, threshold=0.5, label="bad")
    checks = [good, good, good, bad]
    assert all(g1_passes(c) for c in checks) is False
