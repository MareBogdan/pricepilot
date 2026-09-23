"""McNemar exact p-value and interval-overlap helpers (Phase 3 item 7)."""

from __future__ import annotations

import math

import pytest

from pricepilot.matching.metrics import intervals_overlap, mcnemar_exact_p


def test_no_discordant_pairs_gives_p_one() -> None:
    assert mcnemar_exact_p(0, 0) == 1.0


def test_equal_discordant_counts_give_p_one() -> None:
    assert mcnemar_exact_p(7, 7) == 1.0


def test_one_sided_five_zero_is_two_over_thirty_two() -> None:
    # P(X <= 0 | n=5) = 1/32; two-sided = 2/32 = 0.0625, exactly.
    assert mcnemar_exact_p(5, 0) == pytest.approx(0.0625)
    assert mcnemar_exact_p(0, 5) == pytest.approx(0.0625)


def test_symmetric_in_its_arguments() -> None:
    assert mcnemar_exact_p(3, 11) == mcnemar_exact_p(11, 3)


def test_known_value_ten_versus_two() -> None:
    # n=12: P(X<=2) = (1 + 12 + 66) / 4096 = 79/4096; two-sided = 158/4096.
    assert mcnemar_exact_p(10, 2) == pytest.approx(158 / 4096)


def test_capped_at_one() -> None:
    assert mcnemar_exact_p(6, 5) <= 1.0
    assert math.isclose(mcnemar_exact_p(6, 5), 1.0)


def test_negative_counts_rejected() -> None:
    with pytest.raises(ValueError):
        mcnemar_exact_p(-1, 3)


def test_intervals_overlap_cases() -> None:
    assert intervals_overlap((0.1, 0.5), (0.4, 0.9))
    assert intervals_overlap((0.1, 0.5), (0.5, 0.9))  # touching endpoints count
    assert not intervals_overlap((0.1, 0.4), (0.5, 0.9))
    assert intervals_overlap((0.0, 1.0), (0.3, 0.4))  # containment
