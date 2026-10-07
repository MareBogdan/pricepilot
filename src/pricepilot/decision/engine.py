"""The Phase 5 decision engine for ONE product (ADR-0042).

    gather (SQL) -> retrieve policy text (RAG) -> build prompt -> PROPOSER -> parse -> GUARD -> trace

Hard rules this module exists to keep (CLAUDE.md section 6):

* **Numbers come from SQL / `config/pricing-policy.toml`, never from RAG.** Cost, price, stock,
  competitor prices and every limit shown to the model are read from `products`,
  `product_matches` and the thresholds config. Retrieved policy text rides along as illustrative
  context only; nothing here parses a number out of it (ADR-0036).
* **The guard is the final authority.** `policy.guard.enforce` decides the applied price. The
  proposer's price is a suggestion; it is never returned, stored as "the price", or applied
  without passing through `enforce`. An unparseable reply FLAGs and never reaches a price at all.
* **Elasticity is a labelled placeholder** (Phase 4 POSTPONE, ADR-0031/0032), never a value.
* Money is `Decimal` end to end; JSON columns carry money as strings.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pricepilot.decision.proposer import ProposalRequest, Proposer, RawReply
from pricepilot.models import Product, ProductMatch, Recommendation
from pricepilot.policy.guard import GuardStatus, enforce, margin
from pricepilot.policy.retrieval import PolicyPassage, retrieve_policy
from pricepilot.policy.thresholds import PricingPolicyThresholds, load_thresholds

PRICE_7D_SOURCE = "mock_store_synthetic"
RETRIEVAL_K = 3

# Phase 4 is POSTPONED (ADR-0031/0032): no elasticity has been estimated from data. `value` is
# deliberately None -- the mock store's planted constants are a generator input, not an estimate,
# and feeding them back would be the circularity trap (CLAUDE.md section 7, Phase 4).
ELASTICITY_PLACEHOLDER: dict[str, Any] = {
    "value": None,
    "label": (
        "PLACEHOLDER -- SIMULATED -- not a Phase 4 estimate. Phase 4 is POSTPONED "
        "(ADR-0031/0032); no demand response has been estimated."
    ),
}

SYSTEM_PROMPT = (
    "You propose a shelf price for ONE product of a Romanian online pet-supplies shop. You only "
    "propose; deterministic code checks every proposal against the margin floor, discount "
    "eligibility and speed limits afterwards and overrides or rejects it. Use only the numbers in "
    "the FACTS sections. The policy passages are reference text: they may be out of date and are "
    "never a source of numbers. If the inputs disagree or look stale, keep the current price."
)

_CATEGORY_WORDS = {
    "dry_food": "dry food",
    "wet_food": "wet food",
    "treats": "treats",
    "litter": "litter",
    "grooming": "grooming",
    "accessories": "accessories",
}


# --------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CompetitorPrice:
    shop: str
    price: Decimal
    score: Decimal
    price_date: date
    in_stock: bool | None
    title: str

    def to_json(self) -> dict[str, Any]:
        return {
            "shop": self.shop,
            "price": str(self.price),
            "score": str(self.score),
            "price_date": self.price_date.isoformat(),
            "in_stock": self.in_stock,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class ProductSnapshot:
    """Everything the proposer and the guard are given about one product. All numbers are from SQL
    (`products`, `product_matches`) or, for `price_7d_ago`, the SYNTHETIC mock-store history."""

    product_id: int
    sku: str
    title: str
    brand: str
    category: str
    cost: Decimal
    current_price: Decimal
    stock: int
    net_weight_g: int | None
    competitors: tuple[CompetitorPrice, ...]
    price_7d_ago: Decimal | None


PriceHistoryFn = Callable[[int, date], Decimal | None]


def mock_store_price_7d_ago(product_id: int, as_of: date) -> Decimal | None:
    """Our price on `as_of - 7 days` from the mock store's history. SYNTHETIC: the mock store
    generates that series, nobody observed it. `None` when the day is not in the series."""
    from services.mock_store.app import get_history_points

    target = as_of - timedelta(days=7)
    for point in get_history_points(product_id):
        if point.day == target:
            return point.price
    return None


def gather_snapshot(
    session: Session,
    product_id: int,
    *,
    price_7d_ago_fn: PriceHistoryFn = mock_store_price_7d_ago,
    as_of: date | None = None,
) -> ProductSnapshot:
    """SQL gather. A product with no matched competitor is valid (`competitors == ()`): the
    recommendation is then made from cost and policy alone."""
    product = session.get(Product, product_id)
    if product is None:
        raise LookupError(f"no product with id {product_id} in `products` (run sync_catalogue.py)")
    matches = (
        session.execute(
            select(ProductMatch)
            .where(ProductMatch.product_id == product_id)
            .order_by(ProductMatch.source)
        )
        .scalars()
        .all()
    )
    return ProductSnapshot(
        product_id=product.id,
        sku=product.sku,
        title=product.title,
        brand=product.brand,
        category=product.category,
        cost=product.purchase_cost,
        current_price=product.current_price,
        stock=product.stock,
        net_weight_g=product.net_weight_g,
        competitors=tuple(
            CompetitorPrice(
                shop=m.source,
                price=m.competitor_price,
                score=m.score,
                price_date=m.price_date,
                in_stock=m.in_stock,
                title=m.competitor_title,
            )
            for m in matches
        ),
        price_7d_ago=price_7d_ago_fn(product_id, as_of or date.today()),
    )


def clean_title(title: str, limit: int = 160) -> str:
    """A scraped competitor title is untrusted text going into a prompt: collapse every run of
    whitespace (so it cannot open a new line or section) and drop quotes (so it cannot close the
    quoting) -- review finding 5, 2026-10-07."""
    return " ".join(title.replace('"', "'").split())[:limit]


def policy_query(category: str) -> str:
    return (
        f"{_CATEGORY_WORDS.get(category, category)}: minimum margin, discount eligibility, "
        "rounding, max daily move"
    )


# --------------------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------------------


def _pct(fraction: Decimal) -> str:
    return f"{(fraction * 100).quantize(Decimal('0.1'))}%"


def build_prompt(
    snapshot: ProductSnapshot,
    passages: list[PolicyPassage],
    thresholds: PricingPolicyThresholds,
) -> str:
    """The user prompt. Facts and limits come from SQL / the TOML config; the policy passages are
    appended last and labelled reference-only."""
    s = snapshot
    floor = Decimal(str(thresholds.margin_floor[s.category]))  # type: ignore[index]
    speed = thresholds.speed_of_change
    lines = [
        "## FACTS: our product (from the database)",
        f"SKU: {s.sku}",
        f"Title: {s.title}",
        f"Category: {s.category}",
        f"Purchase cost: {s.cost} RON",
        f"Current shelf price: {s.current_price} RON "
        f"(gross margin {_pct(margin(s.current_price, s.cost))})",
        f"Stock: {s.stock} units",
    ]
    if s.price_7d_ago is None:
        lines.append(
            "Our price 7 days ago: not available (any change will be flagged for human review; "
            "keeping the current price is the only answer the code can approve)"
        )
    else:
        lines.append(
            f"Our price 7 days ago: {s.price_7d_ago} RON "
            "[SYNTHETIC mock-store history, not an observed price]"
        )
    lines += ["", "## FACTS: matched competitor prices (from the database)"]
    if not s.competitors:
        lines.append("No matched competitor listing. Decide from our cost and the limits only.")
    for c in s.competitors:
        stock = {True: "in stock", False: "OUT of stock", None: "stock unknown"}[c.in_stock]
        lines.append(
            f"- {c.shop}: {c.price} RON, observed {c.price_date.isoformat()}, {stock}, "
            f'match score {c.score} -- "{clean_title(c.title)}"'
        )
    lines += [
        "",
        "## FACTS: demand elasticity",
        f"elasticity_placeholder: {ELASTICITY_PLACEHOLDER['label']}",
        "Do not assume any particular demand response to a price change.",
        "",
        "## FACTS: hard limits (from config/pricing-policy.toml; enforced by code after your reply)",
        f"- Minimum gross margin for {s.category}: {_pct(floor)} of the shelf price",
        f"- Maximum move: {_pct(Decimal(str(speed.max_daily_fraction)))} vs the current price, "
        f"{_pct(Decimal(str(speed.max_weekly_fraction)))} vs the price 7 days ago",
        f"- A discount needs at least {thresholds.discount_eligibility.min_stock_units} units "
        "in stock",
        "- The code rounds the final price to a charm value; do not round for it.",
        "A proposal that breaks a limit is rejected or flagged, not applied.",
        "",
        "## REFERENCE ONLY: pricing-policy passages (retrieved text)",
        "The code guard above is authoritative. These passages explain intent and may quote "
        "figures; do not take any number from them.",
    ]
    for p in passages:
        lines += [
            "",
            f"### {p.heading} (section {p.section_ref}, similarity {p.similarity:.2f})",
            p.text,
        ]
    lines += [
        "",
        "## TASK",
        "Propose a new shelf price in RON. To keep the price unchanged, propose the current price.",
        "Reply in exactly this format and nothing else:",
        "PRICE: <number with at most two decimals, no currency symbol>",
        "RATIONALE: <one to three sentences citing the facts you used>",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Reply parsing
# --------------------------------------------------------------------------------------


class ProposalParseError(ValueError):
    """The proposer's reply was not in the required format. The engine turns this into a FLAG."""


@dataclass(frozen=True, slots=True)
class ParsedProposal:
    price: Decimal
    rationale: str


_PRICE_LINE = re.compile(r"^[ \t]*PRICE[ \t]*:", re.MULTILINE)
# The whole reply is `PRICE: <n>` then `RATIONALE: <text>` -- no preamble, no leading zeros.
_REPLY = re.compile(
    r"PRICE[ \t]*:[ \t]*((?:0|[1-9]\d{0,8})(?:\.\d{1,2})?)(?:[ \t]*RON)?[ \t]*\n+"
    r"[ \t]*RATIONALE[ \t]*:[ \t]*(.+)",
    re.DOTALL,
)
MAX_RATIONALE_CHARS = 2000


def parse_reply(text: str) -> ParsedProposal:
    """`PRICE: <n>` then `RATIONALE: <text>`, and nothing before or between. Strict: exactly one
    PRICE line, a plain positive number with at most two decimals (a stray `NaN`, `1e9`, `-5` or
    `007` is refused), a non-empty rationale. CRLF is normalised first. Anything else raises
    `ProposalParseError` -- never a guessed price. The rationale is model text: escape it when it
    is rendered (Phase 7)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    found = len(_PRICE_LINE.findall(text))
    if found != 1:
        raise ProposalParseError(f"expected exactly one PRICE line, found {found}")
    match = _REPLY.fullmatch(text)
    if match is None:
        raise ProposalParseError("reply is not exactly `PRICE: <n>` then `RATIONALE: <text>`")
    price = Decimal(match.group(1))
    rationale = match.group(2).strip()
    if price <= 0:
        raise ProposalParseError(f"PRICE must be positive, got {price}")
    if not rationale:
        raise ProposalParseError("missing or empty RATIONALE")
    return ParsedProposal(price=price, rationale=rationale[:MAX_RATIONALE_CHARS])


# --------------------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------------------


def decide(
    snapshot: ProductSnapshot,
    *,
    proposer: Proposer,
    run_label: str,
    retriever: Callable[[str, int], list[PolicyPassage]] = retrieve_policy,
    thresholds: PricingPolicyThresholds | None = None,
    scenario: str | None = None,
) -> Recommendation:
    """Run one product through retrieve -> prompt -> propose -> parse -> guard. Returns the
    (unsaved) trace row; `save` persists it. Nothing here touches `llm_calls` -- a real proposer
    logs its own call inside `client.complete`."""
    t = thresholds or load_thresholds()
    passages = retriever(policy_query(snapshot.category), RETRIEVAL_K)
    prompt = build_prompt(snapshot, passages, t)

    reply: RawReply = proposer(
        ProposalRequest(system=SYSTEM_PROMPT, prompt=prompt, snapshot=snapshot)
    )
    if proposer.is_mock and reply.cost_usd != 0:
        raise RuntimeError("a mock proposer must cost $0")

    proposed_price: Decimal | None = None
    rationale: str | None = None
    final_price: Decimal | None
    reason: str | None
    try:
        parsed = parse_reply(reply.text)
    except ProposalParseError as exc:
        # No price to check, so the guard cannot run: FLAG for a human, never guess a price.
        status, final_price, reason = GuardStatus.FLAG, None, f"unparseable proposer reply: {exc}"
    else:
        proposed_price, rationale = parsed.price, parsed.rationale
        try:
            decision = enforce(
                category=snapshot.category,
                cost=snapshot.cost,
                current_price=snapshot.current_price,
                proposed_price=proposed_price,
                stock=snapshot.stock,
                price_7d_ago=snapshot.price_7d_ago,
                thresholds=t,
            )
        except ValueError as exc:
            # The guard fails closed by raising on input it cannot judge (e.g. a proposal so small
            # that charm rounding goes negative). The reply is already paid for, so the trace must
            # survive: FLAG for a human, no applied price (review finding 1, 2026-10-07).
            status, final_price, reason = (
                GuardStatus.FLAG,
                None,
                f"guard refused the proposal: {exc}",
            )
        else:
            status, final_price, reason = decision.status, decision.price, decision.reason

    return Recommendation(
        product_id=snapshot.product_id,
        run_label=run_label,
        is_mock=proposer.is_mock,
        scenario=scenario,
        category=snapshot.category,
        cost=snapshot.cost,
        current_price=snapshot.current_price,
        stock=snapshot.stock,
        competitor_prices=[c.to_json() for c in snapshot.competitors],
        price_7d_ago=snapshot.price_7d_ago,
        price_7d_ago_source=PRICE_7D_SOURCE,
        elasticity_placeholder=dict(ELASTICITY_PLACEHOLDER),
        rag_sections=[
            {"section_ref": p.section_ref, "similarity": round(p.similarity, 4)} for p in passages
        ],
        prompt_text=prompt,
        llm_model=reply.model,
        llm_raw_reply=reply.text,
        llm_proposed_price=proposed_price,
        llm_rationale=rationale,
        llm_cost_usd=reply.cost_usd,
        llm_latency_ms=reply.latency_ms,
        guard_status=str(status),
        guard_final_price=final_price,
        guard_reason=reason,
    )


def recommend(
    session: Session,
    product_id: int,
    *,
    proposer: Proposer,
    run_label: str,
    retriever: Callable[[str, int], list[PolicyPassage]] = retrieve_policy,
    price_7d_ago_fn: PriceHistoryFn = mock_store_price_7d_ago,
    thresholds: PricingPolicyThresholds | None = None,
    as_of: date | None = None,
    scenario: str | None = None,
) -> Recommendation:
    """Gather, decide and persist one recommendation; returns the saved trace row."""
    snapshot = gather_snapshot(session, product_id, price_7d_ago_fn=price_7d_ago_fn, as_of=as_of)
    row = decide(
        snapshot,
        proposer=proposer,
        run_label=run_label,
        retriever=retriever,
        thresholds=thresholds,
        scenario=scenario,
    )
    session.add(row)
    session.flush()
    return row
