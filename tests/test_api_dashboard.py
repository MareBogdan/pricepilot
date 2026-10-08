"""Dashboard API: each endpoint returns the SQL-sourced numbers, and degrades when the database is
down. The expected values are computed here by hand from the fixture rows, not read back from the
code under test. No HTML snapshot tests.
"""

from __future__ import annotations

import json
import re
import struct
import warnings
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from services.mock_store.app import get_history_points
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from pricepilot.api import deps, facts
from pricepilot.api import results as api_results
from pricepilot.api.anonymise import public_shop
from pricepilot.api.main import app
from pricepilot.api.routes_api import router as api_router
from pricepilot.api.routes_pages import router as pages_router
from pricepilot.decision.scenarios import SUPERSEDED_RUN_LABEL
from pricepilot.models import (
    Product,
    ProductMatch,
    RawListing,
    Recommendation,
    ScrapeRun,
)

ROOT = Path(__file__).resolve().parents[1]
DAY1, DAY2 = date(2026, 10, 5), date(2026, 10, 6)


@pytest.fixture()
def session() -> Iterator[Session]:
    # One shared in-memory connection: TestClient runs sync endpoints on a worker thread.
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # SQLite stores Numeric as float; Decimal API still holds
        for model in (Product, ProductMatch, Recommendation, ScrapeRun, RawListing):
            model.__table__.create(engine)  # type: ignore[attr-defined]
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE policy_chunks (section_ref TEXT, heading TEXT, text TEXT, "
                    "embedding TEXT)"
                )
            )
            conn.execute(
                text("INSERT INTO policy_chunks VALUES ('2', 'Margin floors', 'Never below.', '')")
            )
        with Session(engine, expire_on_commit=False) as s:
            _seed(s)
            s.commit()
            yield s


def _seed(s: Session) -> None:
    # id 1 exists in the mock store, so the synthetic-history endpoint can serve it.
    s.add(
        Product(
            id=1,
            sku="SKU-1",
            title="Test kibble 3 kg",
            brand="Acme",
            category="dry_food",
            purchase_cost=Decimal("100.00"),
            current_price=Decimal("150.00"),
            stock=40,
        )
    )
    s.add(
        Product(
            id=2,
            sku="SKU-2",
            title="Unmatched thing",
            brand="Acme",
            category="treats",
            purchase_cost=Decimal("10.00"),
            current_price=Decimal("20.00"),
            stock=5,
        )
    )
    s.add(ScrapeRun(id=1, source="shop_a_ro", status="ok", started_at=datetime(2026, 10, 6)))
    for src, ext, price in (("shop_a_ro", "a1", "140.00"), ("shop_b_ro", "b1", "160.00")):
        s.add(
            ProductMatch(
                product_id=1,
                source=src,
                norm_listing_id=1,
                content_hash="h" * 64,
                external_id=ext,
                url=f"https://example.invalid/{ext}",
                competitor_title=f"title {ext}",
                score=Decimal("0.950000"),
                threshold=Decimal("0.890000"),
                model_sha256="m" * 64,
                competitor_price=Decimal(price),
                price_date=DAY2,
                in_stock=True,
            )
        )
    # Raw observations: a1 on two days, plus one regulated (excluded) row that must not count.
    for day, price in ((DAY1, "141.00"), (DAY2, "140.00")):
        s.add(_raw("shop_a_ro", "a1", day, price))
    s.add(_raw("shop_b_ro", "b1", DAY2, "160.00"))
    s.add(_raw("shop_b_ro", "regulated", DAY2, "9.00", excluded="regulated"))

    def rec(**kw: Any) -> Recommendation:
        base: dict[str, Any] = {
            "product_id": 1,
            "run_label": "r",
            "is_mock": False,
            "scenario": None,
            "category": "dry_food",
            "cost": Decimal("100.00"),
            "current_price": Decimal("150.00"),
            "stock": 40,
            "competitor_prices": [],
            "price_7d_ago": Decimal("151.00"),
            "price_7d_ago_source": "mock_store_synthetic",
            "elasticity_placeholder": {"value": None, "label": "PLACEHOLDER label"},
            "rag_sections": [{"section_ref": "2", "similarity": 0.61}],
            "prompt_text": "p",
            "llm_model": "claude-test",
            "llm_raw_reply": "r",
            "llm_proposed_price": Decimal("145.00"),
            "llm_rationale": "Between the two competitors.",
            "llm_cost_usd": Decimal("0.01"),
            "guard_status": "APPROVE",
            "guard_final_price": Decimal("145.00"),
            "guard_reason": None,
        }
        base.update(kw)
        return Recommendation(**base)

    s.add(
        rec(
            run_label="old",
            llm_proposed_price=Decimal("999.00"),
            guard_final_price=Decimal("999.00"),
        )
    )
    s.add(rec(run_label="new"))  # newest real, unperturbed: this one must be shown
    # A superseded row written AFTER the newest one must still never be shown.
    s.add(rec(run_label=SUPERSEDED_RUN_LABEL, llm_rationale="SUPERSEDED ROW"))
    s.add(rec(run_label="mock", is_mock=True, llm_rationale="MOCK ROW"))
    s.add(
        rec(
            run_label="stress",
            scenario="competitor_crash",
            llm_proposed_price=Decimal("90.00"),
            guard_status="FLAG",
            guard_final_price=None,
            guard_reason="below the floor",
        )
    )


def _raw(source: str, ext: str, day: date, price: str, excluded: str | None = None) -> RawListing:
    return RawListing(
        run_id=1,
        source=source,
        external_id=ext,
        collected_date=day,
        url=f"https://example.invalid/{ext}",
        title="t",
        price=Decimal(price),
        excluded_reason=excluded,
        content_hash="c" * 64,
        scraped_at=datetime(2026, 10, 6, tzinfo=UTC),
    )


@pytest.fixture()
def client(session: Session) -> Iterator[TestClient]:
    def _session() -> Iterator[Session]:
        yield session

    app.dependency_overrides[deps.get_session] = _session
    app.dependency_overrides[deps.get_optional_session] = _session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_products_list_numbers_come_from_the_rows(client: TestClient) -> None:
    rows = client.get("/api/products").json()
    first, second = rows
    assert first["sku"] == "SKU-1"
    # (150 - 100) / 150 = 33.3%; dry_food floor in config/pricing-policy.toml is 12%
    assert first["margin_pct"] == "33.3"
    assert first["margin_floor_pct"] == "12.0"
    assert (first["cost"], first["current_price"], first["stock"]) == ("100.00", "150.00", 40)
    assert first["matches"] == 2
    assert first["guard_status"] == "APPROVE"
    assert second["matches"] == 0 and second["guard_status"] is None


def test_product_detail_matches_and_price_position(client: TestClient) -> None:
    d = client.get("/api/products/1").json()
    assert [m["shop"] for m in d["matches"]] == [
        public_shop("shop_a_ro"),
        public_shop("shop_b_ro"),
    ]  # cheapest first
    pos = d["position"]
    assert (pos["min"], pos["median"], pos["max"]) == ("140.00", "150.00", "160.00")
    assert pos["vs_min_pct"] == "7.1"  # (150 - 140) / 140
    assert pos["vs_median_pct"] == "0.0"
    # lowest price clearing the 12% floor: 100 / 0.88 = 113.636... rounded UP to the cent
    assert d["floor_price"] == "113.64"


def test_product_without_matches_has_an_empty_position(client: TestClient) -> None:
    d = client.get("/api/products/2").json()
    assert d["matches"] == []
    assert d["position"]["competitors"] == 0 and d["position"]["median"] is None
    assert d["recommendation"] is None


def test_detail_shows_newest_real_recommendation_and_stress_tests_separately(
    client: TestClient,
) -> None:
    d = client.get("/api/products/1").json()
    r = d["recommendation"]
    # not the older row, the superseded row, the mock row or the scenario row
    assert r["run_label"] == "new"
    assert r["scenario"] is None
    assert (r["proposed_price"], r["guard_status"], r["guard_final_price"]) == (
        "145.00",
        "APPROVE",
        "145.00",
    )
    assert r["rationale"] == "Between the two competitors."
    # (145 - 100) / 145 = 31.0%
    assert (r["proposed_margin_pct"], r["final_margin_pct"], r["margin_floor_pct"]) == (
        "31.0",
        "31.0",
        "12.0",
    )
    assert r["rag_sections"] == [
        {"section_ref": "2", "similarity": 0.61, "heading": "Margin floors", "text": "Never below."}
    ]
    assert r["elasticity_placeholder"]["label"] == "PLACEHOLDER label"
    assert r["price_7d_ago_source"] == "mock_store_synthetic"
    (stress,) = d["stress_tests"]
    assert (stress["scenario"], stress["guard_status"], stress["guard_final_price"]) == (
        "competitor_crash",
        "FLAG",
        None,
    )


def test_history_labels_synthetic_and_real_series(client: TestClient) -> None:
    h = client.get("/api/products/1/history").json()
    assert len(h["our_price_synthetic"]) == len(get_history_points(1))
    assert h["our_price_note"].startswith("SYNTHETIC")
    assert h["competitors_note"].startswith("REAL")
    by_shop = {s["shop"]: s["points"] for s in h["competitors_real"]}
    assert by_shop[public_shop("shop_a_ro")] == [["2026-10-05", "141.00"], ["2026-10-06", "140.00"]]
    assert by_shop[public_shop("shop_b_ro")] == [["2026-10-06", "160.00"]]


def test_status_counts_are_sql_counts(client: TestClient) -> None:
    s = client.get("/api/status").json()
    assert s["database"] is True
    assert s["collection_days"] == 2  # distinct collected_date (the excluded row is on DAY2 too)
    assert (s["first_day"], s["last_day"]) == ("2026-10-05", "2026-10-06")
    assert s["price_observations"] == 3  # 4 rows minus the excluded one
    assert s["in_scope_listings"] == 2  # a1 and b1; a1's two days are one listing
    assert {x["source"]: x["in_scope_listings"] for x in s["sources"]} == {
        public_shop("shop_a_ro"): 1,
        public_shop("shop_b_ro"): 1,
    }
    assert s["products"] == 2
    assert s["recommendations_real"] == {"APPROVE": 1}
    assert (s["matcher"]["links"], s["matcher"]["products_with_link"]) == (2, 1)
    assert s["matcher"]["threshold"] == "0.890000"
    assert s["matcher"]["precision_pre_guard"] == facts.PRECISION_PRE_GUARD
    kinds = {row["item"]: row["kind"] for row in s["real_vs_simulated"]}
    assert kinds["Sales volumes"] == "simulated"
    assert kinds["Price elasticity"] == "placeholder"


def test_unknown_product_is_404(client: TestClient) -> None:
    assert client.get("/api/products/999").status_code == 404
    assert client.get("/api/products/999/history").status_code == 404


def test_api_and_dashboard_are_read_only() -> None:
    # Checked on the routers themselves: FastAPI wraps included routers inside `app.routes`.
    for router in (api_router, pages_router):
        routes = [r for r in router.routes if isinstance(r, APIRoute)]
        assert routes
        assert all(r.methods == {"GET"} for r in routes)


def test_precision_facts_still_match_their_source_document() -> None:
    doc = (ROOT / facts.PRECISION_SOURCE_DOC).read_text(encoding="utf-8")
    for figure in facts.PRECISION_SOURCE_FIGURES:
        assert figure in doc


@pytest.fixture()
def database_down(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    def boom(_engine: Any) -> Any:
        raise OperationalError("connect", {}, Exception("offline"))

    monkeypatch.setattr(deps, "connect_with_wakeup_retry", boom)
    app.dependency_overrides.clear()
    return TestClient(app)


def test_offline_api_returns_503_not_a_crash(database_down: TestClient) -> None:
    resp = database_down.get("/api/products")
    assert resp.status_code == 503
    assert resp.json() == {"detail": "database unavailable"}


def test_offline_status_degrades_to_the_documented_facts(database_down: TestClient) -> None:
    resp = database_down.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] is False
    assert body["collection_days"] is None and body["sources"] == []
    assert body["matcher"]["precision_post_guard"] == facts.PRECISION_POST_GUARD
    assert body["phases"] and body["real_vs_simulated"]


def test_offline_pages_say_so_instead_of_crashing(database_down: TestClient) -> None:
    assert database_down.get("/").status_code == 503
    assert database_down.get("/products/1").status_code == 503
    assert database_down.get("/status").status_code == 200  # static facts still render


def test_public_surface_never_shows_real_shop_names_or_shop_links(
    client: TestClient, session: Session
) -> None:
    """LEGAL.md: shops appear as Shop A/B/C and nothing links to their pages. Re-point the seeded
    rows at the three real source names, then scan every page and JSON endpoint."""
    for old, new in (("shop_a_ro", "animax_ro"), ("shop_b_ro", "petmax_ro")):
        for model in (ProductMatch, RawListing, ScrapeRun):
            session.query(model).filter_by(source=old).update({"source": new})
    session.commit()
    paths = ["/", "/status", "/products/1", "/api/products/1", "/api/products/1/history"]
    paths += ["/api/status", "/api/overview", "/api/products"]
    bodies = {p: client.get(p) for p in paths}
    for path, resp in bodies.items():
        assert resp.status_code == 200, path
        text_ = resp.text.lower()
        for forbidden in (
            "animax",
            "petmax",
            "pentruanimale",
            "example.invalid",
            'target="_blank"',
        ):
            assert forbidden not in text_, (path, forbidden)
    assert "Shop A" in bodies["/products/1"].text and "Shop C" in bodies["/products/1"].text
    match = client.get("/api/products/1").json()["matches"][0]
    assert "url" not in match and match["shop"] == "shop_a"


def test_corrupt_cost_shows_no_margin_instead_of_a_fake_one(
    client: TestClient, session: Session
) -> None:
    session.get(Product, 2).purchase_cost = Decimal("0.00")  # type: ignore[union-attr]
    session.commit()
    row = client.get("/api/products").json()[1]
    assert row["margin_pct"] is None


def test_zero_competitor_price_and_unknown_mock_store_id_do_not_crash(
    client: TestClient, session: Session
) -> None:
    session.query(ProductMatch).filter_by(source="shop_a_ro").one().competitor_price = Decimal(
        "0.00"
    )
    session.add(
        Product(
            id=99999,
            sku="NOT-IN-MOCK",
            title="x",
            brand="x",
            category="treats",
            purchase_cost=Decimal("1.00"),
            current_price=Decimal("2.00"),
            stock=1,
        )
    )
    session.commit()
    pos = client.get("/api/products/1").json()["position"]
    assert pos["min"] == "0.00" and pos["vs_min_pct"] is None
    assert client.get("/products/1").status_code == 200
    history = client.get("/api/products/99999/history")
    assert history.status_code == 200 and history.json()["our_price_synthetic"] == []


# --- 7a.2: overview aggregates, listings reconciliation, committed results --------------------


def _json(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "docs" / "learned" / "results" / name).read_text(encoding="utf-8"))


def test_overview_counts_are_sql_counts(client: TestClient) -> None:
    o = client.get("/api/overview").json()
    assert o["database"] is True
    assert (o["products"], o["products_matched"], o["match_links"], o["match_shops"]) == (
        2,
        1,
        2,
        2,
    )
    # in-scope rows only: a1 on two days + b1 on one; the excluded row is not counted
    assert (o["collection_days"], o["price_rows"], o["sources"]) == (2, 3, 2)
    # non-superseded real rows: "old", "new" (APPROVE) and the competitor_crash stress row (FLAG)
    assert o["audit"] == {
        "recommendations": 3,
        "approve": 2,
        "flag": 1,
        "reject": 0,
        "margin_violations": 0,
    }
    assert o["verdict_mix"] == [
        {"group": "baseline", "approve": 2, "flag": 0, "reject": 0},
        {"group": "competitor_crash", "approve": 0, "flag": 1, "reject": 0},
    ]
    margins = {c["category"]: c for c in o["category_margins"]}
    # (150 - 100) / 150 = 33.3%; (20 - 10) / 20 = 50.0%; floors from config/pricing-policy.toml
    assert (margins["dry_food"]["avg_margin_pct"], margins["dry_food"]["floor_pct"]) == (
        "33.3",
        "12.0",
    )
    assert (margins["treats"]["avg_margin_pct"], margins["treats"]["floor_pct"]) == ("50.0", "25.0")


def test_audit_counts_an_approved_price_below_the_floor(
    client: TestClient, session: Session
) -> None:
    bad = session.query(Recommendation).filter_by(run_label="new").one()
    bad.guard_final_price = Decimal("105.00")  # (105 - 100) / 105 = 4.8% < the 12% dry-food floor
    session.commit()
    assert client.get("/api/overview").json()["audit"]["margin_violations"] == 1


def test_listing_counts_separate_the_gate_window_from_today(
    client: TestClient, session: Session
) -> None:
    session.add(_raw("shop_a_ro", "a1", date(2026, 10, 7), "139.00"))
    session.add(_raw("shop_c_ro", "c1", date(2026, 10, 7), "50.00"))  # a new listing on day 3
    session.commit()
    lc = client.get("/api/status").json()["listing_counts"]
    # the window is the first two collection days; the third day is "today" only
    assert (lc["window_days"], lc["window_through"]) == (2, "2026-10-06")
    assert (lc["window_rows_stored"], lc["window_rows_in_scope"]) == (4, 3)
    assert lc["window_distinct_listings"] == 2  # a1 (two days) and b1
    assert (lc["now_rows_in_scope"], lc["now_distinct_listings"]) == (5, 3)


def test_hero_results_come_from_the_committed_result_files(client: TestClient) -> None:
    o = client.get("/api/overview").json()
    fine = _json("mmarco-mMiniLMv2-finetuned-ep6-metrics.json")
    zero = _json("mmarco-mMiniLMv2-zeroshot-metrics.json")
    assert o["matcher_result"]["f1"] == fine["f1"]["value"]
    assert o["matcher_result"]["baseline_f1"] == zero["f1"]["value"]
    assert o["matcher_result"]["n_test_pairs"] == fine["n_scored"]
    rag = _json("phase5-policy-retrieval-eval.json")
    assert (o["rag_result"]["hit_at_1"], o["rag_result"]["hit_at_3"], o["rag_result"]["mrr"]) == (
        rag["hit_at_1"],
        rag["hit_at_3"],
        rag["mrr"],
    )


def test_missing_result_files_show_nothing_instead_of_a_made_up_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_results, "RESULTS_DIR", tmp_path)
    assert api_results.matcher_result() is None
    assert api_results.rag_result() is None


def test_phase1_gate_figure_quoted_on_the_status_page_is_the_documented_one() -> None:
    assert facts.PHASE1_GATE_ROWS in (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_offline_overview_degrades_to_the_committed_results(database_down: TestClient) -> None:
    resp = database_down.get("/api/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database"] is False and body["audit"] is None and body["verdict_mix"] == []
    assert body["matcher_result"] is not None  # committed files do not need the database


def test_all_match_baseline_is_derived_from_the_committed_confusion_matrix() -> None:
    cm = _json("mmarco-mMiniLMv2-finetuned-ep6-metrics.json")["confusion_matrix"]
    positives, total = cm["tp"] + cm["fn"], sum(cm.values())
    rate = Decimal(positives) / Decimal(total)
    expected = float(
        2 * rate / (1 + rate)
    )  # F1 of "match" for every pair: recall 1, precision = rate
    got = api_results.matcher_result()
    assert got is not None and abs(got.all_match_f1 - expected) < 1e-9


def test_overview_skips_a_category_missing_from_the_policy_config(
    client: TestClient, session: Session
) -> None:
    session.add(
        Product(
            id=3,
            sku="SKU-3",
            title="Odd",
            brand="x",
            category="not_a_category",
            purchase_cost=Decimal("5.00"),
            current_price=Decimal("9.00"),
            stock=1,
        )
    )
    session.commit()
    cats = {c["category"] for c in client.get("/api/overview").json()["category_margins"]}
    assert "not_a_category" not in cats and "dry_food" in cats


SITE = "https://pricepilot-s1jj.onrender.com"
PREVIEW_TAGS = (
    '<meta property="og:type" content="website">',
    f'<meta property="og:url" content="{SITE}/">',
    '<meta property="og:title" content="PricePilot — competitive pricing intelligence">',
    f'<meta property="og:image" content="{SITE}/static/og.png">',
    '<meta property="og:image:width" content="1200">',
    '<meta property="og:image:height" content="630">',
    '<meta name="twitter:card" content="summary_large_image">',
)


@pytest.mark.parametrize("path", ["/", "/products/1", "/products/999", "/status"])
def test_every_page_carries_link_preview_metadata(client: TestClient, path: str) -> None:
    html = client.get(path).text  # 200 pages and the 404 page all extend base.html
    for tag in PREVIEW_TAGS:
        assert tag in html, f"{path} is missing {tag}"
    descriptions = re.findall(
        r'<meta (?:name="description"|property="og:description") content="([^"]+)"', html
    )
    assert len(descriptions) == 2 and descriptions[0] == descriptions[1]
    assert len(descriptions[0]) < 160


def test_unavailable_page_carries_link_preview_metadata(database_down: TestClient) -> None:
    html = database_down.get("/").text
    assert all(tag in html for tag in PREVIEW_TAGS)


def test_og_image_is_a_served_1200x630_png(client: TestClient) -> None:
    r = client.get("/static/og.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", r.content[16:24])  # IHDR: width, height
    assert (width, height) == (1200, 630)
