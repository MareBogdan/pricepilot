"""Main FastAPI application: /health, the read-only JSON API under /api, and the dashboard pages."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from pricepilot import __version__
from pricepilot.api.deps import DatabaseUnavailable
from pricepilot.api.routes_api import router as api_router
from pricepilot.api.routes_pages import router as pages_router
from pricepilot.config import get_settings
from pricepilot.db import check_database

app = FastAPI(title="PricePilot", version=__version__)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(api_router)
app.include_router(pages_router)


@app.exception_handler(DatabaseUnavailable)
@app.exception_handler(SQLAlchemyError)
def database_down(_request: Request, _exc: Exception) -> Response:
    """The database is down or a query failed: say so with a 503, never a stack trace."""
    return JSONResponse(status_code=503, content={"detail": "database unavailable"})


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    env: str
    database: bool


@app.get("/health", response_model=Health)
def health() -> Health:
    """Liveness + dependency check.

    Returns 200 with status="degraded" when Postgres is unreachable rather than failing,
    so a container orchestrator can distinguish "app is up, DB is not" from "app is dead".
    """
    db_ok = check_database()
    settings = get_settings()
    return Health(
        status="ok" if db_ok else "degraded",
        version=__version__,
        env=settings.app_env,
        database=db_ok,
    )
