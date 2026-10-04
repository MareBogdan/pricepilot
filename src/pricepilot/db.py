"""Database engine and session factory.

STEP 3 (session note 2026-09-12): Neon suspends compute after 5 minutes idle, so the first
connection of the day pays a wake-up — the proxy holds the socket open until compute resumes
rather than refusing it, but that can take several seconds, longer than a default connect
timeout tolerates. `NEON_CONNECT_TIMEOUT_SECONDS` gives the wake-up room to finish;
`connect_with_wakeup_retry` covers the rest by retrying exactly once on a connection failure,
so a scheduled run does not fail for no reason on the one connection of the day most likely
to hit a cold start.
"""

from __future__ import annotations

import os
import ssl
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from pricepilot.config import get_settings

_engine: Engine | None = None

# Generous but not unbounded: Neon's own guidance is a cold start usually resolves in a few
# seconds. 15s comfortably covers it without a hung connection blocking a scheduled run forever.
NEON_CONNECT_TIMEOUT_SECONDS = 15
# One retry, no long backoff — the timeout above already waited out the wake-up once; a second
# consecutive failure is a real problem (network, credentials, Neon actually down), not a cold
# start, and should surface rather than be retried away.
NEON_WAKEUP_RETRY_DELAY_SECONDS = 2.0


# Fallback driver for machines where psycopg's libpq DLL is blocked by Application Control
# (ADR-0038). Opt-in: `PRICEPILOT_DB_DRIVER=pg8000`. The `.env` value is never edited.
DB_DRIVER_ENV = "PRICEPILOT_DB_DRIVER"
# pg8000's `timeout` is a socket timeout that stays on the connection for its whole life (psycopg's
# `connect_timeout` covers connection setup only), so it must also outlast the slowest query --
# not just a Neon cold start.
PG8000_SOCKET_TIMEOUT_SECONDS = 120


def resolve_database_target(raw_url: str) -> tuple[str, dict[str, Any]]:
    """The (url, connect_args) to hand to SQLAlchemy for `raw_url`.

    Default: the URL unchanged plus psycopg's `connect_timeout`. With
    `PRICEPILOT_DB_DRIVER=pg8000` the driver is swapped and the libpq-only query params
    (`sslmode`, `channel_binding`) are translated: pg8000 rejects them and instead wants an
    explicit `ssl_context` and `timeout`.
    """
    if os.environ.get(DB_DRIVER_ENV, "").lower() != "pg8000":
        return raw_url, {"connect_timeout": NEON_CONNECT_TIMEOUT_SECONDS}
    url = make_url(raw_url).set(drivername="postgresql+pg8000")
    sslmode = url.query.get("sslmode", "")
    url = url.difference_update_query(["sslmode", "channel_binding"])
    args: dict[str, Any] = {"timeout": PG8000_SOCKET_TIMEOUT_SECONDS}
    if sslmode in ("require", "verify-ca", "verify-full"):
        args["ssl_context"] = ssl.create_default_context()
    return url.render_as_string(hide_password=False), args


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url, connect_args = resolve_database_target(get_settings().database_url)
        _engine = create_engine(url, pool_pre_ping=True, future=True, connect_args=connect_args)
    return _engine


def connect_with_wakeup_retry(engine: Engine) -> Connection:
    """`engine.connect()`, tolerating a Neon cold-start wake-up with one retry.

    Used everywhere a *new* connection is opened against the collected-data database:
    `check_database()`, Alembic's `env.py`, and the daily scrape's first query. Not needed
    inside `session_scope` — SQLAlchemy's pool already owns connection reuse there, and
    `pool_pre_ping` covers a connection that went stale mid-session.
    """
    try:
        return engine.connect()
    except (OperationalError, InterfaceError):  # pg8000 reports connect failures as InterfaceError
        time.sleep(NEON_WAKEUP_RETRY_DELAY_SECONDS)
        return engine.connect()


def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope. Commits on success, rolls back on any exception."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database() -> bool:
    """True if the database answers. Used by /health and by `make status`,
    both of which must degrade gracefully rather than crash when Postgres is down."""
    try:
        with connect_with_wakeup_retry(get_engine()) as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
