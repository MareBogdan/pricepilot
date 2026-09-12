"""The ONLY module in this codebase permitted to call an LLM provider (CLAUDE.md §5.4).

ruff bans importing `anthropic` / `openai` anywhere else (see pyproject.toml), so this is
enforced by CI rather than by memory.

Phase 0 ships the *guard rails* only — the budget cap, the cache key, and the call log.
The transport is deliberately not implemented yet: the first paid call happens in Phase 2
and must be preceded by a `SPEND:` approval (CLAUDE.md §5). Per-token prices are not
hardcoded here because no number in this repo may be invented (CLAUDE.md §0.4); they are
filled in from the provider's published price list in the same commit as the first call.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select

from pricepilot.config import get_settings
from pricepilot.db import session_scope
from pricepilot.models import LlmCall


class BudgetExceeded(RuntimeError):
    """Raised when a call would push spend past LLM_BUDGET_USD.

    CLAUDE.md §5.5: on exceeding the cap we raise. We never silently fall back to a
    cheaper model or skip the call, because silent degradation makes the resulting
    metrics unexplainable.
    """


@dataclass(frozen=True)
class Usage:
    model: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    cost_usd: Decimal


def cache_key(*parts: str) -> str:
    """Stable content hash for a request.

    Phase 2 keys attribute extraction on the *normalized title* alone. The price changes
    daily and the title almost never does, so keying on anything price-dependent would
    multiply cost by the number of days collected — the single largest cost risk in the
    project (CLAUDE.md §5).
    """
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")  # separator, so ("ab","c") != ("a","bc")
    return digest.hexdigest()


def spend_to_date() -> Decimal:
    """Total USD spent across every logged call. Backs `make cost`."""
    with session_scope() as session:
        rows = session.execute(select(LlmCall.cost_usd)).scalars().all()
    return sum(rows, Decimal("0"))


def assert_within_budget(estimated_cost_usd: Decimal) -> None:
    """Call before every request. Raises BudgetExceeded rather than degrading."""
    budget = Decimal(str(get_settings().llm_budget_usd))
    spent = spend_to_date()
    if spent + estimated_cost_usd > budget:
        raise BudgetExceeded(
            f"Call would cost ~${estimated_cost_usd} on top of ${spent} already spent, "
            f"exceeding LLM_BUDGET_USD=${budget}."
        )


def log_call(
    *,
    phase: str,
    purpose: str,
    usage: Usage,
    key: str | None = None,
    cache_hit: bool = False,
    latency_ms: int | None = None,
) -> None:
    """Persist one call to `llm_calls`. Cache hits are logged with cost 0 so that
    `make cost` can show what caching actually saved, not just what was spent."""
    with session_scope() as session:
        session.add(
            LlmCall(
                phase=phase,
                purpose=purpose,
                model=usage.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_input_tokens=usage.cached_input_tokens,
                cost_usd=usage.cost_usd,
                cache_key=key,
                cache_hit=cache_hit,
                latency_ms=latency_ms,
            )
        )


def complete(*_args: object, **_kwargs: object) -> str:
    """Transport. Implemented in Phase 2, behind an explicit SPEND approval."""
    raise NotImplementedError(
        "No LLM transport before Phase 2. Phases 0, 1 and 4 must cost $0 (CLAUDE.md §5)."
    )
