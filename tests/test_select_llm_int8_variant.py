"""Phase 3 item 8 session 3, task 1: pins protocol 5.11's eligibility and selection logic in
`scripts/select_llm_int8_variant.py` -- the boundary that decides whether ANY LLM int8 variant
ever gets a TEST touch."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from select_llm_int8_variant import TIE_F1_MARGIN, is_eligible, select_variant  # noqa: E402


def _medians(m: float, n: float) -> dict[str, float]:
    return {"median_p_yes_true_M": m, "median_p_yes_true_N": n}


def test_separated_medians_are_eligible() -> None:
    assert is_eligible(_medians(0.995, 0.000)) is True


def test_inverted_medians_are_not_eligible() -> None:
    """The actual V2/V3 shape: both medians land on the same side of 0.5, or M < N."""
    assert is_eligible(_medians(0.431, 0.326)) is False  # both below 0.5
    assert is_eligible(_medians(0.235, 0.251)) is False  # M < N entirely


def test_medians_exactly_at_0_5_are_not_eligible() -> None:
    """0.5 > median_N and median_M > 0.5 are both STRICT -- a variant that only reaches the
    boundary does not separate the classes."""
    assert is_eligible(_medians(0.5, 0.3)) is False
    assert is_eligible(_medians(0.7, 0.5)) is False


def test_select_variant_none_eligible_returns_none() -> None:
    candidates = {
        "v2": {"eligible": False, "best_f1": 0.535, "p50_ms": 2218.9},
        "v3": {"eligible": False, "best_f1": 0.599, "p50_ms": 2338.0},
    }
    assert select_variant(candidates) is None


def test_select_variant_one_eligible_wins_regardless_of_f1() -> None:
    candidates = {
        "v2": {"eligible": True, "best_f1": 0.60, "p50_ms": 2000.0},
        "v3": {"eligible": False, "best_f1": 0.90, "p50_ms": 1000.0},
    }
    assert select_variant(candidates) == "v2"


def test_select_variant_both_eligible_picks_highest_f1() -> None:
    candidates = {
        "v2": {"eligible": True, "best_f1": 0.80, "p50_ms": 2000.0},
        "v3": {"eligible": True, "best_f1": 0.90, "p50_ms": 1000.0},
    }
    assert select_variant(candidates) == "v3"


def test_select_variant_tie_within_margin_picks_lower_p50() -> None:
    candidates = {
        "v2": {"eligible": True, "best_f1": 0.900, "p50_ms": 2000.0},
        "v3": {"eligible": True, "best_f1": 0.900 - TIE_F1_MARGIN * 0.5, "p50_ms": 1000.0},
    }
    assert select_variant(candidates) == "v3"  # well within the margin -- a tie


def test_select_variant_just_outside_tie_margin_is_not_a_tie() -> None:
    epsilon = 1e-9
    candidates = {
        "v2": {"eligible": True, "best_f1": 0.900, "p50_ms": 2000.0},
        "v3": {"eligible": True, "best_f1": 0.900 - TIE_F1_MARGIN - epsilon, "p50_ms": 1000.0},
    }
    assert select_variant(candidates) == "v2"  # v3 is worse by more than the margin -- no tie


def test_real_session3_inputs_select_no_variant() -> None:
    """The actual numbers from this session's Kaggle run (both architect-precheck and the
    committed files agree): neither V2 nor V3 is eligible."""
    assert is_eligible(_medians(0.431, 0.326)) is False  # V2
    assert is_eligible(_medians(0.322, 0.213)) is False  # V3
