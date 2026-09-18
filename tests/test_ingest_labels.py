"""Phase 3 STEP 8 (ADR-0028 addendum #12, TASK 3) -- tests for scripts/ingest_labels.py.

Every fixture here is SYNTHETIC, built by this test file, never real annotation output --
`FIXTURE_` prefixes make that explicit in variable names. Real labels never enter the test suite
(CLAUDE.md's own discipline: no AI-produced or fabricated data may pass as a real measurement).
These tests exercise the ingest pipeline's control flow (clean run / conflict / SHA mismatch /
TEST-with-suggestion violation / partial run) against a small synthetic queue+split, not against
the real frozen queue -- `FROZEN_QUEUE_SHA256` and every file path the script reads/writes are
monkeypatched to point at a synthetic dataset the test builds under `tmp_path`, so no test run can
ever write into the real `docs/learned/` directory.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "ingest_labels_under_test", ROOT / "scripts" / "ingest_labels.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec: dataclasses.dataclass() looks up
    # sys.modules[cls.__module__] while processing @dataclass-decorated classes in the module
    # body, and fails with a confusing AttributeError if the module isn't registered yet.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


il = _load_module()


# --- synthetic fixture builders --------------------------------------------------------------

FIXTURE_QUEUE_PAIRS = [
    {
        "pair_id": "FIXTURE_pair_test_1",
        "tier": "blocked_retrieval_candidate",
        "left": {"content_hash": "h1"},
        "right": {"content_hash": "h2"},
    },
    {
        "pair_id": "FIXTURE_pair_trainval_1",
        "tier": "capacity_differs_cross_shop",
        "left": {"content_hash": "h3"},
        "right": {"content_hash": "h4"},
    },
    {
        "pair_id": "FIXTURE_pair_trainval_2",
        "tier": "capacity_differs_cross_shop",
        "left": {"content_hash": "h5"},
        "right": {"content_hash": "h6"},
    },
]


def _write_synthetic_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    # Must be ROOT/"docs"/"learned" (not some other tmp subdirectory): main() computes the QA
    # report path fresh as `ROOT / "docs" / "learned" / ...` on every call, and `ROOT` below is
    # monkeypatched to `tmp_path` -- so this is where the script will actually look/write.
    learned = tmp_path / "docs" / "learned"
    learned.mkdir(parents=True)

    queue_path = learned / "FIXTURE-queue.json"
    queue_bytes = json.dumps({"pairs": FIXTURE_QUEUE_PAIRS, "shuffle_seed": 1}, indent=1).encode(
        "utf-8"
    )
    queue_path.write_bytes(queue_bytes)
    queue_sha256 = hashlib.sha256(queue_bytes).hexdigest()

    split_path = learned / "FIXTURE-split.json"
    split_bytes = json.dumps(
        {
            "assignments": {
                "FIXTURE_pair_test_1_0": {
                    "split": "test",
                    "tier": "blocked_retrieval_candidate",
                    "pair_id": "FIXTURE_pair_test_1",
                },
                "FIXTURE_pair_trainval_1_0": {
                    "split": "train_val",
                    "tier": "capacity_differs_cross_shop",
                    "pair_id": "FIXTURE_pair_trainval_1",
                    "engine_prediction": {"label": "N", "rule": "rule2_quantity_differs"},
                },
                "FIXTURE_pair_trainval_2_0": {
                    "split": "train_val",
                    "tier": "capacity_differs_cross_shop",
                    "pair_id": "FIXTURE_pair_trainval_2",
                    "engine_prediction": {"label": "M", "rule": "default_M"},
                },
            }
        },
        indent=1,
    ).encode("utf-8")
    split_path.write_bytes(split_bytes)
    split_sha256 = hashlib.sha256(split_bytes).hexdigest()

    test_reference_path = learned / "FIXTURE-test-reference.json"
    test_reference_path.write_text(
        json.dumps(
            {
                "predictions": {
                    "FIXTURE_pair_test_1_0": {
                        "pair_id": "FIXTURE_pair_test_1",
                        "engine_prediction": {"label": "M", "rule": "default_M"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    labels_out_path = learned / "FIXTURE-labels.json"

    monkeypatch.setattr(il, "QUEUE_JSON", queue_path)
    monkeypatch.setattr(il, "SPLIT_JSON", split_path)
    monkeypatch.setattr(il, "TEST_REFERENCE_JSON", test_reference_path)
    monkeypatch.setattr(il, "REPEAT_LOOKUP_JSON", learned / "does-not-exist.json")
    monkeypatch.setattr(il, "LABELS_JSON", labels_out_path)
    monkeypatch.setattr(il, "ROOT", tmp_path)
    monkeypatch.setattr(il, "FROZEN_QUEUE_SHA256", queue_sha256)

    return {
        "learned": learned,
        "queue_path": queue_path,
        "split_path": split_path,
        "labels_out_path": labels_out_path,
        "queue_sha256": queue_sha256,
        "split_sha256": split_sha256,
    }


def _write_export(
    path: Path,
    queue_sha256: str,
    split_sha256: str,
    state: dict[str, dict[str, Any]],
    exported_at: str = "2026-09-18T10:00:00.000Z",
) -> None:
    path.write_text(
        json.dumps(
            {
                "queue_sha256": queue_sha256,
                "split_sha256": split_sha256,
                "decision_count": len(state),
                "exported_at": exported_at,
                "state": state,
            }
        ),
        encoding="utf-8",
    )


def _decision(
    pair_id: str,
    tier: str,
    split: str,
    answer: str,
    source: str,
    *,
    engine_prediction: dict[str, str] | None = None,
    corrected: bool = False,
    ms: int = 5000,
    decided_at: str = "2026-09-18T10:00:00.000Z",
) -> dict[str, Any]:
    return {
        "pair_id": pair_id,
        "tier": tier,
        "split": split,
        "answer": answer,
        "source": source,
        "engine_prediction": engine_prediction,
        "corrected": corrected,
        "flagged": False,
        "s_reason": None,
        "ms": ms,
        "decided_at": decided_at,
    }


# --- 1. clean run -------------------------------------------------------------------------------


def test_clean_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ds = _write_synthetic_dataset(tmp_path, monkeypatch)
    export_path = ds["learned"] / "FIXTURE-export-clean.json"
    _write_export(
        export_path,
        ds["queue_sha256"],
        ds["split_sha256"],
        {
            "FIXTURE_pair_test_1_0": _decision(
                "FIXTURE_pair_test_1", "blocked_retrieval_candidate", "test", "M", "blind"
            ),
            "FIXTURE_pair_trainval_1_0": _decision(
                "FIXTURE_pair_trainval_1",
                "capacity_differs_cross_shop",
                "train_val",
                "N",
                "confirm",
                engine_prediction={"label": "N", "rule": "rule2_quantity_differs"},
                corrected=False,
            ),
        },
    )

    rc = il.main([str(export_path)])
    assert rc == 0

    out = json.loads(ds["labels_out_path"].read_text(encoding="utf-8"))
    assert out["decision_count"] == 2
    assert out["decisions"]["FIXTURE_pair_test_1_0"]["label"] == "M"
    assert out["decisions"]["FIXTURE_pair_trainval_1_0"]["label"] == "N"
    assert out["queue_sha256"] == ds["queue_sha256"]
    assert out["split_sha256"] == ds["split_sha256"]

    qa_files = list((tmp_path / "docs" / "learned").glob("phase3-label-qa-*.md"))
    assert len(qa_files) == 1
    qa_text = qa_files[0].read_text(encoding="utf-8")
    assert "Coverage" in qa_text
    assert "Label distribution" in qa_text


# --- 2. conflict ----------------------------------------------------------------------------


def test_conflict_refused_without_resolve_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ds = _write_synthetic_dataset(tmp_path, monkeypatch)
    export_a = ds["learned"] / "FIXTURE-export-a.json"
    export_b = ds["learned"] / "FIXTURE-export-b.json"
    _write_export(
        export_a,
        ds["queue_sha256"],
        ds["split_sha256"],
        {
            "FIXTURE_pair_trainval_1_0": _decision(
                "FIXTURE_pair_trainval_1",
                "capacity_differs_cross_shop",
                "train_val",
                "N",
                "confirm",
                engine_prediction={"label": "N", "rule": "rule2_quantity_differs"},
                decided_at="2026-09-18T10:00:00.000Z",
            )
        },
    )
    _write_export(
        export_b,
        ds["queue_sha256"],
        ds["split_sha256"],
        {
            "FIXTURE_pair_trainval_1_0": _decision(
                "FIXTURE_pair_trainval_1",
                "capacity_differs_cross_shop",
                "train_val",
                "S",
                "override",
                engine_prediction={"label": "N", "rule": "rule2_quantity_differs"},
                corrected=True,  # answer "S" != suggested "N", so decide() sets corrected=True
                decided_at="2026-09-18T11:00:00.000Z",
            )
        },
    )

    with pytest.raises(SystemExit) as exc_info:
        il.main([str(export_a), str(export_b)])
    assert exc_info.value.code == 1
    assert not ds["labels_out_path"].exists()


def test_conflict_resolved_with_latest_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ds = _write_synthetic_dataset(tmp_path, monkeypatch)
    export_a = ds["learned"] / "FIXTURE-export-a.json"
    export_b = ds["learned"] / "FIXTURE-export-b.json"
    _write_export(
        export_a,
        ds["queue_sha256"],
        ds["split_sha256"],
        {
            "FIXTURE_pair_trainval_1_0": _decision(
                "FIXTURE_pair_trainval_1",
                "capacity_differs_cross_shop",
                "train_val",
                "N",
                "confirm",
                engine_prediction={"label": "N", "rule": "rule2_quantity_differs"},
                decided_at="2026-09-18T10:00:00.000Z",
            )
        },
    )
    _write_export(
        export_b,
        ds["queue_sha256"],
        ds["split_sha256"],
        {
            "FIXTURE_pair_trainval_1_0": _decision(
                "FIXTURE_pair_trainval_1",
                "capacity_differs_cross_shop",
                "train_val",
                "S",
                "override",
                engine_prediction={"label": "N", "rule": "rule2_quantity_differs"},
                corrected=True,  # answer "S" != suggested "N", so decide() sets corrected=True
                decided_at="2026-09-18T11:00:00.000Z",
            )
        },
    )

    rc = il.main([str(export_a), str(export_b), "--resolve=latest"])
    assert rc == 0
    out = json.loads(ds["labels_out_path"].read_text(encoding="utf-8"))
    # export_b's decided_at is later -> its label ("S") wins
    assert out["decisions"]["FIXTURE_pair_trainval_1_0"]["label"] == "S"


# --- 3. SHA mismatch ----------------------------------------------------------------------------


def test_queue_sha256_mismatch_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ds = _write_synthetic_dataset(tmp_path, monkeypatch)
    export_path = ds["learned"] / "FIXTURE-export-badhash.json"
    _write_export(
        export_path,
        "0" * 64,  # deliberately wrong
        ds["split_sha256"],
        {
            "FIXTURE_pair_test_1_0": _decision(
                "FIXTURE_pair_test_1", "blocked_retrieval_candidate", "test", "M", "blind"
            )
        },
    )

    with pytest.raises(SystemExit) as exc_info:
        il.main([str(export_path)])
    assert exc_info.value.code == 1
    assert not ds["labels_out_path"].exists()


def test_split_sha256_mismatch_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ds = _write_synthetic_dataset(tmp_path, monkeypatch)
    export_path = ds["learned"] / "FIXTURE-export-badsplithash.json"
    _write_export(
        export_path,
        ds["queue_sha256"],
        "1" * 64,  # deliberately wrong
        {
            "FIXTURE_pair_test_1_0": _decision(
                "FIXTURE_pair_test_1", "blocked_retrieval_candidate", "test", "M", "blind"
            )
        },
    )

    with pytest.raises(SystemExit) as exc_info:
        il.main([str(export_path)])
    assert exc_info.value.code == 1
    assert not ds["labels_out_path"].exists()


# --- 4. TEST-with-suggestion violation -----------------------------------------------------------


def test_test_decision_with_non_blind_source_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ds = _write_synthetic_dataset(tmp_path, monkeypatch)
    export_path = ds["learned"] / "FIXTURE-export-testviolation.json"
    _write_export(
        export_path,
        ds["queue_sha256"],
        ds["split_sha256"],
        {
            # A TEST-split occurrence must always have source="blind" -- this decision
            # (source="confirm") is exactly the shape the real tool can never produce, since a
            # TEST pair is never shown a suggestion to confirm.
            "FIXTURE_pair_test_1_0": _decision(
                "FIXTURE_pair_test_1",
                "blocked_retrieval_candidate",
                "test",
                "M",
                "confirm",
                engine_prediction={"label": "M", "rule": "default_M"},
            )
        },
    )

    with pytest.raises(SystemExit) as exc_info:
        il.main([str(export_path)])
    assert exc_info.value.code == 1
    assert not ds["labels_out_path"].exists()


def test_test_decision_with_populated_engine_prediction_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A code-review finding, not one of the 5 required paths: the real tool structurally never
    attaches an engine_prediction to a TEST row (decide() always writes null there), so an export
    claiming otherwise -- even with source="blind" correctly set -- must be refused too."""
    ds = _write_synthetic_dataset(tmp_path, monkeypatch)
    export_path = ds["learned"] / "FIXTURE-export-test-with-prediction.json"
    _write_export(
        export_path,
        ds["queue_sha256"],
        ds["split_sha256"],
        {
            "FIXTURE_pair_test_1_0": _decision(
                "FIXTURE_pair_test_1",
                "blocked_retrieval_candidate",
                "test",
                "M",
                "blind",
                engine_prediction={"label": "M", "rule": "default_M"},
            )
        },
    )

    with pytest.raises(SystemExit) as exc_info:
        il.main([str(export_path)])
    assert exc_info.value.code == 1
    assert not ds["labels_out_path"].exists()


def test_confirm_with_label_not_matching_suggestion_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A code-review finding, not one of the 5 required paths: confirmSuggestion() in the real
    tool can only ever record the suggested label itself -- an export claiming source="confirm"
    with a different answer is a shape the tool cannot produce."""
    ds = _write_synthetic_dataset(tmp_path, monkeypatch)
    export_path = ds["learned"] / "FIXTURE-export-bad-confirm.json"
    _write_export(
        export_path,
        ds["queue_sha256"],
        ds["split_sha256"],
        {
            "FIXTURE_pair_trainval_1_0": _decision(
                "FIXTURE_pair_trainval_1",
                "capacity_differs_cross_shop",
                "train_val",
                "S",  # suggestion is "N" (see fixture split assignments) -- mismatch
                "confirm",
                engine_prediction={"label": "N", "rule": "rule2_quantity_differs"},
            )
        },
    )

    with pytest.raises(SystemExit) as exc_info:
        il.main([str(export_path)])
    assert exc_info.value.code == 1
    assert not ds["labels_out_path"].exists()


# --- 5. partial run -------------------------------------------------------------------------------


def test_partial_export_ingests_without_complaint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ds = _write_synthetic_dataset(tmp_path, monkeypatch)
    export_path = ds["learned"] / "FIXTURE-export-partial.json"
    _write_export(
        export_path,
        ds["queue_sha256"],
        ds["split_sha256"],
        {
            # Only ONE of the three fixture pairs decided -- the other two (one TEST-eligible
            # slot doesn't exist here, but FIXTURE_pair_trainval_2 is undecided) are simply
            # absent, exactly like a real first-100-of-997 pilot export.
            "FIXTURE_pair_test_1_0": _decision(
                "FIXTURE_pair_test_1", "blocked_retrieval_candidate", "test", "N", "blind"
            )
        },
    )

    rc = il.main([str(export_path)])
    assert rc == 0

    out = json.loads(ds["labels_out_path"].read_text(encoding="utf-8"))
    assert out["decision_count"] == 1
    assert set(out["decisions"].keys()) == {"FIXTURE_pair_test_1_0"}

    qa_files = sorted((tmp_path / "docs" / "learned").glob("phase3-label-qa-*.md"))
    assert len(qa_files) == 1
    qa_text = qa_files[0].read_text(encoding="utf-8")
    # Coverage must show 1/3 decided overall, not complain about the missing 2.
    assert "Coverage" in qa_text
