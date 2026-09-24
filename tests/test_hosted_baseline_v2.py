"""Phase 3 item 8 session 3, task 3: pins `scripts/run_hosted_baseline_v2.py`'s `run()` -- the
per-call diagnostic report (stop_reason, block_types) that v1 never captured, and that parsing
stays byte-for-byte the same strict Yes/No match as v1 despite the longer max_tokens. No network,
no spend -- a mocked SDK client and an in-memory SQLite `llm_calls` table."""

from __future__ import annotations

import json
import sys
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pricepilot.llm import client  # noqa: E402
from pricepilot.models import LlmCall  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))

import run_hosted_baseline_v2 as rhb2  # noqa: E402

MODEL = "claude-sonnet-5"


class FakeSdkRaw:
    """Returns caller-chosen content blocks and a stop_reason per queued reply -- the shape
    rhb2.run() needs to exercise the stop_reason/block_types path, unlike v1's plain-text fake."""

    def __init__(self, replies: list[tuple[str, list[Any], int, int]]) -> None:
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


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def test_max_tokens_is_64_not_5() -> None:
    assert rhb2.MAX_TOKENS == 64


def test_run_records_stop_reason_and_block_types_per_call(tmp_path: Path, db: Any) -> None:
    prompts = [("p1", "a"), ("p2", "b")]
    sdk = FakeSdkRaw(
        [
            ("end_turn", [_text_block("Yes")], 500, 1),
            ("max_tokens", [_text_block(""), SimpleNamespace(type="thinking", text=None)], 500, 64),
        ]
    )
    scores, report = rhb2.run(MODEL, prompts, sdk_client=sdk, cache_dir=tmp_path)
    assert scores == {"p1": 1.0, "p2": 0.0}
    assert report["per_call"][0] == {
        "pair_id": "p1",
        "stop_reason": "end_turn",
        "block_types": ["text"],
        "raw": "Yes",
        "parsed_ok": True,
    }
    assert report["per_call"][1] == {
        "pair_id": "p2",
        "stop_reason": "max_tokens",
        "block_types": ["text", "thinking"],
        "raw": "",
        "parsed_ok": False,
    }
    assert report["stop_reason_counts"] == {"end_turn": 1, "max_tokens": 1}
    assert report["block_type_counts"] == {"text": 2, "thinking": 1}


def test_parsing_is_unchanged_a_reply_that_continues_past_yes_is_unparseable(
    tmp_path: Path, db: Any
) -> None:
    """Protocol 5.12: max_tokens=64 gives the model room to finish, it does NOT relax what counts
    as a valid answer -- parse_answer still requires an exact stripped "Yes" or "No"."""
    prompts = [("p1", "a")]
    sdk = FakeSdkRaw([("end_turn", [_text_block("Yes, they are the same product.")], 500, 10)])
    scores, report = rhb2.run(MODEL, prompts, sdk_client=sdk, cache_dir=tmp_path)
    assert scores == {"p1": 0.0}
    assert report["unparseable"] == 1
    assert report["unparseable_replies"] == [
        {"pair_id": "p1", "raw": "Yes, they are the same product."}
    ]


def test_reproduces_the_v1_empty_reply_shape_as_a_config_artifact(tmp_path: Path, db: Any) -> None:
    """The exact shape session 2 missed: output_tokens == max_tokens, a "text" block that is
    empty, no visible reply -- now captured in the report instead of silently disappearing."""
    prompts = [("p1", "a")]
    sdk = FakeSdkRaw([("max_tokens", [_text_block("")], 500, 64)])
    scores, report = rhb2.run(MODEL, prompts, sdk_client=sdk, cache_dir=tmp_path)
    assert scores == {"p1": 0.0}
    assert report["unparseable"] == 1
    assert report["per_call"][0]["stop_reason"] == "max_tokens"
    assert report["per_call"][0]["raw"] == ""


def test_refuses_a_cache_hit_with_no_stop_reason(tmp_path: Path, db: Any) -> None:
    """A reviewer suggestion: enforce in code, not just by construction, that v2's cache key can
    never silently read back a pre-5.12 (v1-era) entry lacking stop_reason/block_types."""
    key = client.cache_key(MODEL, str(rhb2.MAX_TOKENS), repr(None), "", "a")
    (tmp_path / f"{key}.json").write_text(
        json.dumps({"text": "Yes", "input_tokens": 500, "output_tokens": 1}), encoding="utf-8"
    )
    sdk = FakeSdkRaw([])  # never reached -- the cache hit happens first
    with pytest.raises(SystemExit):
        rhb2.run(MODEL, [("p1", "a")], sdk_client=sdk, cache_dir=tmp_path)


def test_load_prompts_reads_no_label_tier_or_split() -> None:
    prompts = rhb2.load_prompts()
    assert len(prompts) == rhb2.EXPECTED_PAIRS == 287
    assert all(isinstance(pid, str) and isinstance(p, str) for pid, p in prompts)
