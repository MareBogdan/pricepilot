"""Statistics helpers for the Phase 3 matching harness (CLAUDE.md §7 item 5; ADR-0028 addendum
#19). Implemented from the closed-form Wilson score formula directly -- no `scipy`/`statsmodels`
dependency -- because the harness must run with zero installed model/stats libraries beyond what
this project already has.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# z for a 95% two-sided confidence interval (Phi^-1(0.975)), the standard constant every
# statistics reference quotes to 4+ decimal places. Not computed at runtime (that would need a
# normal-distribution inverse-CDF implementation this module has no other use for); hardcoded and
# named so the one magic number in this file is self-explanatory.
Z_95 = 1.959963984540054


@dataclass(frozen=True, slots=True)
class WilsonInterval:
    point: float
    lower: float
    upper: float


def wilson_confidence_interval(successes: int, n: int, z: float = Z_95) -> WilsonInterval:
    """The Wilson score interval for a binomial proportion `successes / n`, at the confidence
    level implied by `z` (default: 95%, two-sided).

    Preferred over the naive `p +/- z*sqrt(p(1-p)/n)` (Wald) interval because Wald produces a
    zero-width or out-of-[0,1] interval at p=0 or p=1 -- exactly the cases this harness hits
    constantly (a tier with 0 positives, a perfect predictor). Wilson stays inside [0, 1] and
    gives a real, non-degenerate interval even at the extremes.

    `n == 0` (no trials at all -- a tier that is entirely absent, not just entirely one label)
    returns the maximally uninformative interval `[0.0, 1.0]` rather than raising or dividing by
    zero: there is no valid point estimate, but a caller printing an interval-shaped line rather
    than crashing is more useful, matching this project's "a status command that crashes is worse
    than useless" convention.
    """
    if n == 0:
        return WilsonInterval(point=0.0, lower=0.0, upper=1.0)
    if successes < 0 or successes > n:
        raise ValueError(f"successes={successes} must be between 0 and n={n}")

    p_hat = successes / n
    z2 = z * z
    denominator = 1 + z2 / n
    center = (p_hat + z2 / (2 * n)) / denominator
    margin = (z * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))) / denominator
    lower = center - margin
    upper = center + margin
    # At p_hat = 0 or 1, "center - margin"/"center + margin" are ALGEBRAICALLY exactly 0/1 (the
    # margin term collapses to equal the center exactly -- see tests/test_matching_metrics.py's
    # worked derivation) but floating-point subtraction of two near-equal values can leave a
    # residue on the order of 1e-19 on either side of the true boundary. Pin the known-exact
    # boundary explicitly rather than merely clamping (`max(0.0, ...)`), which would only catch a
    # NEGATIVE residue and silently let a tiny POSITIVE one through as a non-zero "lower bound".
    if successes == 0:
        lower = 0.0
    if successes == n:
        upper = 1.0
    lower = max(0.0, min(1.0, lower))
    upper = max(0.0, min(1.0, upper))
    return WilsonInterval(point=p_hat, lower=lower, upper=upper)


def find_invalid_prediction_values(predictions: Mapping[str, Any]) -> dict[str, str]:
    """Returns {pair_id: reason} for every value in a `{pair_id: score}` predictions mapping that
    is not a finite real number usable as a score (CLAUDE.md §9: silent degradation must never
    happen). `score_predictions.py` and `select_threshold.py` both threshold scores with a plain
    `score >= threshold` comparison -- Python's `json.loads` accepts bare `NaN`/`Infinity` by
    default, and `NaN >= t` is always False, so an unvalidated NaN score silently becomes a
    confident, wrong "N" prediction rather than a refused run. A JSON boolean is also rejected
    explicitly: `bool` is a subclass of `int` in Python, so `isinstance(True, (int, float))` is
    true and a stray `true`/`false` in the predictions file would otherwise pass silently as 1/0.
    """
    bad: dict[str, str] = {}
    for pair_id, value in predictions.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            bad[pair_id] = f"not a number: {value!r}"
        elif isinstance(value, float) and not math.isfinite(value):
            bad[pair_id] = f"not finite: {value!r}"
    return bad


def mcnemar_exact_p(b: int, c: int) -> float:
    """Exact two-sided McNemar p-value from the two discordant counts of a paired comparison
    (`b` = pairs only model A got right, `c` = pairs only model B got right).

    Under H0 (the two models are equally likely to be the one that is right on a pair they
    disagree on) the smaller discordant count is Binomial(b + c, 0.5); the two-sided p-value is
    2 * P(X <= min(b, c)), capped at 1. Exact rather than the chi-square approximation because
    the discordant counts here are small (single digits to low tens), where chi-square is
    unreliable. Implemented from the binomial formula directly -- no scipy.
    """
    if b < 0 or c < 0:
        raise ValueError("discordant counts must be non-negative")
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2**n
    return float(min(1.0, 2 * tail))


def intervals_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    """True iff the closed intervals [a0, a1] and [b0, b1] share at least one point."""
    return a[0] <= b[1] and b[0] <= a[1]
