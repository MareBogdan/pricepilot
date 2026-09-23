"""Tests for scripts/score_predictions.py (CLAUDE.md §7 item 5; ADR-0028 addendum #19).

This is the harness's most consequential file: everything the fine-tune gets compared against
runs through it, once per model, on the real 287 TEST pairs. Every test here builds its
predictions from the REAL, committed docs/learned/phase3-eval-view.json TEST entries -- no
synthetic labels, only synthetic PREDICTIONS scored against real labels -- and monkeypatches
scripts.score_predictions.RESULTS_DIR / LEDGER_JSON to a tmp_path so no test run ever touches the
real docs/learned/results/test-touch-ledger.json (which the actual baseline and fine-tune runs
will use, once per model, for real)."""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import score_predictions as sp  # noqa: E402

EVAL_VIEW_FILE = ROOT / "docs" / "learned" / "phase3-eval-view.json"


def _real_test_entries() -> list[dict[str, Any]]:
    view = json.loads(EVAL_VIEW_FILE.read_text(encoding="utf-8"))
    return [e for e in view["entries"] if e["split"] == "test"]


ENTRIES = _real_test_entries()
SCORED_ENTRIES = [e for e in ENTRIES if e["scored"]]
ALL_PAIR_IDS = [e["pair_id"] for e in ENTRIES]
N_POS = sum(1 for e in SCORED_ENTRIES if e["label"] == "M")
N_NEG = sum(1 for e in SCORED_ENTRIES if e["label"] == "N")


@pytest.fixture(autouse=True)
def _isolate_results_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test in this file runs against a throwaway results dir/ledger -- the real
    docs/learned/results/test-touch-ledger.json must never be touched by a test run, only by a
    real model's scoring run (docs/phase3-baseline-model-choice.md rule 3: TEST touched once)."""
    results_dir = tmp_path / "results"
    monkeypatch.setattr(sp, "RESULTS_DIR", results_dir)
    monkeypatch.setattr(sp, "LEDGER_JSON", results_dir / "test-touch-ledger.json")
    return results_dir


def _write_predictions(
    tmp_path: Path, predictions: dict[str, float], name: str = "preds.json"
) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(predictions), encoding="utf-8")
    return path


def _run_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    predictions: dict[str, float],
    model_id: str,
    threshold: float = 0.5,
    extra_args: list[str] | None = None,
    predictions_name: str = "preds.json",
) -> None:
    pred_path = _write_predictions(tmp_path, predictions, predictions_name)
    argv = [
        "score_predictions.py",
        "--predictions",
        str(pred_path),
        "--threshold",
        str(threshold),
        "--model-id",
        model_id,
        *(extra_args or []),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    sp.main()


# ---------------------------------------------------------------------------
# TASK 5: synthetic predictors, direct score() calls (no ledger/CLI involved)
# ---------------------------------------------------------------------------


def test_perfect_predictor_f1_is_one() -> None:
    predictions = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    result = sp.score(ENTRIES, predictions, threshold=0.5)

    assert result["f1"]["value"] == 1.0
    assert result["precision"]["value"] == 1.0
    assert result["recall_all_positives"]["value"] == 1.0
    assert result["recall_excluding_13_repeat_positives"]["value"] == 1.0
    assert result["accuracy"]["value"] == 1.0
    assert result["s_dropped"] == len(ENTRIES) - len(SCORED_ENTRIES) == 3
    assert result["n_scored"] == len(SCORED_ENTRIES) == 284

    cm = result["confusion_matrix"]
    assert cm == {"tp": N_POS, "fp": 0, "fn": 0, "tn": N_NEG}

    # every CI must be a real, sane interval around the point estimate
    for key in (
        "precision",
        "recall_all_positives",
        "recall_excluding_13_repeat_positives",
        "accuracy",
    ):
        report = result[key]
        assert report["value"] == 1.0
        assert report["ci_95_upper"] == 1.0
        assert 0.0 <= report["ci_95_lower"] <= 1.0

    for _tier, t in result["per_tier"].items():
        if t["reportable"]:
            assert t["precision"]["value"] == 1.0
            assert t["recall"]["value"] == 1.0
            assert t["f1"] == 1.0
        else:
            assert "note" in t and "recall not computable" in t["note"]
            # a perfect predictor makes zero false positives everywhere, including tiers with
            # too few positives to report recall/precision for -- except a tier with zero
            # negatives too (trivial_spot_check), where the rate is undefined (0/0), not 0.0.
            if t["n_neg"] > 0:
                assert t["false_positive_rate"]["value"] == 0.0
            else:
                assert t["false_positive_rate"]["value"] is None


def test_always_m_predictor() -> None:
    predictions = {e["pair_id"]: 1.0 for e in ENTRIES}
    result = sp.score(ENTRIES, predictions, threshold=0.5)

    assert result["recall_all_positives"]["value"] == 1.0
    assert result["recall_all_positives"]["n"] == N_POS
    assert result["precision"]["value"] == pytest.approx(N_POS / len(SCORED_ENTRIES))
    assert result["precision"]["n"] == len(SCORED_ENTRIES)

    cm = result["confusion_matrix"]
    assert cm["tp"] == N_POS
    assert cm["fp"] == N_NEG
    assert cm["fn"] == 0
    assert cm["tn"] == 0

    for _tier, t in result["per_tier"].items():
        if t["n_pos"] == 0:
            # a tier with zero positives must never print a recall figure -- always-M makes
            # every one of its negatives a false positive, so FP rate must be exactly 1.0
            # (unless the tier also has zero negatives, in which case n=0 and the value is None).
            assert not t["reportable"]
            assert "recall not computable, n_pos = 0" in t["note"]
            if t["n_neg"] > 0:
                assert t["false_positive_rate"]["value"] == 1.0
            else:
                assert t["false_positive_rate"]["value"] is None


def test_always_n_predictor() -> None:
    predictions = {e["pair_id"]: 0.0 for e in ENTRIES}
    result = sp.score(ENTRIES, predictions, threshold=0.5)

    assert result["recall_all_positives"]["value"] == 0.0
    assert result["recall_all_positives"]["n"] == N_POS
    # precision is undefined (tp + fp == 0), never reported as 0 or NaN
    assert result["precision"]["value"] is None
    assert result["precision"]["n"] == 0
    assert "undefined" in result["precision"]["note"]
    # F1 must reflect precision being undefined, not silently become 0.0
    assert result["f1"]["value"] is None

    cm = result["confusion_matrix"]
    assert cm == {"tp": 0, "fp": 0, "fn": N_POS, "tn": N_NEG}


def test_random_predictor_reproducible_at_fixed_seed() -> None:
    def _predictions_for_seed(seed: int) -> dict[str, float]:
        rng = random.Random(seed)
        return {pair_id: rng.random() for pair_id in sorted(ALL_PAIR_IDS)}

    result_a = sp.score(ENTRIES, _predictions_for_seed(1234), threshold=0.5)
    result_b = sp.score(ENTRIES, _predictions_for_seed(1234), threshold=0.5)
    assert json.dumps(result_a, sort_keys=True) == json.dumps(result_b, sort_keys=True)

    result_c = sp.score(ENTRIES, _predictions_for_seed(9999), threshold=0.5)
    # not asserting inequality of every field (a coincidence is theoretically possible), just that
    # the confusion matrix differs for a different seed, which is true for this dataset/threshold.
    assert result_a["confusion_matrix"] != result_c["confusion_matrix"]


def test_recall_excluding_repeats_diverges_from_recall_all_when_repeats_are_wrong() -> None:
    """Constructs a predictor that gets every real positive right EXCEPT the 13 duplicated
    trivial_spot_check-derived proxy_key_collision positives -- recall_all_positives must drop
    below 1.0 while recall_excluding_13_repeat_positives stays at 1.0, proving the two numbers are
    actually computed differently, not just two names for the same value."""
    repeat_ids = {
        e["pair_id"]
        for e in SCORED_ENTRIES
        if e["label"] == "M" and e["is_repeat"] and e["tier"] == "proxy_key_collision"
    }
    assert len(repeat_ids) == 13

    predictions = {
        e["pair_id"]: (0.0 if e["pair_id"] in repeat_ids else (1.0 if e["label"] == "M" else 0.0))
        for e in ENTRIES
    }
    result = sp.score(ENTRIES, predictions, threshold=0.5)

    assert result["recall_all_positives"]["value"] == pytest.approx((N_POS - 13) / N_POS)
    assert result["recall_excluding_13_repeat_positives"]["value"] == 1.0
    assert result["recall_excluding_13_repeat_positives"]["n"] == N_POS - 13


def test_tier_reportability_threshold_matches_min_positives_constant() -> None:
    predictions = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    result = sp.score(ENTRIES, predictions, threshold=0.5)
    for _tier, t in result["per_tier"].items():
        if t["n_pos"] < sp.MIN_POSITIVES_FOR_FULL_METRICS:
            assert not t["reportable"]
            assert "precision" not in t
            assert "recall" not in t
        else:
            assert t["reportable"]
            assert "false_positive_rate" not in t


def test_no_zero_positive_tier_ever_prints_a_recall_figure() -> None:
    for predictor_name, score_fn in (
        ("perfect", lambda e: 1.0 if e["label"] == "M" else 0.0),
        ("always_m", lambda e: 1.0),
        ("always_n", lambda e: 0.0),
    ):
        predictions = {e["pair_id"]: score_fn(e) for e in ENTRIES}
        result = sp.score(ENTRIES, predictions, threshold=0.5)
        for tier, t in result["per_tier"].items():
            if t["n_pos"] == 0:
                assert not t["reportable"], f"{predictor_name}/{tier} reported recall with n_pos=0"
                assert "recall" not in t


# ---------------------------------------------------------------------------
# TASK 4 rules enforced by main()/CLI-level behaviour
# ---------------------------------------------------------------------------


def test_missing_pair_id_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    predictions = {e["pair_id"]: 0.5 for e in ENTRIES}
    del predictions[ALL_PAIR_IDS[0]]
    with pytest.raises(SystemExit):
        _run_main(tmp_path, monkeypatch, predictions, model_id="missing-pair-test")


def test_extra_pair_id_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    predictions = {e["pair_id"]: 0.5 for e in ENTRIES}
    predictions["not-a-real-pair-id"] = 0.5
    with pytest.raises(SystemExit):
        _run_main(tmp_path, monkeypatch, predictions, model_id="extra-pair-test")


def test_predictions_missing_and_extra_both_reported_in_one_refusal() -> None:
    predictions = {e["pair_id"]: 0.5 for e in ENTRIES}
    del predictions[ALL_PAIR_IDS[0]]
    predictions["bogus-id"] = 0.5
    with pytest.raises(SystemExit, match="1 missing, 1 unexpected"):
        sp._validate_predictions_cover_exactly(predictions, ENTRIES)


def test_scoring_same_model_id_twice_is_refused_without_rescore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predictions = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    _run_main(tmp_path, monkeypatch, predictions, model_id="dup-model")
    with pytest.raises(SystemExit, match="already has"):
        _run_main(tmp_path, monkeypatch, predictions, model_id="dup-model")


def test_rescore_without_reason_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    predictions = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    _run_main(tmp_path, monkeypatch, predictions, model_id="rescore-model")
    with pytest.raises(SystemExit, match="requires --reason"):
        _run_main(
            tmp_path, monkeypatch, predictions, model_id="rescore-model", extra_args=["--rescore"]
        )


def test_rescore_with_reason_is_allowed_and_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _isolate_results_dir: Path
) -> None:
    predictions = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    _run_main(tmp_path, monkeypatch, predictions, model_id="rescore-ok")
    _run_main(
        tmp_path,
        monkeypatch,
        predictions,
        model_id="rescore-ok",
        extra_args=["--rescore", "--reason", "fixed a bug in my model wrapper"],
    )
    ledger = json.loads(sp.LEDGER_JSON.read_text(encoding="utf-8"))
    entries = [e for e in ledger["entries"] if e["model_id"] == "rescore-ok"]
    assert len(entries) == 2
    assert entries[1]["rescore"] is True
    assert entries[1]["reason"] == "fixed a bug in my model wrapper"


def test_different_model_ids_each_get_their_own_ledger_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _isolate_results_dir: Path
) -> None:
    predictions = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    _run_main(tmp_path, monkeypatch, predictions, model_id="model-a")
    _run_main(tmp_path, monkeypatch, predictions, model_id="model-b")
    ledger = json.loads(sp.LEDGER_JSON.read_text(encoding="utf-8"))
    assert {e["model_id"] for e in ledger["entries"]} == {"model-a", "model-b"}


def test_refuses_when_eval_view_hash_does_not_match_live_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_view = tmp_path / "eval-view.json"
    fake_view.write_text(
        json.dumps({"frozen": True, "frozen_labels_sha256": "deadbeef" * 8, "entries": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(sp, "EVAL_VIEW_JSON", fake_view)
    with pytest.raises(SystemExit, match="REFUSING TO RUN"):
        sp._load_eval_view()


def test_refuses_when_eval_view_reports_unfrozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_view = tmp_path / "eval-view.json"
    fake_view.write_text(
        json.dumps({"frozen": False, "frozen_labels_sha256": sp._frozen_marker(), "entries": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(sp, "EVAL_VIEW_JSON", fake_view)
    with pytest.raises(SystemExit, match="not frozen"):
        sp._load_eval_view()


def test_wrong_test_pair_count_refuses() -> None:
    view = {"entries": [{"split": "test", "pair_id": "only-one"}]}
    with pytest.raises(SystemExit, match="expected 287"):
        sp._test_entries(view)


def test_threshold_is_always_a_required_cli_argument(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """score_predictions.py must never select a threshold itself -- the one place it could dodge
    that is by defaulting --threshold instead of requiring it. Calling main() without
    --threshold must fail at argparse's own required-argument check, before any scoring runs."""
    predictions = {e["pair_id"]: 0.5 for e in ENTRIES}
    pred_path = _write_predictions(tmp_path, predictions)
    monkeypatch.setattr(
        sys,
        "argv",
        ["score_predictions.py", "--predictions", str(pred_path), "--model-id", "no-threshold"],
    )
    with pytest.raises(SystemExit):
        sp.main()


def test_score_never_reads_a_threshold_from_anywhere_but_its_argument() -> None:
    """A direct regression pin on rule 8: score() takes threshold as a plain parameter with no
    default, so it structurally cannot supply its own."""
    import inspect

    sig = inspect.signature(sp.score)
    assert sig.parameters["threshold"].default is inspect.Parameter.empty


def test_full_markdown_table_prints_for_perfect_predictor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    predictions = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    _run_main(tmp_path, monkeypatch, predictions, model_id="perfect-markdown-check")
    out = capsys.readouterr().out
    assert "## Scoring results: perfect-markdown-check" in out
    assert "| precision |" in out
    assert "Confusion matrix" in out
    assert "Per-tier:" in out


# ---------------------------------------------------------------------------
# Regression tests for reviewer-found bugs (blocking crash, ledger ordering,
# NaN/non-numeric scores, unaudited --rescore threshold drift, overwrite of
# evidence on rescore).
# ---------------------------------------------------------------------------


def test_markdown_does_not_crash_when_a_reportable_tier_has_undefined_precision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Regression pin: an always-N predictor makes tp==fp==0 in EVERY tier, including the two
    reportable ones (proxy_key_collision, blocked_retrieval_candidate -- n_pos >= 5), so their
    precision value is None. print_markdown previously formatted it with `:.3f` unconditionally
    and crashed with TypeError -- after the TEST touch had already been spent scoring it."""
    predictions = {e["pair_id"]: 0.0 for e in ENTRIES}
    _run_main(tmp_path, monkeypatch, predictions, model_id="always-n-markdown-check")
    out = capsys.readouterr().out
    assert "P=undefined" in out
    assert "proxy_key_collision" in out


def test_ledger_entry_recorded_even_if_printing_the_report_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _isolate_results_dir: Path
) -> None:
    """Regression pin: the ledger must record a TEST touch as soon as score() succeeds, not only
    after print_markdown finishes -- otherwise a crash mid-print (such as the one fixed above)
    leaves TEST touched with no ledger record, and a retry without --rescore is wrongly allowed."""
    predictions = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    pred_path = _write_predictions(tmp_path, predictions)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "score_predictions.py",
            "--predictions",
            str(pred_path),
            "--threshold",
            "0.5",
            "--model-id",
            "print-crash-model",
        ],
    )

    real_print_markdown = sp.print_markdown

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("simulated crash while printing the report")

    monkeypatch.setattr(sp, "print_markdown", boom)
    with pytest.raises(RuntimeError):
        sp.main()

    ledger = json.loads(sp.LEDGER_JSON.read_text(encoding="utf-8"))
    assert any(e["model_id"] == "print-crash-model" for e in ledger["entries"])

    # restore the real print_markdown -- only that one attribute, so the RESULTS_DIR/LEDGER_JSON
    # isolation the autouse fixture set up on this same monkeypatch instance stays in place.
    monkeypatch.setattr(sp, "print_markdown", real_print_markdown)
    with pytest.raises(SystemExit, match="already has"):
        _run_main(tmp_path, monkeypatch, predictions, model_id="print-crash-model")


def test_rescore_at_a_different_threshold_prints_a_warning_to_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    predictions = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    _run_main(tmp_path, monkeypatch, predictions, model_id="threshold-drift-model", threshold=0.5)
    capsys.readouterr()  # discard first run's output
    _run_main(
        tmp_path,
        monkeypatch,
        predictions,
        model_id="threshold-drift-model",
        threshold=0.7,
        extra_args=["--rescore", "--reason", "trying a different threshold"],
    )
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "tuning against TEST" in err


def test_rescore_at_the_same_threshold_prints_no_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    predictions = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    _run_main(tmp_path, monkeypatch, predictions, model_id="same-threshold-model", threshold=0.5)
    capsys.readouterr()
    _run_main(
        tmp_path,
        monkeypatch,
        predictions,
        model_id="same-threshold-model",
        threshold=0.5,
        extra_args=["--rescore", "--reason", "re-running the exact same thing"],
    )
    err = capsys.readouterr().err
    assert "WARNING" not in err


def test_rescore_writes_a_separate_metrics_file_not_overwriting_the_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _isolate_results_dir: Path
) -> None:
    predictions_v1 = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    _run_main(tmp_path, monkeypatch, predictions_v1, model_id="rescore-file-model", threshold=0.5)
    first_path = _isolate_results_dir / "rescore-file-model-metrics.json"
    assert first_path.exists()
    first_content = json.loads(first_path.read_text(encoding="utf-8"))

    predictions_v2 = {e["pair_id"]: 0.0 for e in ENTRIES}  # a materially different model
    _run_main(
        tmp_path,
        monkeypatch,
        predictions_v2,
        model_id="rescore-file-model",
        threshold=0.5,
        extra_args=["--rescore", "--reason", "second model version"],
    )
    second_path = _isolate_results_dir / "rescore-file-model-rescore1-metrics.json"
    assert second_path.exists()

    # the first touch's evidence must survive the second run byte-for-byte
    assert json.loads(first_path.read_text(encoding="utf-8")) == first_content
    assert (
        json.loads(second_path.read_text(encoding="utf-8"))["confusion_matrix"]
        != (first_content["confusion_matrix"])
    )


def test_nan_prediction_value_is_refused_not_silently_scored_as_n(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predictions = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    predictions[ALL_PAIR_IDS[0]] = float("nan")
    with pytest.raises(SystemExit, match="non-finite or non-numeric"):
        _run_main(tmp_path, monkeypatch, predictions, model_id="nan-score-model")


def test_non_numeric_prediction_value_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    predictions: dict[str, object] = {
        e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES
    }
    predictions[ALL_PAIR_IDS[0]] = "0.9"
    pred_path = tmp_path / "preds.json"
    pred_path.write_text(json.dumps(predictions), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "score_predictions.py",
            "--predictions",
            str(pred_path),
            "--threshold",
            "0.5",
            "--model-id",
            "string-score-model",
        ],
    )
    with pytest.raises(SystemExit, match="non-finite or non-numeric"):
        sp.main()


def test_n_repeat_positives_excluded_is_reported_and_matches_the_real_count() -> None:
    predictions = {e["pair_id"]: (1.0 if e["label"] == "M" else 0.0) for e in ENTRIES}
    result = sp.score(ENTRIES, predictions, threshold=0.5)
    assert result["n_repeat_positives_excluded"] == 13
