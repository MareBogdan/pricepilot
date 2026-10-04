"""`resolve_database_target`: the default psycopg path is untouched; pg8000 is translated (ADR-0038)."""

from __future__ import annotations

import ssl

import pytest

from pricepilot.db import DB_DRIVER_ENV, NEON_CONNECT_TIMEOUT_SECONDS, resolve_database_target

NEON = "postgresql+psycopg://u:p%40ss@host.example/db?sslmode=require&channel_binding=require"


def test_default_path_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DB_DRIVER_ENV, raising=False)
    assert resolve_database_target(NEON) == (
        NEON,
        {"connect_timeout": NEON_CONNECT_TIMEOUT_SECONDS},
    )


def test_pg8000_swaps_driver_and_translates_libpq_params(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DB_DRIVER_ENV, "pg8000")
    url, args = resolve_database_target(NEON)
    assert url == "postgresql+pg8000://u:p%40ss@host.example/db"  # password kept, params gone
    assert isinstance(args["ssl_context"], ssl.SSLContext)
    assert "connect_timeout" not in args and args["timeout"] > NEON_CONNECT_TIMEOUT_SECONDS


def test_pg8000_without_sslmode_gets_no_tls_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DB_DRIVER_ENV, "pg8000")
    _, args = resolve_database_target("postgresql+psycopg://u:p@localhost:5433/db")
    assert "ssl_context" not in args
