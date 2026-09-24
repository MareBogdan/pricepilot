"""Money moves through `pricepilot.llm.client.complete`, and a README number depends on it, so its
guard rails are pinned here with a mocked SDK client and an in-memory SQLite `llm_calls` table
(no network, no Postgres, no spend)."""

from __future__ import annotations

import sys
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from pricepilot.llm import client
from pricepilot.matching.hosted_baseline import parse_answer, summarise_latency
from pricepilot.models import LlmCall

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_hosted_baseline as rhb  # noqa: E402

MODEL = "claude-sonnet-5"


class FakeSdk:
    """Stands in for `anthropic.Anthropic`; counts calls, replies from a queue."""

    def __init__(self, replies: list[str], in_tokens: int = 500, out_tokens: int = 1) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []
        self.in_tokens, self.out_tokens = in_tokens, out_tokens
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.replies.pop(0))],
            usage=SimpleNamespace(input_tokens=self.in_tokens, output_tokens=self.out_tokens),
        )


@pytest.fixture()
def db(monkeypatch: pytest.MonkeyPatch) -> Any:
    engine = create_engine("sqlite://")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        LlmCall.__table__.create(engine)  # type: ignore[attr-defined]

    @contextmanager
    def scope() -> Iterator[Session]:
        session = Session(engine, expire_on_commit=False)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(client, "session_scope", scope)
    monkeypatch.setattr(
        client, "get_settings", lambda: SimpleNamespace(llm_budget_usd=5.0, anthropic_api_key="k")
    )
    return scope


def _rows(scope: Any) -> list[LlmCall]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with scope() as s:
            return list(s.execute(select(LlmCall).order_by(LlmCall.id)).scalars())


def _call(sdk: FakeSdk, tmp_path: Path, prompt: str = "hello", **kw: Any) -> client.Completion:
    return client.complete(
        model=MODEL, prompt=prompt, max_tokens=5, phase="phase3", purpose="t",
        sdk_client=sdk, cache_dir=tmp_path, **kw,
    )  # fmt: skip


def test_budget_cap_raises_before_any_call(
    db: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        client,
        "get_settings",
        lambda: SimpleNamespace(llm_budget_usd=0.0001, anthropic_api_key="k"),
    )
    sdk = FakeSdk(["Yes"])
    with pytest.raises(client.BudgetExceeded):
        _call(sdk, tmp_path, prompt="x" * 30_000)  # ~10k estimated input tokens = $0.02 > cap
    assert sdk.calls == []  # never reached the API
    assert list(tmp_path.glob("*.json")) == []  # nothing cached
    assert _rows(db) == []  # nothing logged


def test_budget_cap_counts_spend_already_logged(db: Any, tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with db() as s:
            s.add(LlmCall(phase="p", purpose="x", model=MODEL, cost_usd=Decimal("4.999999")))
    assert client.spend_to_date() == Decimal("4.999999")
    sdk = FakeSdk(["Yes"])
    with pytest.raises(client.BudgetExceeded):
        _call(sdk, tmp_path, prompt="x" * 3000)
    assert sdk.calls == []


def test_second_identical_call_is_a_cache_hit_costing_zero(db: Any, tmp_path: Path) -> None:
    sdk = FakeSdk(["Yes", "should-never-be-used"])
    first = _call(sdk, tmp_path)
    second = _call(sdk, tmp_path)
    assert (first.cache_hit, second.cache_hit) == (False, True)
    assert second.text == first.text == "Yes"
    assert second.usage.cost_usd == Decimal("0")
    assert len(sdk.calls) == 1  # the API was called once
    rows = _rows(db)
    assert [r.cache_hit for r in rows] == [False, True]
    assert rows[1].cost_usd == Decimal("0")
    assert rows[0].cache_key == rows[1].cache_key


def test_cache_key_covers_every_request_parameter(db: Any, tmp_path: Path) -> None:
    sdk = FakeSdk(["Yes", "No"])
    a = _call(sdk, tmp_path)
    b = client.complete(
        model=MODEL, prompt="hello", max_tokens=6, phase="p", purpose="t",
        sdk_client=sdk, cache_dir=tmp_path,
    )  # fmt: skip
    assert not a.cache_hit and not b.cache_hit and len(sdk.calls) == 2


def test_log_call_writes_model_tokens_and_cost(db: Any, tmp_path: Path) -> None:
    sdk = FakeSdk(["No"], in_tokens=1000, out_tokens=3)
    out = _call(sdk, tmp_path)
    (row,) = _rows(db)
    assert row.model == MODEL
    assert (row.input_tokens, row.output_tokens) == (1000, 3)
    # $2 / Mtok in, $10 / Mtok out: (2*1000 + 10*3) / 1e6
    assert row.cost_usd == Decimal("0.002030") == out.usage.cost_usd
    assert row.cache_hit is False and row.phase == "phase3" and row.latency_ms is not None


def test_call_forwards_temperature_and_max_tokens(db: Any, tmp_path: Path) -> None:
    sdk = FakeSdk(["Yes"])
    _call(sdk, tmp_path)
    (kw,) = sdk.calls
    assert kw["model"] == MODEL and kw["max_tokens"] == 5 and "extra_body" not in kw
    assert kw["messages"] == [{"role": "user", "content": "hello"}]


class FakeSdkRaw:
    """Like FakeSdk, but returns caller-chosen content blocks and a stop_reason -- for
    complete_diagnostic, which needs to see block types the FakeSdk/`Completion.text` path
    collapses away."""

    def __init__(self, replies: list[tuple[str, list[Any], int, int]]) -> None:
        # each reply: (stop_reason, blocks, in_tokens, out_tokens); each block a SimpleNamespace
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        stop_reason, blocks, in_tok, out_tok = self.replies.pop(0)
        return SimpleNamespace(
            content=blocks,
            stop_reason=stop_reason,
            usage=SimpleNamespace(input_tokens=in_tok, output_tokens=out_tok),
        )


def test_diagnostic_call_returns_stop_reason_and_every_block(db: Any) -> None:
    blocks = [SimpleNamespace(type="text", text=""), SimpleNamespace(type="thinking", text=None)]
    sdk = FakeSdkRaw([("max_tokens", blocks, 500, 5)])
    out = client.complete_diagnostic(
        model=MODEL, prompt="diag", max_tokens=5, phase="phase3", purpose="diag", sdk_client=sdk
    )
    assert out.stop_reason == "max_tokens"
    assert [(b.type, b.text) for b in out.blocks] == [("text", ""), ("thinking", None)]
    assert out.usage.output_tokens == 5


def test_diagnostic_call_is_logged_and_never_cached(db: Any) -> None:
    sdk = FakeSdkRaw(
        [
            ("end_turn", [SimpleNamespace(type="text", text="Yes")], 500, 1),
            ("end_turn", [SimpleNamespace(type="text", text="Yes")], 500, 1),
        ]
    )
    client.complete_diagnostic(
        model=MODEL, prompt="diag", max_tokens=5, phase="phase3", purpose="diag", sdk_client=sdk
    )
    client.complete_diagnostic(
        model=MODEL, prompt="diag", max_tokens=5, phase="phase3", purpose="diag", sdk_client=sdk
    )
    assert len(sdk.calls) == 2  # no disk cache -- a second identical call hits the API again
    rows = _rows(db)
    assert len(rows) == 2 and all(r.cache_hit is False for r in rows)


def test_diagnostic_call_respects_the_budget_cap(db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        client,
        "get_settings",
        lambda: SimpleNamespace(llm_budget_usd=0.0001, anthropic_api_key="k"),
    )
    sdk = FakeSdkRaw([("end_turn", [SimpleNamespace(type="text", text="Yes")], 500, 1)])
    with pytest.raises(client.BudgetExceeded):
        client.complete_diagnostic(
            model=MODEL,
            prompt="x" * 30_000,
            max_tokens=5,
            phase="phase3",
            purpose="diag",
            sdk_client=sdk,
        )
    assert sdk.calls == []


def test_unknown_model_has_no_price() -> None:
    with pytest.raises(KeyError):
        client.cost_usd("some-unpriced-model", 1, 1)


def test_prices_match_the_published_list() -> None:
    assert client.PRICES_USD_PER_MTOK["claude-sonnet-5"] == (Decimal("2"), Decimal("10"))
    assert client.PRICES_USD_PER_MTOK["claude-haiku-4-5-20251001"] == (Decimal("1"), Decimal("5"))


# ---- the answer parser (protocol 5.7) --------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Yes", (1.0, True)),
        (" Yes\n", (1.0, True)),
        ("No", (0.0, True)),
        ("Maybe", (0.0, False)),
        ("Yes.", (0.0, False)),
        ("yes", (0.0, False)),
        ("", (0.0, False)),
        ("No, they differ", (0.0, False)),
    ],
)
def test_parse_answer(raw: str, expected: tuple[float, bool]) -> None:
    assert parse_answer(raw) == expected


def test_run_counts_unparseable_scores_zero_and_never_retries(db: Any, tmp_path: Path) -> None:
    prompts = [("p1", "a"), ("p2", "b"), ("p3", "c"), ("p4", "d")]
    sdk = FakeSdk(["Yes", "No", "I think so", "Yes"])
    scores, report = rhb.run(MODEL, prompts, sdk_client=sdk, cache_dir=tmp_path)
    assert scores == {"p1": 1.0, "p2": 0.0, "p3": 0.0, "p4": 1.0}
    assert report["unparseable"] == 1
    assert report["unparseable_replies"] == [{"pair_id": "p3", "raw": "I think so"}]
    assert len(sdk.calls) == 4  # one call per pair: no retry into a better answer
    assert report["threshold"] == 0.5 and "NOT selected" in report["threshold_note"]
    # 4 calls x (2 * 500 + 10 * 1) / 1e6 dollars
    assert Decimal(report["cost_usd"]) == Decimal("0.00404")


def test_summarise_latency_shape() -> None:
    s = summarise_latency([100.0, 200.0, 300.0])
    assert s["n"] == 3 and s["p50"] == 200.0 and s["mean"] == 200.0
    assert summarise_latency([]) == {"n": 0}
