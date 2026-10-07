"""The proposer seam (ADR-0042): everything between "a prompt is built" and "a reply comes back".

The engine builds the prompt and parses the reply; only this step differs between sessions:

* `MockProposer` (session 4) -- deterministic, no network, no `llm_calls` row, $0.
* `LlmProposer` (session 5) -- a thin wrapper over `pricepilot.llm.client.complete`, the one module
  allowed to call a provider (CLAUDE.md section 5.4). It is NOT instantiated by any session-4 code.

Both return the same `RawReply`, in the reply format `engine.parse_reply` enforces, so the parser
and the prompt are exercised for real by the mock.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pricepilot.decision.engine import ProductSnapshot

MOCK_MODEL = "mock"
_CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class ProposalRequest:
    system: str
    prompt: str
    # The structured inputs behind the prompt. The real LLM proposer ignores this (it only sees the
    # prompt text); the mock proposer needs it to compute a deterministic answer.
    snapshot: ProductSnapshot


@dataclass(frozen=True, slots=True)
class RawReply:
    text: str
    model: str
    cost_usd: Decimal
    latency_ms: int | None


class Proposer(Protocol):
    # TRUE only for proposers that cost nothing and never reach a provider. Read by the engine to
    # stamp `recommendations.is_mock`, so a mock row can never be counted toward the Phase 5 gate.
    is_mock: bool

    def __call__(self, request: ProposalRequest) -> RawReply: ...


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _reply(price: Decimal, rationale: str) -> str:
    return f"PRICE: {_q(price)}\nRATIONALE: {rationale}"


def _keep(s: ProductSnapshot) -> str:
    return _reply(
        s.current_price, "Keeping the current price; nothing in the inputs justifies a move."
    )


def _toward_cheapest(s: ProductSnapshot) -> str:
    """Move at most 3% of the current price toward the cheapest in-stock matched competitor, never
    past it. No matched competitor -> keep the price (policy: doing nothing is always acceptable)."""
    prices = [c.price for c in s.competitors if c.in_stock is not False]
    if not prices:
        return _keep(s)
    target = min(prices)
    step = s.current_price * Decimal("0.03")
    delta = target - s.current_price
    move = max(-step, min(step, delta))
    return _reply(
        s.current_price + move,
        f"Moving toward the cheapest matched competitor ({target} RON), limited to a 3% step.",
    )


def _below_floor(s: ProductSnapshot) -> str:
    """A deliberately bad proposal: 5% over cost, i.e. a margin of ~4.8% -- below every category
    floor. The guard, not this mock, must stop it."""
    return _reply(s.cost * Decimal("1.05"), "Undercut hard to win the sale.")


def _discount_3pct(s: ProductSnapshot) -> str:
    return _reply(s.current_price * Decimal("0.97"), "A small discount to move stock.")


def _malformed(s: ProductSnapshot) -> str:
    return "I think the price should be around twelve lei, give or take."


MOCK_STRATEGIES: dict[str, Callable[[ProductSnapshot], str]] = {
    "toward_cheapest": _toward_cheapest,
    "keep": _keep,
    "below_floor": _below_floor,
    "discount_3pct": _discount_3pct,
    "malformed": _malformed,
}


class MockProposer:
    """Deterministic stand-in for the LLM: no network, no `llm_calls` row, cost 0."""

    is_mock = True

    def __init__(self, strategy: str = "toward_cheapest") -> None:
        if strategy not in MOCK_STRATEGIES:
            raise ValueError(
                f"unknown mock strategy {strategy!r}; choose from {sorted(MOCK_STRATEGIES)}"
            )
        self.strategy = strategy

    def __call__(self, request: ProposalRequest) -> RawReply:
        text = MOCK_STRATEGIES[self.strategy](request.snapshot)
        return RawReply(text=text, model=MOCK_MODEL, cost_usd=Decimal("0"), latency_ms=0)


class LlmProposer:
    """Session 5's proposer: `client.complete` (cache, budget cap, `llm_calls` row) + a RawReply.

    `complete_fn` is injectable so tests can prove the seam without a network; the default is the
    real transport. `model` has no default on purpose: the model for the 50 real recommendations is
    a SPEND decision made in session 5.
    """

    is_mock = False

    def __init__(
        self,
        model: str,
        *,
        max_tokens: int = 400,
        phase: str = "phase5",
        purpose: str = "recommendation",
        complete_fn: Callable[..., Any] | None = None,
        sdk_client: Any | None = None,
    ) -> None:
        if complete_fn is None:
            from pricepilot.llm.client import complete

            complete_fn = complete
        self.model = model
        self.max_tokens = max_tokens
        self.phase = phase
        self.purpose = purpose
        self._complete = complete_fn
        self._sdk_client = sdk_client

    def __call__(self, request: ProposalRequest) -> RawReply:
        completion = self._complete(
            model=self.model,
            prompt=request.prompt,
            system=request.system,
            max_tokens=self.max_tokens,
            phase=self.phase,
            purpose=self.purpose,
            sdk_client=self._sdk_client,
        )
        latency = completion.latency_ms
        return RawReply(
            text=completion.text,
            model=self.model,
            cost_usd=completion.usage.cost_usd,
            latency_ms=None if latency is None else round(latency),
        )
