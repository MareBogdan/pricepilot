"""Phase 5 session 3b: pure selection / mapping logic of the serve-time matcher (ADR-0039).

No model, no database. The cross-encoder itself is vouched for by
`scripts/check_ce_faithfulness.py`, not by a unit test.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from pricepilot.matching.pair_text import ATTRIBUTE_FIELDS, build_pair_text
from pricepilot.matching.serve import (
    MATCH_THRESHOLD,
    ScoredLink,
    norm_row_to_record,
    product_to_listing,
    score_to_decimal,
    select_best_per_shop,
    select_current_prices,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from match_catalogue import WORKSHEET_COLUMNS, size_text


def test_weighted_product_becomes_a_listing_record() -> None:
    listing = product_to_listing("Orijen Original Dog Adult Mini 1.8 kg", "Orijen", 1800)
    rec = listing.record
    assert rec["title"] == "Orijen Original Dog Adult Mini 1.8 kg"
    assert (rec["brand"], rec["product_line"], rec["net_weight_g"]) == (
        "orijen",
        "Original Dog Adult Mini",
        1800,
    )
    assert rec["life_stage"] == "adult" and rec["flavour"] is None
    assert listing.blocking_key == "orijen"
    # a missing attribute renders as the explicit marker, never as an empty string
    text_a, _ = build_pair_text(rec, rec)
    assert "flavour: <missing>" in text_a and "weight_g: 1800" in text_a


def test_row_weight_is_the_system_of_record_and_volume_only_item_keeps_volume() -> None:
    def fake_extractor(title: str, source_brand: str | None = None) -> SimpleNamespace:
        return SimpleNamespace(
            brand="trixie",
            product_line="Ceramic Bowl",
            net_weight_g=999,  # extractor disagrees with the row
            net_volume_ml=None,
            pack_count=None,
            bonus_weight_g=None,
            breed_size_code=None,
            life_stage=None,
            food_form=None,
            flavour=None,
        )

    assert product_to_listing("x", "Trixie", 1800, fake_extractor).record["net_weight_g"] == 1800

    bowl = product_to_listing("Trixie Ceramic Bowl 0.3L", "Trixie", None)
    assert bowl.record["net_weight_g"] is None and bowl.record["net_volume_ml"] == 300


def test_norm_row_record_has_exactly_title_plus_ten_attributes() -> None:
    row = SimpleNamespace(sample_title="T", **{f: f"v-{f}" for f in ATTRIBUTE_FIELDS})
    assert norm_row_to_record(row) == {"title": "T", **{f: f"v-{f}" for f in ATTRIBUTE_FIELDS}}


def _link(pid: int, src: str, score: float, ext: str) -> ScoredLink:
    return ScoredLink(pid, src, score, ext)


def test_best_score_wins_per_product_and_shop() -> None:
    kept = select_best_per_shop(
        [
            _link(1, "petmax", 0.91, "a"),
            _link(1, "petmax", 0.97, "b"),  # same shop, higher score -> wins
            _link(1, "animax", 0.90, "c"),  # other shop -> its own match
            _link(2, "petmax", 0.93, "d"),  # other product -> its own match
        ],
        MATCH_THRESHOLD,
    )
    assert [(k.product_id, k.source, k.external_id) for k in kept] == [
        (1, "animax", "c"),
        (1, "petmax", "b"),
        (2, "petmax", "d"),
    ]


def test_threshold_is_inclusive_and_ties_are_deterministic() -> None:
    kept = select_best_per_shop(
        [
            _link(1, "s", 0.8899999, "below"),
            _link(2, "s", 0.89, "exactly"),
            _link(3, "s", 0.95, "z"),
            _link(3, "s", 0.95, "m"),  # exact tie -> lowest external_id
        ],
        0.89,
    )
    assert [(k.product_id, k.external_id) for k in kept] == [(2, "exactly"), (3, "m")]


def _obs(src: str, ext: str, day: int, price: str, in_stock: bool | None) -> dict:
    return {
        "source": src,
        "external_id": ext,
        "collected_date": date(2026, 10, day),
        "price": Decimal(price),
        "in_stock": in_stock,
    }


def test_current_price_is_latest_day_then_in_stock_then_cheapest() -> None:
    latest = {"petmax": date(2026, 10, 4), "animax": date(2026, 10, 4)}
    rows = [
        _obs("petmax", "p1", 3, "100.00", True),  # older day: loses to any day-4 row
        _obs("petmax", "p2", 4, "90.00", False),  # newest day but out of stock
        _obs("petmax", "p3", 4, "95.00", True),  # newest day, in stock -> wins over cheaper p2
        _obs("petmax", "p4", 4, "97.00", True),  # in stock but dearer than p3
        _obs("animax", "a1", 4, "88.50", None),
    ]
    chosen = select_current_prices(rows, latest)
    assert (chosen["petmax"]["external_id"], chosen["petmax"]["price"]) == ("p3", Decimal("95.00"))
    assert chosen["animax"]["price"] == Decimal("88.50")


def test_stale_or_unknown_shop_has_no_current_price() -> None:
    latest = {"petmax": date(2026, 10, 4)}
    rows = [
        _obs("petmax", "old", 1, "50.00", True),  # 3 days old: still current
        _obs("ghost", "g", 4, "10.00", True),  # shop with no scrape date: skipped
    ]
    assert set(select_current_prices(rows, latest)) == {"petmax"}
    assert select_current_prices(rows, latest, max_age_days=2) == {}


def test_persisted_score_never_rounds_up_across_the_threshold() -> None:
    assert score_to_decimal(0.8899999) == Decimal("0.889999") < Decimal("0.89")
    assert score_to_decimal(0.89) == Decimal("0.890000")
    assert score_to_decimal(0.9999999) == Decimal("0.999999")


def test_blind_worksheet_has_no_score_and_no_label_column() -> None:
    lowered = [c.lower() for c in WORKSHEET_COLUMNS]
    assert not any(w in c for c in lowered for w in ("score", "label", "yes", "prob"))
    assert size_text(1800, None) == "1800 g" and size_text(None, 300) == "300 ml"
    assert size_text(None, None) == ""
