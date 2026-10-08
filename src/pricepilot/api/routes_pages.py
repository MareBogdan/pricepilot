"""Server-rendered dashboard pages. Read-only: no forms, no write actions (Phase 6's apply stays a
CLI). Every figure shown is computed in `queries.py`."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pricepilot.api import facts, queries
from pricepilot.api.anonymise import shop_label
from pricepilot.api.deps import get_optional_session
from pricepilot.api.schemas import Overview, ProductDetail, Status

log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _money(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{value:,.2f}"


def _pct(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{value:.1f}%"


def _signed_pct(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{value:+.1f}%"


def _day(value: date | datetime | None) -> str:
    return "n/a" if value is None else value.strftime("%Y-%m-%d")


def _shop(value: str) -> str:
    """`shop_c` -> `Shop C` (the public alias; real names never reach a page)."""
    return shop_label(value)


def _fixed(value: Decimal | None, places: int) -> str:
    """Fixed decimals, formatted on the Decimal itself (never through float)."""
    return "n/a" if value is None else f"{value:.{places}f}"


templates.env.filters.update(
    money=_money, pct=_pct, signed_pct=_signed_pct, day=_day, shop=_shop, fixed=_fixed
)

templates.env.globals["gate_figure"] = facts.PHASE1_GATE_ROWS
templates.env.globals["gate_min"] = facts.PHASE1_GATE_MIN_LISTINGS

router = APIRouter(include_in_schema=False)
OptionalSessionDep = Annotated[Session | None, Depends(get_optional_session)]


def _render(request: Request, name: str, status_code: int = 200, **ctx: Any) -> HTMLResponse:
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _unavailable(request: Request) -> HTMLResponse:
    return _render(request, "unavailable.html", status_code=503, page="")


GROUP_LABELS = {
    "baseline": "Real inputs",
    "stress_undercut_15": "Competitors cut 15% (stress)",
    "stress_undercut_30": "Competitors cut 30% (stress)",
}


def overview_chart_data(o: Overview) -> dict[str, Any]:
    """Chart payloads. Numbers stay strings (Decimal) until the browser plots them."""
    return {
        "verdict": [
            {
                "label": f"{GROUP_LABELS.get(r.group, r.group.replace('_', ' '))} ({r.approve + r.flag + r.reject})",
                "approve": r.approve,
                "flag": r.flag,
                "reject": r.reject,
            }
            for r in o.verdict_mix
        ],
        "margins": [
            {
                "label": f"{c.category.replace('_', ' ')} ({c.products})",
                "avg": str(c.avg_margin_pct),
                "floor": str(c.floor_pct),
            }
            for c in o.category_margins
        ],
    }


def comparison_bars(d: ProductDetail) -> list[dict[str, str]]:
    """Our price, each matched competitor price, and the guard-approved price (if any)."""
    bars = [{"label": "Our price", "price": str(d.product.current_price), "kind": "ours"}]
    bars += [
        {"label": _shop(m.shop), "price": str(m.price), "kind": "shop", "shop": m.shop}
        for m in d.matches
    ]
    rec = d.recommendation
    if rec and rec.guard_status == "APPROVE" and rec.guard_final_price is not None:
        bars.append({"label": "Recommended", "price": str(rec.guard_final_price), "kind": "rec"})
    return bars


@router.get("/", response_class=HTMLResponse)
def products_page(request: Request, session: OptionalSessionDep) -> HTMLResponse:
    if session is None:
        return _unavailable(request)
    try:
        rows = queries.list_products(session)
        o = queries.overview(session)
    except SQLAlchemyError:
        log.warning("products page: query failed", exc_info=True)
        return _unavailable(request)
    return _render(
        request,
        "products.html",
        page="products",
        products=rows,
        o=o,
        chart_data=overview_chart_data(o),
        stress_n=sum(r.approve + r.flag + r.reject for r in o.verdict_mix if r.group != "baseline"),
    )


@router.get("/products/{product_id}", response_class=HTMLResponse)
def product_page(request: Request, product_id: int, session: OptionalSessionDep) -> HTMLResponse:
    if session is None:
        return _unavailable(request)
    try:
        detail = queries.product_detail(session, product_id)
    except queries.ProductNotFound:
        return _render(request, "not_found.html", status_code=404, page="")
    except SQLAlchemyError:
        log.warning("product page: query failed", exc_info=True)
        return _unavailable(request)
    return _render(request, "product.html", page="products", d=detail, bars=comparison_bars(detail))


@router.get("/status", response_class=HTMLResponse)
def status_page(request: Request, session: OptionalSessionDep) -> HTMLResponse:
    st: Status | None = None
    if session is not None:
        try:
            st = queries.pipeline_status(session)
        except SQLAlchemyError:
            log.warning("status page: query failed", exc_info=True)
    return _render(request, "status.html", page="status", s=st or queries.static_status())
