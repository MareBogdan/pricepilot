r"""Phase 3 item 7 (CLAUDE.md §7): pick 10 representative failures of the WINNING model, by a
stated deterministic rule -- not by hand, not cherry-picked.

    uv run python scripts/select_failure_cases.py

"Winning" here means only: the higher TEST F1 (read from the TEST-touch ledger) of the two
fine-tuned models. `docs/learned/phase3-model-comparison.md` shows that difference is NOT
statistically significant; the winner is used purely as a deterministic way to choose whose
errors to inspect, never as a claim of superiority.

THE RULE (also written into the generated document):
  1. Errors = scored TEST pairs where the winner's prediction (score >= its ledger threshold)
     differs from the label. S-labelled pairs are excluded (they are not scored).
  2. Group errors by tier. Order the tiers that contain errors by error count, descending; ties
     broken by the fixed `TIER_ORDER`.
  3. Within a tier, order errors by confidence: |score - threshold|, largest first (the model was
     most sure, so the error is the most informative); ties broken by pair_id.
  4. Take round-robin: the top error of each tier in tier order, then the second of each, and so
     on, until 10 are chosen (or errors run out).

Nothing here reads a hand-picked id. The only hand-written input is the optional causes file
`docs/learned/phase3-failure-causes.json` ({pair_id: one sentence}); a case with no entry is
printed as "cause not yet written", and the selection never depends on that file.

Outputs: `docs/learned/results/phase3-failure-cases.json` and `docs/learned/phase3-failure-analysis.md`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_eval_view import TIER_ORDER  # noqa: E402
from compare_models import CROSS_ENCODER, LLM  # noqa: E402
from export_model_inputs import _listings_by_occurrence_id  # noqa: E402
from pricepilot.matching.pair_text import ATTRIBUTE_FIELDS  # noqa: E402
from score_predictions import LEDGER_JSON, RESULTS_DIR, _load_eval_view, _test_entries  # noqa: E402

PRED_FILES = {
    CROSS_ENCODER: RESULTS_DIR / "predictions" / "preds-finetuned-test.json",
    LLM: RESULTS_DIR / "predictions" / "preds-llm-test.json",
}
CAUSES_JSON = ROOT / "docs" / "learned" / "phase3-failure-causes.json"
OUT_JSON = RESULTS_DIR / "phase3-failure-cases.json"
OUT_MD = ROOT / "docs" / "learned" / "phase3-failure-analysis.md"
N_CASES = 10
# Shown in addition to the ten model-input attributes, because they can differ between listings
# even though the models never see them.
EXTRA_FIELDS = ("species", "breed_size_class")


def _differing_attributes(left: dict[str, Any], right: dict[str, Any]) -> dict[str, list[Any]]:
    return {
        f: [left.get(f), right.get(f)]
        for f in (*ATTRIBUTE_FIELDS, *EXTRA_FIELDS)
        if left.get(f) != right.get(f)
    }


def main() -> int:
    ledger = {
        e["model_id"]: e for e in json.loads(LEDGER_JSON.read_text(encoding="utf-8"))["entries"]
    }
    threshold = {m: float(ledger[m]["threshold"]) for m in PRED_FILES}
    f1 = {m: float(ledger[m]["f1"]) for m in PRED_FILES}
    winner = max(PRED_FILES, key=lambda m: f1[m])
    other = next(m for m in PRED_FILES if m != winner)
    preds = {m: json.loads(p.read_text(encoding="utf-8")) for m, p in PRED_FILES.items()}

    view = _load_eval_view()
    scored = [e for e in _test_entries(view) if e["scored"]]

    def predicted(m: str, pid: str) -> str:
        return "M" if preds[m][pid] >= threshold[m] else "N"

    errors = [e for e in scored if predicted(winner, e["pair_id"]) != e["label"]]

    def confidence(e: dict[str, Any]) -> float:
        return float(abs(preds[winner][e["pair_id"]] - threshold[winner]))

    by_tier: dict[str, list[dict[str, Any]]] = {}
    for e in errors:
        by_tier.setdefault(e["tier"], []).append(e)
    for lst in by_tier.values():
        lst.sort(key=lambda e: (-confidence(e), e["pair_id"]))
    tier_order = sorted(by_tier, key=lambda t: (-len(by_tier[t]), TIER_ORDER.index(t)))

    chosen: list[dict[str, Any]] = []
    depth = 0
    while len(chosen) < N_CASES and any(len(by_tier[t]) > depth for t in tier_order):
        for t in tier_order:
            if len(chosen) < N_CASES and len(by_tier[t]) > depth:
                chosen.append(by_tier[t][depth])
        depth += 1

    listings = _listings_by_occurrence_id()
    causes: dict[str, str] = (
        json.loads(CAUSES_JSON.read_text(encoding="utf-8")) if CAUSES_JSON.exists() else {}
    )

    cases: list[dict[str, Any]] = []
    for rank, e in enumerate(chosen, 1):
        left, right = listings[e["first_occurrence_id"]]
        pid = e["pair_id"]
        cases.append(
            {
                "rank": rank,
                "pair_id": pid,
                "tier": e["tier"],
                "true_label": e["label"],
                "error_type": "false positive" if e["label"] == "N" else "false negative",
                "title_a": left["title"],
                "title_b": right["title"],
                "differing_attributes": _differing_attributes(left, right),
                "scores": {m: preds[m][pid] for m in PRED_FILES},
                "predictions": {m: predicted(m, pid) for m in PRED_FILES},
                "winner_distance_from_threshold": confidence(e),
                "cause": causes.get(pid),
            }
        )

    out = {
        "built_from": "scripts/select_failure_cases.py",
        "winner_by_test_f1": winner,
        "f1": f1,
        "thresholds": threshold,
        "n_winner_errors": len(errors),
        "errors_per_tier": {t: len(by_tier[t]) for t in tier_order},
        "cases": cases,
    }
    OUT_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")

    md = [
        "# Phase 3 failure analysis (CLAUDE.md §7 item 7)\n",
        f"Model inspected: **{winner}** (TEST F1 {f1[winner]:.4f} vs {f1[other]:.4f} for "
        f"{other}). It is inspected only because its point F1 is higher; the difference is not "
        "statistically significant (`phase3-model-comparison.md`), so this is not a claim that "
        "it is the better model.\n",
        f"Its errors on the {len(scored)} scored TEST pairs: **{len(errors)}** "
        f"(per tier: {', '.join(f'{t} {len(by_tier[t])}' for t in tier_order)}).\n",
        "## Selection rule (deterministic, scripts/select_failure_cases.py)\n",
        "1. Errors = scored TEST pairs where the model's prediction (score >= its ledger "
        "threshold) differs from the label.",
        "2. Tiers containing errors ordered by error count (descending), ties by the fixed tier "
        "order.",
        "3. Within a tier, errors ordered by confidence = |score - threshold| (largest first), "
        "ties by pair_id.",
        f"4. Round-robin over tiers (top error of each, then second of each, ...) until {N_CASES} "
        "are chosen.\n",
        "Cause sentences are hand-written from the displayed data only "
        "(`docs/learned/phase3-failure-causes.json`); selection never reads that file.\n",
    ]
    for c in cases:
        s = c["scores"]
        md.append(f"## Case {c['rank']} -- {c['tier']} -- {c['error_type']}\n")
        md.append(f"- pair_id: `{c['pair_id']}`  true label: **{c['true_label']}**")
        md.append(f"- title A: {c['title_a']}")
        md.append(f"- title B: {c['title_b']}")
        diff = c["differing_attributes"]
        md.append(
            "- differing extracted attributes (A vs B): "
            + ("; ".join(f"{k}: {v[0]!r} vs {v[1]!r}" for k, v in diff.items()) or "none")
        )
        md.append(
            f"- scores: {winner} {s[winner]:.4f} (t={threshold[winner]}, predicted "
            f"{c['predictions'][winner]}); {other} {s[other]:.4f} (t={threshold[other]}, "
            f"predicted {c['predictions'][other]}); distance of {winner} from its threshold "
            f"{c['winner_distance_from_threshold']:.4f}"
        )
        md.append(f"- plausible cause: {c['cause'] or '(cause not yet written)'}\n")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    print(f"winner by TEST F1: {winner}; errors: {len(errors)}; per tier: {out['errors_per_tier']}")
    for c in cases:
        print(
            f"{c['rank']:>2}. {c['tier']:<32} {c['error_type']:<15} {c['pair_id']}  "
            f"dist={c['winner_distance_from_threshold']:.3f}"
        )
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
