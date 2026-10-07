"""JSON endpoints under /api -- read-only, numbers from SQL (see `queries.py`)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pricepilot.api import queries
from pricepilot.api.deps import get_optional_session, get_session
from pricepilot.api.schemas import PriceHistory, ProductDetail, ProductRow, Status

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["dashboard"])

SessionDep = Annotated[Session, Depends(get_session)]
OptionalSessionDep = Annotated[Session | None, Depends(get_optional_session)]


@router.get("/products", response_model=list[ProductRow])
def products(session: SessionDep) -> list[ProductRow]:
    return queries.list_products(session)


@router.get("/products/{product_id}", response_model=ProductDetail)
def product(product_id: int, session: SessionDep) -> ProductDetail:
    try:
        return queries.product_detail(session, product_id)
    except queries.ProductNotFound:
        raise HTTPException(status_code=404, detail="product not found") from None


@router.get("/products/{product_id}/history", response_model=PriceHistory)
def history(product_id: int, session: SessionDep) -> PriceHistory:
    try:
        return queries.price_history(session, product_id)
    except queries.ProductNotFound:
        raise HTTPException(status_code=404, detail="product not found") from None


@router.get("/status", response_model=Status)
def status(session: OptionalSessionDep) -> Status:
    """Pipeline facts. Degrades instead of failing: with the database unreachable it still
    returns the documented (static) facts and `database: false`."""
    if session is not None:
        try:
            return queries.pipeline_status(session)
        except SQLAlchemyError:
            log.warning("status: database query failed, serving static facts", exc_info=True)
    return queries.static_status()
