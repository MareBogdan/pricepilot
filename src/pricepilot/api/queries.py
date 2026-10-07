"""Read-only SQL behind the dashboard API. Every number returned is a query result or comes from
`config/pricing-policy.toml`; nothing is retrieved by similarity or invented. No writes."""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from statistics import median
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import column, func, select, table
from sqlalchemy.orm import Session

from pricepilot.api import facts, results
from pricepilot.api.schemas import (
    CategoryMargin,
    CompetitorSeries,
    DecisionAudit,
    ListingCounts,
    MatcherFacts,
    MatchRow,
    OurPricePoint,
    Overview,
    PhaseState,
    PolicyPassage,
    PriceHistory,
    PricePosition,
    ProductDetail,
    ProductRow,
    RecommendationOut,
    SourceStatus,
    Status,
    StressTest,
    VerdictMixRow,
)
from pricepilot.decision.scenarios import SUPERSEDED_RUN_LABEL
from pricepilot.models import Product as ProductModel
from pricepilot.models import ProductMatch, RawListing, Recommendation, ScrapeRun
from pricepilot.policy.guard import margin, meets_floor
from pricepilot.policy.thresholds import load_thresholds

_ONE_DP = Decimal("0.1")
_CENT = Decimal("0.01")

HISTORY_NOTE = (
    "SYNTHETIC: the mock store generates this price and sales series; nobody observed it."
)
COMPETITOR_NOTE = "REAL: daily prices of the matched competitor listings, as scraped."


class ProductNotFound(LookupError):
    pass


def _pct(fraction: Decimal) -> Decimal:
    return (fraction * 100).quantize(_ONE_DP, rounding=ROUND_HALF_UP)


def _margin_pct(price: Decimal, cost: Decimal) -> Decimal | None:
    try:
        return _pct(margin(price, cost))
    except ValueError:  # corrupt (non-positive) input: show nothing rather than a fake margin
        return None


def _floor_fraction(category: str) -> Decimal:
    return Decimal(str(load_thresholds().margin_floor[category]))  # type: ignore[index]


def _latest_real_recommendations(session: Session) -> dict[int, Recommendation]:
    """Newest real (is_mock = FALSE), unperturbed (scenario IS NULL) recommendation per product."""
    rows = session.scalars(
        select(Recommendation)
        .where(
            Recommendation.is_mock.is_(False),
            Recommendation.scenario.is_(None),
            Recommendation.run_label != SUPERSEDED_RUN_LABEL,
        )
        .order_by(Recommendation.id)
    ).all()
    return {r.product_id: r for r in rows}  # ascending id: the last write per product wins


def _product_row(p: ProductModel, matches: int, rec: Recommendation | None) -> ProductRow:
    margin_pct = _margin_pct(p.current_price, p.purchase_cost)
    return ProductRow(
        id=p.id,
        sku=p.sku,
        title=p.title,
        brand=p.brand,
        category=p.category,
        cost=p.purchase_cost,
        current_price=p.current_price,
        margin_pct=margin_pct,
        margin_floor_pct=_pct(_floor_fraction(p.category)),
        stock=p.stock,
        matches=matches,
        guard_status=rec.guard_status if rec else None,
    )


def list_products(session: Session) -> list[ProductRow]:
    counts: dict[int, int] = {
        pid: n
        for pid, n in session.execute(
            select(ProductMatch.product_id, func.count()).group_by(ProductMatch.product_id)
        )
    }
    latest = _latest_real_recommendations(session)
    products = session.scalars(select(ProductModel).order_by(ProductModel.id)).all()
    return [_product_row(p, counts.get(p.id, 0), latest.get(p.id)) for p in products]


def _position(our_price: Decimal, matches: list[MatchRow]) -> PricePosition:
    prices = [m.price for m in matches]
    if not prices:
        return PricePosition(
            our_price=our_price,
            competitors=0,
            min=None,
            median=None,
            max=None,
            vs_min_pct=None,
            vs_median_pct=None,
        )
    lo, mid, hi = (
        min(prices),
        Decimal(median(prices)).quantize(_CENT, rounding=ROUND_HALF_UP),
        max(prices),
    )

    def vs(ref: Decimal) -> Decimal | None:
        if ref <= 0:  # a zero scraped price has no meaningful percentage
            return None
        return ((our_price - ref) / ref * 100).quantize(_ONE_DP, rounding=ROUND_HALF_UP)

    return PricePosition(
        our_price=our_price,
        competitors=len(prices),
        min=lo,
        median=mid,
        max=hi,
        vs_min_pct=vs(lo),
        vs_median_pct=vs(mid),
    )


def _policy_passages(session: Session, sections: list[dict[str, Any]]) -> list[PolicyPassage]:
    """The retrieved policy sections with their text. Prose only: the numbers a recommendation
    acts on never come from here (CLAUDE.md section 6, rule 1)."""
    refs = [str(s["section_ref"]) for s in sections]
    chunks = table("policy_chunks", column("section_ref"), column("heading"), column("text"))
    found = {
        r.section_ref: r
        for r in session.execute(
            select(chunks.c.section_ref, chunks.c.heading, chunks.c.text).where(
                chunks.c.section_ref.in_(refs)
            )
        )
    }
    out = []
    for s in sections:
        ref = str(s["section_ref"])
        chunk = found.get(ref)
        out.append(
            PolicyPassage(
                section_ref=ref,
                similarity=float(s.get("similarity", 0.0)),
                heading=chunk.heading if chunk else None,
                text=chunk.text if chunk else None,
            )
        )
    return out


def _recommendation_out(session: Session, r: Recommendation) -> RecommendationOut:
    return RecommendationOut(
        id=r.id,
        created_at=r.created_at,
        run_label=r.run_label,
        scenario=r.scenario,
        llm_model=r.llm_model,
        proposed_price=r.llm_proposed_price,
        rationale=r.llm_rationale,
        guard_status=r.guard_status,
        guard_final_price=r.guard_final_price,
        guard_reason=r.guard_reason,
        cost=r.cost,
        current_price=r.current_price,
        margin_floor_pct=_pct(_floor_fraction(r.category)),
        proposed_margin_pct=(
            _margin_pct(r.llm_proposed_price, r.cost) if r.llm_proposed_price else None
        ),
        final_margin_pct=_margin_pct(r.guard_final_price, r.cost) if r.guard_final_price else None,
        rag_sections=_policy_passages(session, list(r.rag_sections)),
        competitor_prices=list(r.competitor_prices),
        price_7d_ago=r.price_7d_ago,
        price_7d_ago_source=r.price_7d_ago_source,
        elasticity_placeholder=dict(r.elasticity_placeholder),
        llm_cost_usd=r.llm_cost_usd,
        llm_latency_ms=r.llm_latency_ms,
    )


def _safe_url(url: str) -> str | None:
    """Only http(s) links are rendered as links: the URL comes from a scraped page, and a
    `javascript:` href would run script on the dashboard's origin."""
    return url if urlsplit(url.strip()).scheme.lower() in ("http", "https") else None


def _matches(session: Session, product_id: int) -> list[MatchRow]:
    rows = session.scalars(
        select(ProductMatch)
        .where(ProductMatch.product_id == product_id)
        .order_by(ProductMatch.competitor_price, ProductMatch.source)
    ).all()
    return [
        MatchRow(
            shop=m.source,
            competitor_title=m.competitor_title,
            price=m.competitor_price,
            score=m.score,
            threshold=m.threshold,
            price_date=m.price_date,
            in_stock=m.in_stock,
            url=_safe_url(m.url),
        )
        for m in rows
    ]


def product_detail(session: Session, product_id: int) -> ProductDetail:
    p = session.get(ProductModel, product_id)
    if p is None:
        raise ProductNotFound(product_id)
    matches = _matches(session, product_id)
    rec = _latest_real_recommendations(session).get(product_id)
    stress_rows = session.scalars(
        select(Recommendation)
        .where(
            Recommendation.product_id == product_id,
            Recommendation.is_mock.is_(False),
            Recommendation.scenario.is_not(None),
            Recommendation.run_label.not_like("%superseded%"),
        )
        .order_by(Recommendation.id)
    ).all()
    stress: dict[str, Recommendation] = {r.scenario: r for r in stress_rows if r.scenario}
    floor = _floor_fraction(p.category)
    return ProductDetail(
        product=_product_row(p, len(matches), rec),
        floor_price=(p.purchase_cost / (1 - floor)).quantize(_CENT, rounding=ROUND_CEILING),
        matches=matches,
        position=_position(p.current_price, matches),
        recommendation=_recommendation_out(session, rec) if rec else None,
        stress_tests=[
            StressTest(
                scenario=name,
                proposed_price=r.llm_proposed_price,
                guard_status=r.guard_status,
                guard_final_price=r.guard_final_price,
                guard_reason=r.guard_reason,
            )
            for name, r in stress.items()
        ],
    )


def price_history(session: Session, product_id: int) -> PriceHistory:
    if session.get(ProductModel, product_id) is None:
        raise ProductNotFound(product_id)
    # In-process import: the mock store's generated series, no server needed (the same accessor
    # the decision engine uses). Lazy so importing the API does not build 30 x 180 points.
    from services.mock_store.app import get_history_points

    try:
        points = get_history_points(product_id)
    except KeyError:  # a product the mock store does not know: no synthetic series
        points = []
    ours = [OurPricePoint(day=h.day, price=h.price, units_sold=h.units_sold) for h in points]
    series = []
    for m in session.scalars(select(ProductMatch).where(ProductMatch.product_id == product_id)):
        pts = session.execute(
            select(RawListing.collected_date, RawListing.price)
            .where(RawListing.source == m.source, RawListing.external_id == m.external_id)
            .order_by(RawListing.collected_date)
        ).all()
        series.append(CompetitorSeries(shop=m.source, points=[(d, pr) for d, pr in pts]))
    return PriceHistory(
        product_id=product_id,
        our_price_synthetic=ours,
        our_price_note=HISTORY_NOTE,
        competitors_real=sorted(series, key=lambda s: s.shop),
        competitors_note=COMPETITOR_NOTE,
    )


def _static_status(database: bool) -> Status:
    return Status(
        database=database,
        collection_days=None,
        first_day=None,
        last_day=None,
        in_scope_listings=None,
        price_observations=None,
        listing_counts=None,
        sources=[],
        products=None,
        recommendations_real={},
        matcher=MatcherFacts(
            model=facts.MATCHER_MODEL,
            threshold=None,
            links=0,
            products_with_link=0,
            precision_pre_guard=facts.PRECISION_PRE_GUARD,
            precision_post_guard=facts.PRECISION_POST_GUARD,
            precision_caveat=facts.PRECISION_CAVEAT,
        ),
        phases=[PhaseState(phase=a, state=b) for a, b in facts.PHASES],
        real_vs_simulated=facts.REAL_VS_SIMULATED,
    )


def static_status() -> Status:
    """Everything that does not need the database (used when it is unreachable)."""
    return _static_status(False)


def pipeline_status(session: Session) -> Status:
    in_scope = RawListing.excluded_reason.is_(None)
    first, last, days = session.execute(
        select(
            func.min(RawListing.collected_date),
            func.max(RawListing.collected_date),
            func.count(func.distinct(RawListing.collected_date)),
        )
    ).one()
    observations = session.execute(
        select(func.count()).select_from(RawListing).where(in_scope)
    ).scalar_one()
    distinct_listings = session.execute(
        select(func.count()).select_from(
            select(RawListing.source, RawListing.external_id).where(in_scope).distinct().subquery()
        )
    ).scalar_one()
    per_source = session.execute(
        select(
            RawListing.source,
            func.count(func.distinct(RawListing.external_id)).filter(in_scope),
            func.count().filter(in_scope),
            func.count(func.distinct(RawListing.collected_date)),
        ).group_by(RawListing.source)
    ).all()
    last_runs: dict[str, ScrapeRun] = {}
    for run in session.scalars(select(ScrapeRun).order_by(ScrapeRun.id)):
        last_runs[run.source] = run
    sources = [
        SourceStatus(
            source=src,
            in_scope_listings=n,
            price_observations=obs,
            collection_days=d,
            last_run_status=last_runs[src].status if src in last_runs else None,
            last_run_at=last_runs[src].started_at if src in last_runs else None,
        )
        for src, n, obs, d in sorted(per_source)
    ]
    recs: dict[str, int] = defaultdict(int)
    for r in _latest_real_recommendations(session).values():
        recs[r.guard_status] += 1
    n_links, n_products = session.execute(
        select(func.count(), func.count(func.distinct(ProductMatch.product_id)))
    ).one()
    threshold = session.execute(select(func.max(ProductMatch.threshold))).scalar_one()
    status = _static_status(True)
    status.collection_days = days
    status.first_day = first
    status.last_day = last
    status.in_scope_listings = distinct_listings
    status.price_observations = observations
    status.listing_counts = _listing_counts(session, observations, distinct_listings)
    status.sources = sources
    status.products = session.execute(select(func.count()).select_from(ProductModel)).scalar_one()
    status.recommendations_real = dict(sorted(recs.items()))
    status.matcher.threshold = threshold
    status.matcher.links = n_links
    status.matcher.products_with_link = n_products
    return status


# Phase 1 closed on the first two collection days' data (ADR-0025: 18,703 stored -> 18,585 in scope).
GATE_WINDOW_DAYS = 2


def _listing_counts(session: Session, now_rows: int, now_distinct: int) -> ListingCounts:
    days = session.scalars(
        select(RawListing.collected_date)
        .distinct()
        .order_by(RawListing.collected_date)
        .limit(GATE_WINDOW_DAYS)
    ).all()
    through = days[-1] if days else None
    in_window = RawListing.collected_date <= through if through else RawListing.id < 0
    in_scope = RawListing.excluded_reason.is_(None)
    stored = session.execute(
        select(func.count()).select_from(RawListing).where(in_window)
    ).scalar_one()
    rows = session.execute(
        select(func.count()).select_from(RawListing).where(in_window, in_scope)
    ).scalar_one()
    distinct = session.execute(
        select(func.count()).select_from(
            select(RawListing.source, RawListing.external_id)
            .where(in_window, in_scope)
            .distinct()
            .subquery()
        )
    ).scalar_one()
    return ListingCounts(
        window_days=len(days),
        window_through=through,
        window_rows_stored=stored,
        window_rows_in_scope=rows,
        window_distinct_listings=distinct,
        now_rows_in_scope=now_rows,
        now_distinct_listings=now_distinct,
    )


def _decision_audit(session: Session) -> DecisionAudit:
    """Every real, non-superseded recommendation, re-checked here against the policy floor from the
    stored cost / final price / category -- independent of the guard's own verdict."""
    rows = session.scalars(
        select(Recommendation).where(
            Recommendation.is_mock.is_(False), Recommendation.run_label != SUPERSEDED_RUN_LABEL
        )
    ).all()
    counts: dict[str, int] = defaultdict(int)
    violations = 0
    for r in rows:
        counts[r.guard_status] += 1
        if r.guard_status == "APPROVE" and r.guard_final_price is not None:
            try:
                ok = meets_floor(r.category, r.guard_final_price, r.cost)
            except ValueError:
                ok = False  # corrupt input counts against us, not for us
            violations += 0 if ok else 1
    return DecisionAudit(
        recommendations=len(rows),
        approve=counts["APPROVE"],
        flag=counts["FLAG"],
        reject=counts["REJECT"],
        margin_violations=violations,
    )


def _verdict_mix(session: Session) -> list[VerdictMixRow]:
    rows = session.execute(
        select(Recommendation.scenario, Recommendation.guard_status, func.count())
        .where(Recommendation.is_mock.is_(False), Recommendation.run_label != SUPERSEDED_RUN_LABEL)
        .group_by(Recommendation.scenario, Recommendation.guard_status)
    ).all()
    mix: dict[str, dict[str, int]] = {}
    for scenario, status, n in rows:
        mix.setdefault(scenario or "baseline", {})[status] = n
    order = sorted(mix, key=lambda g: (g != "baseline", g))  # real inputs first
    return [
        VerdictMixRow(
            group=g,
            approve=mix[g].get("APPROVE", 0),
            flag=mix[g].get("FLAG", 0),
            reject=mix[g].get("REJECT", 0),
        )
        for g in order
    ]


def _category_margins(session: Session) -> list[CategoryMargin]:
    by_cat: dict[str, list[Decimal]] = defaultdict(list)
    for p in session.scalars(select(ProductModel)):
        m = _margin_pct(p.current_price, p.purchase_cost)
        if m is not None:
            by_cat[p.category].append(m)
    return [
        CategoryMargin(
            category=cat,
            products=len(ms),
            avg_margin_pct=(sum(ms, Decimal(0)) / len(ms)).quantize(
                _ONE_DP, rounding=ROUND_HALF_UP
            ),
            min_margin_pct=min(ms),
            floor_pct=_pct(_floor_fraction(cat)),
        )
        for cat, ms in sorted(by_cat.items())
    ]


def _overview_base(database: bool) -> Overview:
    matcher = results.matcher_result()
    rag = results.rag_result()
    return Overview(
        database=database,
        matcher_result=matcher.model_dump() if matcher else None,
        rag_result=rag.model_dump() if rag else None,
        products=None,
        products_matched=None,
        match_links=None,
        match_shops=None,
        matcher_threshold=None,
        precision_post_guard=facts.PRECISION_POST_GUARD,
        precision_caveat=facts.PRECISION_CAVEAT,
        collection_days=None,
        price_rows=None,
        sources=None,
        audit=None,
        verdict_mix=[],
        category_margins=[],
    )


def static_overview() -> Overview:
    """The committed-results half of the overview (no database needed)."""
    return _overview_base(False)


def overview(session: Session) -> Overview:
    o = _overview_base(True)
    o.products = session.execute(select(func.count()).select_from(ProductModel)).scalar_one()
    links, matched, shops = session.execute(
        select(
            func.count(),
            func.count(func.distinct(ProductMatch.product_id)),
            func.count(func.distinct(ProductMatch.source)),
        )
    ).one()
    o.match_links, o.products_matched, o.match_shops = links, matched, shops
    o.matcher_threshold = session.execute(select(func.max(ProductMatch.threshold))).scalar_one()
    days, rows, sources = session.execute(
        select(
            func.count(func.distinct(RawListing.collected_date)),
            func.count(),
            func.count(func.distinct(RawListing.source)),
        ).where(RawListing.excluded_reason.is_(None))
    ).one()
    o.collection_days, o.price_rows, o.sources = days, rows, sources
    o.audit = _decision_audit(session)
    o.verdict_mix = _verdict_mix(session)
    o.category_margins = _category_margins(session)
    return o
