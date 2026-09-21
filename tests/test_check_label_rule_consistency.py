"""Phase 3 mechanical rule-consistency check tests (DECISIONS.md ADR-0028 addendum #13) --
scripts/check_label_rule_consistency.py.

Every fixture here is SYNTHETIC, built by this test file, never real annotation output --
`FIXTURE_` prefixes make that explicit. These tests exercise the five mechanical classes (a)-(e)
against a small synthetic queue+labels set, never the real frozen queue -- `FROZEN_QUEUE_SHA256`
and every file path the script reads/writes are monkeypatched to a synthetic dataset under
`tmp_path`, so no test run can ever write into the real `docs/learned/` directory.
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
        "check_label_rule_consistency_under_test",
        ROOT / "scripts" / "check_label_rule_consistency.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


clc = _load_module()


def _listing(
    content_hash: str,
    title: str,
    species: str | None = "dog",
    food_form: str | None = "dry",
    net_weight_g: int | None = 400,
    net_volume_ml: int | None = None,
    pack_count: int | None = None,
    bonus_weight_g: int | None = None,
) -> dict[str, Any]:
    return {
        "content_hash": content_hash,
        "title": title,
        "species": species,
        "food_form": food_form,
        "net_weight_g": net_weight_g,
        "net_volume_ml": net_volume_ml,
        "pack_count": pack_count,
        "bonus_weight_g": bonus_weight_g,
    }


# One pair per class, plus a clean pair that must never be flagged by anything.
FIXTURE_PAIRS = [
    {
        "pair_id": "FIXTURE_a",
        "tier": "capacity_differs_cross_shop",
        "left": _listing("ha1", "Brand X Adult Dog Food 400g caini"),
        "right": _listing("ha2", "Brand X Adult Dog Food 800g caini", net_weight_g=800),
    },
    {
        "pair_id": "FIXTURE_b",
        "tier": "diff_brand_similar_title",
        "left": _listing("hb1", "Brand Y Adult Dog Food 400g caini", species="dog"),
        "right": _listing("hb2", "Brand Y Adult Cat Food 400g pisici", species="cat"),
    },
    {
        "pair_id": "FIXTURE_c",
        "tier": "same_capacity_diff_flavour",
        "left": _listing("hc1", "Brand Z Dry Food 400g caini", food_form="dry"),
        "right": _listing("hc2", "Brand Z Wet Pouch 400g caini", food_form="pouch"),
    },
    {
        "pair_id": "FIXTURE_d",
        "tier": "trivial_spot_check",
        "left": _listing("hd1", "Brand W Adult Dog Food 400g caini"),
        "right": _listing("hd2", "Brand W Adult Dog Food 400g caini"),
    },
    {
        "pair_id": "FIXTURE_e",
        "tier": "blocked_retrieval_candidate",
        # field says "dog" but the title unambiguously says "pisici" (cat) -- a species
        # extraction defect. Right side's field agrees with its own title, so rule 1 (species
        # differ, both known) does NOT fire here -- both fields say "dog".
        "left": _listing("he1", "Brand V Adult Food pentru pisici 400g", species="dog"),
        "right": _listing("he2", "Brand V Adult Dog Food 400g caini", species="dog"),
    },
    {
        "pair_id": "FIXTURE_clean",
        "tier": "same_capacity_diff_flavour",
        "left": _listing("hclean1", "Brand U Adult Dog Food 400g caini"),
        "right": _listing("hclean2", "Brand U Adult Dog Food 400g caini"),
    },
]

# Decisions chosen so that every mechanical rule above is CONTRADICTED (label M where the rule
# says N, or vice versa for tier (d)) except FIXTURE_clean, which is left consistent throughout.
FIXTURE_DECISIONS_TRIGGERING = {
    "FIXTURE_a_0": {"pair_id": "FIXTURE_a", "label": "M"},
    "FIXTURE_b_0": {"pair_id": "FIXTURE_b", "label": "M"},
    "FIXTURE_c_0": {"pair_id": "FIXTURE_c", "label": "M"},
    "FIXTURE_d_0": {"pair_id": "FIXTURE_d", "label": "N"},
    "FIXTURE_e_0": {"pair_id": "FIXTURE_e", "label": "M"},
    "FIXTURE_clean_0": {"pair_id": "FIXTURE_clean", "label": "M"},
}

FIXTURE_DECISIONS_CLEAN = {
    "FIXTURE_a_0": {"pair_id": "FIXTURE_a", "label": "N"},
    "FIXTURE_b_0": {"pair_id": "FIXTURE_b", "label": "N"},
    "FIXTURE_c_0": {"pair_id": "FIXTURE_c", "label": "N"},
    "FIXTURE_d_0": {"pair_id": "FIXTURE_d", "label": "M"},
    # FIXTURE_e's underlying species-field defect exists regardless of the label given -- (e) is a
    # data-quality check, not label-dependent -- so it is left out of the "clean" set entirely
    # rather than pretending a label choice could ever silence it.
    "FIXTURE_clean_0": {"pair_id": "FIXTURE_clean", "label": "M"},
}


def _write_synthetic_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, decisions: dict[str, dict[str, Any]]
) -> dict[str, Path]:
    learned = tmp_path / "docs" / "learned"
    learned.mkdir(parents=True)

    queue_path = learned / "FIXTURE-queue.json"
    queue_bytes = json.dumps({"pairs": FIXTURE_PAIRS, "shuffle_seed": 1}, indent=1).encode("utf-8")
    queue_path.write_bytes(queue_bytes)
    queue_sha256 = hashlib.sha256(queue_bytes).hexdigest()

    split_path = learned / "FIXTURE-split.json"
    split_path.write_bytes(b"{}")  # only hashed by the script, never parsed for content here

    labels_path = learned / "FIXTURE-labels.json"
    labels_path.write_text(
        json.dumps(
            {"ingested_at": "2026-09-21T00:00:00+00:00", "decisions": decisions},
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    relabel_queue_path = learned / "FIXTURE-relabel-queue.json"

    monkeypatch.setattr(clc, "QUEUE_JSON", queue_path)
    monkeypatch.setattr(clc, "SPLIT_JSON", split_path)
    monkeypatch.setattr(clc, "LABELS_JSON", labels_path)
    monkeypatch.setattr(clc, "RELABEL_QUEUE_JSON", relabel_queue_path)
    monkeypatch.setattr(clc, "ROOT", tmp_path)
    monkeypatch.setattr(clc, "FROZEN_QUEUE_SHA256", queue_sha256)

    return {"relabel_queue_path": relabel_queue_path}


def _full_decisions(overrides: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fills in the REQUIRED_DECISION-adjacent shape this script actually reads (just pair_id +
    label -- check() never touches the other provenance fields)."""
    return {occ_id: dict(d) for occ_id, d in overrides.items()}


def test_class_a_quantity_differs_but_labelled_m(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_synthetic_dataset(tmp_path, monkeypatch, _full_decisions(FIXTURE_DECISIONS_TRIGGERING))
    pairs_by_occ = dict(
        zip(
            clc.derive_occurrence_ids(FIXTURE_PAIRS),
            FIXTURE_PAIRS,
            strict=True,
        )
    )
    flags = clc.check(pairs_by_occ, FIXTURE_DECISIONS_TRIGGERING)
    a_flags = [f for f in flags if f.cls == "a"]
    assert len(a_flags) == 1
    assert a_flags[0].occurrence_id == "FIXTURE_a_0"


def test_class_b_species_differs_but_labelled_m(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_synthetic_dataset(tmp_path, monkeypatch, _full_decisions(FIXTURE_DECISIONS_TRIGGERING))
    pairs_by_occ = dict(zip(clc.derive_occurrence_ids(FIXTURE_PAIRS), FIXTURE_PAIRS, strict=True))
    flags = clc.check(pairs_by_occ, FIXTURE_DECISIONS_TRIGGERING)
    b_flags = [f for f in flags if f.cls == "b"]
    assert len(b_flags) == 1
    assert b_flags[0].occurrence_id == "FIXTURE_b_0"


def test_class_c_foodform_dry_vs_wet_but_labelled_m(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_synthetic_dataset(tmp_path, monkeypatch, _full_decisions(FIXTURE_DECISIONS_TRIGGERING))
    pairs_by_occ = dict(zip(clc.derive_occurrence_ids(FIXTURE_PAIRS), FIXTURE_PAIRS, strict=True))
    flags = clc.check(pairs_by_occ, FIXTURE_DECISIONS_TRIGGERING)
    c_flags = [f for f in flags if f.cls == "c"]
    assert len(c_flags) == 1
    assert c_flags[0].occurrence_id == "FIXTURE_c_0"


def test_class_d_trivial_spot_check_not_m(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_synthetic_dataset(tmp_path, monkeypatch, _full_decisions(FIXTURE_DECISIONS_TRIGGERING))
    pairs_by_occ = dict(zip(clc.derive_occurrence_ids(FIXTURE_PAIRS), FIXTURE_PAIRS, strict=True))
    flags = clc.check(pairs_by_occ, FIXTURE_DECISIONS_TRIGGERING)
    d_flags = [f for f in flags if f.cls == "d"]
    assert len(d_flags) == 1
    assert d_flags[0].occurrence_id == "FIXTURE_d_0"


def test_class_e_species_title_field_mismatch_never_reported_as_annotator_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_synthetic_dataset(tmp_path, monkeypatch, _full_decisions(FIXTURE_DECISIONS_TRIGGERING))
    pairs_by_occ = dict(zip(clc.derive_occurrence_ids(FIXTURE_PAIRS), FIXTURE_PAIRS, strict=True))
    flags = clc.check(pairs_by_occ, FIXTURE_DECISIONS_TRIGGERING)
    e_flags = [f for f in flags if f.cls == "e"]
    assert len(e_flags) == 1
    assert e_flags[0].occurrence_id == "FIXTURE_e_0"
    assert e_flags[0].note is not None
    assert "never a labelling error" in e_flags[0].note
    # (e) must not fire on FIXTURE_b even though that pair ALSO happens to be flagged (class b) --
    # FIXTURE_b's two species fields disagree with EACH OTHER but each field agrees with its own
    # listing's title, so no title/field mismatch exists there.
    assert not any(f.occurrence_id == "FIXTURE_b_0" and f.cls == "e" for f in flags)


def test_negative_case_clean_labels_flag_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A label set consistent with every mechanical rule (FIXTURE_e's fixed species-field defect
    aside -- see its own fixture comment) must flag nothing at all."""
    clean_pairs = [p for p in FIXTURE_PAIRS if p["pair_id"] != "FIXTURE_e"]
    _write_synthetic_dataset(tmp_path, monkeypatch, _full_decisions(FIXTURE_DECISIONS_CLEAN))
    pairs_by_occ = dict(zip(clc.derive_occurrence_ids(clean_pairs), clean_pairs, strict=True))
    decisions = {k: v for k, v in FIXTURE_DECISIONS_CLEAN.items() if k != "FIXTURE_e_0"}
    flags = clc.check(pairs_by_occ, decisions)
    assert flags == []


def test_main_writes_relabel_queue_grouped_by_occurrence_id_and_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _write_synthetic_dataset(
        tmp_path, monkeypatch, _full_decisions(FIXTURE_DECISIONS_TRIGGERING)
    )
    exit_code = clc.main()
    assert exit_code != 0

    relabel = json.loads(paths["relabel_queue_path"].read_text(encoding="utf-8"))
    assert relabel["class_counts"] == {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1}
    assert relabel["flagged_count"] == 5
    # FIXTURE_b_0 is flagged once, under class "b" only -- FIXTURE_e_0 is the one carrying both
    # a genuine species-differs flag AND the extraction-defect flag in the real data, not this one.
    assert len(relabel["flagged"]["FIXTURE_b_0"]["classes"]) == 1
    assert relabel["flagged"]["FIXTURE_b_0"]["classes"][0]["class"] == "b"
    assert relabel["flagged"]["FIXTURE_e_0"]["classes"][0]["class"] == "e"


def test_main_exits_zero_on_clean_labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clean_pairs = [p for p in FIXTURE_PAIRS if p["pair_id"] != "FIXTURE_e"]
    decisions = {k: v for k, v in FIXTURE_DECISIONS_CLEAN.items() if k != "FIXTURE_e_0"}

    learned = tmp_path / "docs" / "learned"
    learned.mkdir(parents=True)
    queue_path = learned / "FIXTURE-queue.json"
    queue_bytes = json.dumps({"pairs": clean_pairs, "shuffle_seed": 1}, indent=1).encode("utf-8")
    queue_path.write_bytes(queue_bytes)
    queue_sha256 = hashlib.sha256(queue_bytes).hexdigest()
    split_path = learned / "FIXTURE-split.json"
    split_path.write_bytes(b"{}")
    labels_path = learned / "FIXTURE-labels.json"
    labels_path.write_text(
        json.dumps({"ingested_at": "2026-09-21T00:00:00+00:00", "decisions": decisions}, indent=1),
        encoding="utf-8",
    )
    relabel_queue_path = learned / "FIXTURE-relabel-queue.json"

    monkeypatch.setattr(clc, "QUEUE_JSON", queue_path)
    monkeypatch.setattr(clc, "SPLIT_JSON", split_path)
    monkeypatch.setattr(clc, "LABELS_JSON", labels_path)
    monkeypatch.setattr(clc, "RELABEL_QUEUE_JSON", relabel_queue_path)
    monkeypatch.setattr(clc, "ROOT", tmp_path)
    monkeypatch.setattr(clc, "FROZEN_QUEUE_SHA256", queue_sha256)

    exit_code = clc.main()
    assert exit_code == 0
    relabel = json.loads(relabel_queue_path.read_text(encoding="utf-8"))
    assert relabel["flagged_count"] == 0
    assert relabel["flagged"] == {}


def test_queue_sha256_mismatch_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_synthetic_dataset(tmp_path, monkeypatch, _full_decisions(FIXTURE_DECISIONS_CLEAN))
    monkeypatch.setattr(clc, "FROZEN_QUEUE_SHA256", "0" * 64)
    exit_code = clc.main()
    assert exit_code == 1
