"""Phase 3 item 8 session 3, task 4: pins the pure arithmetic in
`scripts/build_serving_table.py` -- the cost/wall-clock formulas protocol 5.6 fixes, and the
"refuse rather than fabricate" behaviour when hosted v2 has not been scored yet."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_serving_table import (  # noqa: E402
    K20_SCORINGS,
    K100_SCORINGS,
    VPS_USD_PER_HOUR,
    _fmt_proportion,
    _hosted_dollars_per_1000,
    _k_hours,
    _local_dollars_per_1000,
    main,
)


def test_local_dollars_per_1000_matches_protocol_5_6_formula() -> None:
    # protocol 5.6: VPS hourly USD x (1000 / pairs_per_s) / 3600
    pairs_per_s = 12.26415414350153  # the real CE fp32 figure
    expected = VPS_USD_PER_HOUR * (1000.0 / pairs_per_s) / 3600.0
    assert _local_dollars_per_1000(pairs_per_s) == pytest.approx(expected)
    assert _local_dollars_per_1000(pairs_per_s) > 0


def test_hosted_dollars_per_1000_is_measured_cost_over_pairs_times_1000() -> None:
    assert _hosted_dollars_per_1000(cost_usd=0.400858, pairs=287) == pytest.approx(
        0.400858 / 287 * 1000
    )


def test_k_hours_scales_inversely_with_throughput() -> None:
    faster = _k_hours(pairs_per_s=20.0, scorings=K20_SCORINGS)
    slower = _k_hours(pairs_per_s=10.0, scorings=K20_SCORINGS)
    assert slower == pytest.approx(faster * 2)
    assert _k_hours(pairs_per_s=12.26415414350153, scorings=K20_SCORINGS) == pytest.approx(
        K20_SCORINGS / 12.26415414350153 / 3600.0
    )


def test_k100_is_five_times_k20_scorings() -> None:
    assert K100_SCORINGS == K20_SCORINGS * 5


def test_fmt_proportion_undefined_when_denominator_is_none() -> None:
    assert _fmt_proportion({"value": None, "n": 0}) == "undefined (n=0)"


def test_fmt_proportion_includes_the_wilson_ci() -> None:
    formatted = _fmt_proportion({"value": 0.9, "n": 100, "ci_95_lower": 0.8, "ci_95_upper": 0.95})
    assert "0.9000" in formatted and "100" in formatted
    assert "0.8000" in formatted and "0.9500" in formatted


def test_refuses_when_hosted_v2_has_not_been_scored_yet() -> None:
    """The real state as of this commit: hosted v2 has not run yet (blocked on a SPEND yes). The
    script must refuse, not fabricate a row or silently omit it."""
    with pytest.raises(SystemExit, match="hosted v2 has not been scored yet"):
        main()
