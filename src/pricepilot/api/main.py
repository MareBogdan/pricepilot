"""Main FastAPI application. Phase 0 ships /health only; the dashboard API arrives in Phase 7."""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from pricepilot import __version__
from pricepilot.config import get_settings
from pricepilot.db import check_database

app = FastAPI(title="PricePilot", version=__version__)


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
