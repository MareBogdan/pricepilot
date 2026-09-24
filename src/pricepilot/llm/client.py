"""The ONLY module in this codebase permitted to call an LLM provider (CLAUDE.md §5.4).

ruff bans importing `anthropic` / `openai` anywhere else (see pyproject.toml), so this is
enforced by CI rather than by memory.

The guard rails are the budget cap, the cache key and the call log; `complete()` is the
transport that uses all three. Every paid call is preceded by a `SPEND:` approval (CLAUDE.md §5).
Per-token prices below are copied from the provider's published price list
(docs/phase3-serving-prices.md, retrieved 2026-09-23) -- no number here is invented (§0.4).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select

from pricepilot.config import get_settings
from pricepilot.db import session_scope
from pricepilot.models import LlmCall

# USD per million tokens (input, output). Source: https://platform.claude.com/docs/en/about-claude/pricing
# retrieved 2026-09-23, recorded in docs/phase3-serving-prices.md. A model missing from this table
# cannot be called: we never guess a price.
PRICES_USD_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "claude-sonnet-5": (Decimal("2"), Decimal("10")),
    "claude-haiku-4-5-20251001": (Decimal("1"), Decimal("5")),
}

# Content-addressed response cache. `data/` is gitignored, so cached model output never enters git.
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "llm-cache"


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


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Cost from the published per-token prices. Raises for a model without a recorded price."""
    if model not in PRICES_USD_PER_MTOK:
        raise KeyError(f"no published price recorded for model {model!r}; refusing to guess one")
    price_in, price_out = PRICES_USD_PER_MTOK[model]
    return (price_in * input_tokens + price_out * output_tokens) / Decimal(1_000_000)


def make_sdk_client() -> Any:
    """The one place the SDK client is built. Callers making many calls should build it ONCE and
    pass it to `complete`, so per-call latency is not inflated by a new TLS handshake each time."""
    import anthropic  # the ONLY module allowed to import the SDK (ruff TID251 enforces it)

    api_key = get_settings().anthropic_api_key
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in .env; cannot make a paid call")
    # max_retries=0: the SDK's silent retries could bill a response twice while writing one log
    # row, and would hide inside the measured latency. A failed call raises loudly.
    return anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=60.0)


@dataclass(frozen=True)
class Completion:
    text: str
    usage: Usage
    cache_hit: bool
    latency_ms: float | None  # wall-clock of the API call; None for a cache hit
    # Protocol 5.12: v1's hosted run threw this information away (only `.text` survived), which is
    # exactly what made session 2's empty-reply diagnosis wrong -- it had no way to tell a
    # truncated non-text reply from a genuinely empty one. Carried on EVERY call, cache hit or
    # not, so it is never lost again. `None`/`[]` on a cache entry written before this field
    # existed (a v1 call cached under the old format) -- backward compatible, not a new call.
    stop_reason: str | None = None
    block_types: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ContentBlock:
    type: str
    text: str | None


@dataclass(frozen=True)
class DiagnosticCompletion:
    stop_reason: str | None
    blocks: list[ContentBlock]
    usage: Usage
    latency_ms: float


def complete(
    *,
    model: str,
    prompt: str,
    max_tokens: int,
    phase: str,
    purpose: str,
    temperature: float | None = None,
    system: str | None = None,
    estimated_input_tokens: int | None = None,
    sdk_client: Any | None = None,
    cache_dir: Path | None = None,
) -> Completion:
    """The only path to a paid LLM call.

    1. cache lookup by content hash -- a hit costs 0, is logged as a hit, and never calls the API;
    2. `assert_within_budget` BEFORE the call -- raises `BudgetExceeded`, never degrades;
    3. the call; 4. cache write (so a crash while logging cannot cause a second paid call);
    5. `log_call` with model, tokens, cost and latency.
    """
    cache_root = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR
    key = cache_key(model, str(max_tokens), repr(temperature), system or "", prompt)
    cache_path = cache_root / f"{key}.json"

    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        usage = Usage(
            model=model,
            input_tokens=cached["input_tokens"],
            output_tokens=cached["output_tokens"],
            cached_input_tokens=0,
            cost_usd=Decimal("0"),
        )
        log_call(phase=phase, purpose=purpose, usage=usage, key=key, cache_hit=True)
        return Completion(
            text=cached["text"],
            usage=usage,
            cache_hit=True,
            latency_ms=None,
            stop_reason=cached.get("stop_reason"),
            block_types=cached.get("block_types", []),
        )

    # Pessimistic pre-call estimate: caller's token estimate (else ~1 token per 3 characters) plus
    # the full max_tokens of output.
    est_input = (
        estimated_input_tokens if estimated_input_tokens is not None else len(prompt) // 3 + 1
    )
    assert_within_budget(cost_usd(model, est_input, max_tokens))

    if sdk_client is None:
        sdk_client = make_sdk_client()

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if temperature is not None:
        # anthropic 1.8.0's create() has no `temperature` parameter, so it goes in the body.
        # claude-sonnet-5's API rejects it (400 "`temperature` is deprecated for this model"),
        # so the item-8 hosted run passes None -- a recorded deviation from protocol 5.7.
        kwargs["extra_body"] = {"temperature": temperature}
    if system is not None:
        kwargs["system"] = system
    started = time.perf_counter()
    response = sdk_client.messages.create(**kwargs)
    latency_ms = (time.perf_counter() - started) * 1000.0

    text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
    stop_reason = getattr(response, "stop_reason", None)
    block_types = [getattr(b, "type", "?") for b in response.content]
    in_tok, out_tok = int(response.usage.input_tokens), int(response.usage.output_tokens)
    usage = Usage(
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cached_input_tokens=0,
        cost_usd=cost_usd(model, in_tok, out_tok),
    )
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "text": text,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "stop_reason": stop_reason,
                "block_types": block_types,
            }
        ),
        encoding="utf-8",
    )
    try:
        log_call(
            phase=phase,
            purpose=purpose,
            usage=usage,
            key=key,
            cache_hit=False,
            latency_ms=round(latency_ms),
        )
    except Exception as e:
        # Money was spent and is NOT in llm_calls: say so loudly instead of leaving a silent gap.
        raise RuntimeError(
            f"PAID CALL NOT LOGGED (${usage.cost_usd}, key {key}): {e!r}. The response is cached, "
            "so a rerun will not pay again -- add this cost to docs/COSTS.md by hand."
        ) from e
    return Completion(
        text=text,
        usage=usage,
        cache_hit=False,
        latency_ms=latency_ms,
        stop_reason=stop_reason,
        block_types=block_types,
    )


def complete_diagnostic(
    *,
    model: str,
    prompt: str,
    max_tokens: int,
    phase: str,
    purpose: str,
    temperature: float | None = None,
    system: str | None = None,
    sdk_client: Any | None = None,
) -> DiagnosticCompletion:
    """A second, narrower path to a paid call, for diagnosing a reply `complete()` would score as
    empty. `complete()` only ever returns `.text` -- the concatenation of "text"-type content
    blocks -- so it cannot show WHY a reply came back empty: a non-text block type, or a "text"
    block truncated by `stop_reason="max_tokens"` before any visible token. This returns the raw
    `stop_reason` and every block's type/text instead.

    Same budget check and `log_call` as `complete()`, so it is still capped and still traced in
    `llm_calls`. Deliberately has NO disk cache: this is a one-off diagnostic call meant to run
    once, not a scoring path meant to be replayed for free on a second run.
    """
    est_input = len(prompt) // 3 + 1
    assert_within_budget(cost_usd(model, est_input, max_tokens))

    if sdk_client is None:
        sdk_client = make_sdk_client()

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if temperature is not None:
        kwargs["extra_body"] = {"temperature": temperature}
    if system is not None:
        kwargs["system"] = system
    started = time.perf_counter()
    response = sdk_client.messages.create(**kwargs)
    latency_ms = (time.perf_counter() - started) * 1000.0

    blocks = [
        ContentBlock(type=getattr(b, "type", "?"), text=getattr(b, "text", None))
        for b in response.content
    ]
    in_tok, out_tok = int(response.usage.input_tokens), int(response.usage.output_tokens)
    usage = Usage(
        model=model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cached_input_tokens=0,
        cost_usd=cost_usd(model, in_tok, out_tok),
    )
    log_call(
        phase=phase,
        purpose=purpose,
        usage=usage,
        key=None,
        cache_hit=False,
        latency_ms=round(latency_ms),
    )
    return DiagnosticCompletion(
        stop_reason=getattr(response, "stop_reason", None),
        blocks=blocks,
        usage=usage,
        latency_ms=latency_ms,
    )
