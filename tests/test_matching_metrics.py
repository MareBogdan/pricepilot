"""Tests for src/pricepilot/matching/metrics.py's Wilson score interval (CLAUDE.md §7 item 5;
ADR-0028 addendum #19). Every expected value here is either a well-known closed-form
simplification of the Wilson formula (a genuinely independent derivation, not the same code path
as the general case) or hand-worked arithmetic shown in the comment next to it -- never computed
by calling the function under test a second time."""

from __future__ import annotations

import math

import pytest

from pricepilot.matching.metrics import (
    Z_95,
    WilsonInterval,
    find_invalid_prediction_values,
    wilson_confidence_interval,
)


def test_zero_successes_case_hand_computed() -> None:
    """x=0 has a well-known closed-form simplification of the general Wilson formula (derived
    independently, not by running the general formula and checking it matches itself): when
    p_hat=0, the margin term collapses to equal the center exactly, so lower=0 exactly, and
    upper = z^2 / (n + z^2). n=10: z^2 = 1.959963984540054^2 = 3.840471861920298 (computed here,
    not imported), upper = 3.840471861920298 / 13.840471861920298 = 0.2775327998628892."""
    z2 = Z_95 * Z_95
    n = 10
    expected_upper = z2 / (n + z2)
    result = wilson_confidence_interval(successes=0, n=n)
    assert result.point == 0.0
    assert result.lower == 0.0
    assert math.isclose(result.upper, expected_upper, rel_tol=1e-12)
    assert math.isclose(expected_upper, 0.2775327998628892, rel_tol=1e-9)


def test_hundred_percent_case_hand_computed() -> None:
    """x=n's closed form is the mirror image of x=0's: upper=1 exactly, lower = n / (n + z^2).
    n=10: lower = 10 / 13.840471861920298 = 0.7224672001371107."""
    z2 = Z_95 * Z_95
    n = 10
    expected_lower = n / (n + z2)
    result = wilson_confidence_interval(successes=n, n=n)
    assert result.point == 1.0
    assert result.upper == 1.0
    assert math.isclose(result.lower, expected_lower, rel_tol=1e-12)
    assert math.isclose(expected_lower, 0.7224672001371107, rel_tol=1e-9)


def test_fifty_fifty_case_hand_worked_arithmetic() -> None:
    """n=100, x=50 -- the textbook symmetric case. Worked by hand (shown step by step, not by
    calling the function under test):
      p_hat = 0.5, z^2 = 3.840471861920298
      center = (0.5 + z^2/200) / (1 + z^2/100)
             = (0.5 + 0.019202359309601490) / (1.03840471861920298)
             = 0.519202359309601490 / 1.03840471861920298 = 0.5 exactly (numerator is always
               0.5 * denominator when p_hat = 0.5 -- algebraic identity, not a coincidence)
      margin = z * sqrt(0.25/100 + z^2/40000) / 1.03840471861920298
             = 1.959963984540054 * sqrt(0.0025 + 0.0000960117965...) / 1.03840471861920298
             ~= 0.099864...  / 1.038405 ~= 0.096168
      => interval ~= [0.403832, 0.596168], the widely-cited n=100 Wilson interval for a 50% rate.
    """
    result = wilson_confidence_interval(successes=50, n=100)
    assert result.point == 0.5
    assert math.isclose(result.lower, 0.4038315303659956, rel_tol=1e-9)
    assert math.isclose(result.upper, 0.5961684696340044, rel_tol=1e-9)
    # Symmetry sanity check independent of the exact digits above: the interval must be
    # symmetric around 0.5 when p_hat = 0.5.
    assert math.isclose(0.5 - result.lower, result.upper - 0.5, rel_tol=1e-9)


def test_n_zero_returns_the_maximally_uninformative_interval() -> None:
    result = wilson_confidence_interval(successes=0, n=0)
    assert result == WilsonInterval(point=0.0, lower=0.0, upper=1.0)


def test_interval_always_widens_as_n_shrinks_at_the_same_rate() -> None:
    """Not a hand-computed value -- a monotonicity property any correct implementation must
    satisfy, cheap to check and a useful second kind of evidence alongside the exact-value tests
    above."""
    small_n = wilson_confidence_interval(successes=5, n=10)
    large_n = wilson_confidence_interval(successes=50, n=100)
    assert (small_n.upper - small_n.lower) > (large_n.upper - large_n.lower)


def test_interval_bounds_never_escape_zero_one() -> None:
    for successes, n in [(0, 1), (1, 1), (0, 1000), (999, 1000), (1, 2)]:
        result = wilson_confidence_interval(successes, n)
        assert 0.0 <= result.lower <= result.point <= result.upper <= 1.0


def test_out_of_range_successes_raises() -> None:
    with pytest.raises(ValueError):
        wilson_confidence_interval(successes=11, n=10)
    with pytest.raises(ValueError):
        wilson_confidence_interval(successes=-1, n=10)


def test_find_invalid_prediction_values_catches_nan_and_infinity() -> None:
    """A reviewer finding on score_predictions.py/select_threshold.py: both threshold scores with
    a plain `score >= threshold`, and `NaN >= t` is always False, so an unvalidated NaN silently
    became a confident wrong "N" prediction instead of a refused run. Python's json.loads accepts
    bare NaN/Infinity by default, so this is reachable from an ordinary predictions file."""
    bad = find_invalid_prediction_values({"a": float("nan"), "b": float("inf"), "c": 0.5})
    assert set(bad) == {"a", "b"}
    assert "not finite" in bad["a"]
    assert "not finite" in bad["b"]


def test_find_invalid_prediction_values_catches_non_numeric_types() -> None:
    bad = find_invalid_prediction_values({"a": "0.9", "b": None, "c": [0.5], "d": 0.5})
    assert set(bad) == {"a", "b", "c"}
    assert all("not a number" in reason for reason in bad.values())


def test_find_invalid_prediction_values_rejects_bool_despite_being_an_int_subclass() -> None:
    """bool is a subclass of int in Python -- isinstance(True, (int, float)) is True -- so a
    stray JSON `true`/`false` in a predictions file would otherwise silently pass as 1/0."""
    bad = find_invalid_prediction_values({"a": True, "b": False, "c": 0.5})
    assert set(bad) == {"a", "b"}


def test_find_invalid_prediction_values_accepts_a_clean_payload() -> None:
    bad = find_invalid_prediction_values({"a": 0.0, "b": 1.0, "c": 0.5, "d": -3, "e": 4})
    assert bad == {}
