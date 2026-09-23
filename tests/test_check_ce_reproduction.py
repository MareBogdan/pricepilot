"""The reproduction verdict decides which cross-encoder's numbers reach the README, so the rule in
docs/phase3-ce-reproduction-rule.md is pinned here case by case."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_ce_reproduction as ccr  # noqa: E402

LEDGER = {
    "entries": [
        {"model_id": ccr.FINETUNED_MODEL_ID, "threshold": 0.89},
        {"model_id": ccr.ZEROSHOT_MODEL_ID, "threshold": 0.86},
    ]
}


def _scores(n: int, offset: int = 0) -> dict[str, float]:
    return {f"p{offset + i}": (i % 100) / 100 for i in range(n)}


def _write(dir_: Path, name: str, data: dict[str, float]) -> None:
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / name).write_text(json.dumps(data), encoding="utf-8")


def _setup(tmp_path: Path, flip_one: bool = False) -> tuple[Path, Path]:
    committed, retrain = tmp_path / "committed", tmp_path / "retrain"
    for stem, _which, _gated in ccr.FILES:
        n = 287 if stem.endswith("-test") else 672
        base = _scores(n)
        _write(committed, f"{stem}.json", base)
        changed = dict(base)
        if flip_one and stem == "preds-finetuned-test":
            key = "p50"  # 0.50, below the 0.89 threshold
            changed[key] = 0.95  # crosses it
        _write(retrain, f"{stem}-retrain.json", changed)
    return committed, retrain


def test_identical_is_reproduced(tmp_path: Path) -> None:
    committed, retrain = _setup(tmp_path)
    r = ccr.run_check(committed, retrain, LEDGER, {"best_epoch": 6})
    assert r["verdict"] == "REPRODUCED"
    assert r["finetuned_flips_total"] == 0
    assert r["finetuned_pairs_compared"] == 959
    assert r["cross_encoder_id_for_item_8"] == ccr.FINETUNED_MODEL_ID


def test_one_flip_is_not_reproduced(tmp_path: Path) -> None:
    committed, retrain = _setup(tmp_path, flip_one=True)
    r = ccr.run_check(committed, retrain, LEDGER, {"best_epoch": 6})
    assert r["verdict"] == "NOT_REPRODUCED"
    assert r["finetuned_flips_total"] == 1
    assert r["cross_encoder_id_for_item_8"] == ccr.RETRAIN_MODEL_ID


def test_epoch_7_with_zero_flips_is_not_reproduced(tmp_path: Path) -> None:
    committed, retrain = _setup(tmp_path)
    r = ccr.run_check(committed, retrain, LEDGER, {"best_epoch": 7})
    assert r["finetuned_flips_total"] == 0
    assert r["verdict"] == "NOT_REPRODUCED"


def test_zeroshot_flips_do_not_enter_the_verdict(tmp_path: Path) -> None:
    committed, retrain = _setup(tmp_path)
    changed = _scores(287)
    changed["p50"] = 0.95  # crosses the zero-shot 0.86 threshold
    _write(retrain, "preds-zeroshot-test-retrain.json", changed)
    r = ccr.run_check(committed, retrain, LEDGER, {"best_epoch": 6})
    assert r["files"]["preds-zeroshot-test"]["flips"] == 1
    assert r["verdict"] == "REPRODUCED"


def test_key_set_mismatch_is_an_error(tmp_path: Path) -> None:
    committed, retrain = _setup(tmp_path)
    data = _scores(287)
    del data["p3"]
    data["extra"] = 0.5
    _write(retrain, "preds-finetuned-test-retrain.json", data)
    with pytest.raises(ccr.KeySetMismatchError):
        ccr.run_check(committed, retrain, LEDGER, {"best_epoch": 6})


def test_wrong_pair_count_is_an_error() -> None:
    with pytest.raises(ccr.KeySetMismatchError):
        ccr.verdict(6, 0, 958)


def test_threshold_comes_from_the_ledger_not_a_constant(tmp_path: Path) -> None:
    committed, retrain = _setup(tmp_path, flip_one=True)
    low = {
        "entries": [
            {"model_id": ccr.FINETUNED_MODEL_ID, "threshold": 0.10},
            {"model_id": ccr.ZEROSHOT_MODEL_ID, "threshold": 0.86},
        ]
    }
    # 0.50 -> 0.95 does not cross a 0.10 threshold, so no flip
    r = ccr.run_check(committed, retrain, low, {"best_epoch": 6})
    assert r["thresholds_from_ledger"]["finetuned"] == 0.10
    assert r["finetuned_flips_total"] == 0


def test_source_reads_no_label_file() -> None:
    src = (ROOT / "scripts" / "check_ce_reproduction.py").read_text(encoding="utf-8")
    assert "eval-view" not in src
    assert "labels.json" not in src


def test_non_finite_score_is_an_error() -> None:
    with pytest.raises(ccr.KeySetMismatchError):
        ccr.compare_scores({"a": 0.1}, {"a": float("nan")}, 0.89, "x")


def test_wrong_per_file_pair_count_is_an_error(tmp_path: Path) -> None:
    committed, retrain = _setup(tmp_path)
    short = _scores(286)  # 286 + 672 + ... would still need the per-file check to catch it
    _write(committed, "preds-finetuned-test.json", short)
    _write(retrain, "preds-finetuned-test-retrain.json", short)
    with pytest.raises(ccr.KeySetMismatchError):
        ccr.run_check(committed, retrain, LEDGER, {"best_epoch": 6})
