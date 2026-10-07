"""Request dependencies for the read-only dashboard API."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import Connection
from sqlalchemy.orm import Session

from pricepilot.db import connect_with_wakeup_retry, get_engine

log = logging.getLogger(__name__)


class DatabaseUnavailable(Exception):
    """The database could not be reached. Mapped to a 503 (JSON or HTML), never a crash."""


def _connect() -> Connection:
    try:
        return connect_with_wakeup_retry(get_engine())
    except Exception as exc:  # driver errors vary (pg8000 / psycopg / DNS): all mean "down"
        log.warning("database unreachable: %s", type(exc).__name__)
        raise DatabaseUnavailable from exc


def get_session() -> Iterator[Session]:
    """One read-only unit of work per request. The connection goes through the Neon cold-start
    retry (the first request of the day pays the wake-up); nothing here ever commits."""
    with _connect() as conn, Session(bind=conn) as session:
        yield session
        session.rollback()


def get_optional_session() -> Iterator[Session | None]:
    """Like `get_session`, but yields None when the database is down (for endpoints that can
    still say something useful without it)."""
    try:
        conn = _connect()
    except DatabaseUnavailable:
        yield None
        return
    with conn, Session(bind=conn) as session:
        yield session
        session.rollback()
