"""Configuration and cost-discipline guards."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from pricepilot.config import Settings
from pricepilot.llm.client import cache_key, complete

ROOT = Path(__file__).resolve().parents[1]


def test_settings_defaults_are_safe() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    # CLAUDE.md §5.4: minimum 2 seconds between requests.
    assert s.scraper_min_delay_seconds >= 2.0
    assert s.scraper_max_delay_seconds >= s.scraper_min_delay_seconds
    # §5.2: scrapers default to a small limit; full runs must be explicit.
    assert s.scraper_default_limit <= 5
    assert s.llm_budget_usd >= 0


def test_no_llm_transport_before_phase_2() -> None:
    """Phases 0, 1 and 4 must cost $0 (CLAUDE.md §5). The transport does not exist yet."""
    with pytest.raises(NotImplementedError):
        complete("anything")


def test_cache_key_is_stable_and_unambiguous() -> None:
    assert cache_key("orijen 1.8 kg") == cache_key("orijen 1.8 kg")
    assert cache_key("orijen 1.8 kg") != cache_key("orijen 4.5 kg")
    # The separator must prevent ("ab","c") colliding with ("a","bc").
    assert cache_key("ab", "c") != cache_key("a", "bc")


def test_env_file_is_not_committed() -> None:
    """CLAUDE.md §0.5 — secrets live in .env only, and .env is never in the repo."""
    assert not (ROOT / ".env").exists() or ".env" in (ROOT / ".gitignore").read_text()
    assert (ROOT / ".env.example").exists()


def test_env_example_has_no_real_secret() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("ANTHROPIC_API_KEY"):
            assert line.strip() == "ANTHROPIC_API_KEY="


def test_no_direct_sdk_import_outside_client() -> None:
    """CLAUDE.md §9 — ruff enforces this in CI; this test enforces it for humans too."""
    allowed = (ROOT / "src" / "pricepilot" / "llm" / "client.py").resolve()
    for path in list((ROOT / "src").rglob("*.py")) + list((ROOT / "services").rglob("*.py")):
        if path.resolve() == allowed:
            continue
        text = path.read_text(encoding="utf-8")
        assert "import anthropic" not in text, path
        assert "import openai" not in text, path


def test_money_is_never_float_in_models() -> None:
    """Margin comparisons on floats are a real bug (CLAUDE.md §6.2)."""
    from sqlalchemy import Numeric

    from pricepilot.models import LlmCall, Product, RawListing

    for column in (
        Product.__table__.c.purchase_cost,
        Product.__table__.c.current_price,
        RawListing.__table__.c.price,
        RawListing.__table__.c.compare_at_price,
        LlmCall.__table__.c.cost_usd,
    ):
        assert isinstance(column.type, Numeric), column
        assert column.type.asdecimal is True, column
    # ...because this is the property a float silently loses.
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")
