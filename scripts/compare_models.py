r"""Phase 3 item 7 (CLAUDE.md §7): the three-model TEST comparison, as code.

    uv run python scripts/compare_models.py

Reads NOTHING new from TEST in the sense that matters: it scores no new model, selects no
threshold and touches no ledger. Every model's threshold is READ from
`docs/learned/results/test-touch-ledger.json` (chosen earlier on validation only by
`scripts/select_threshold.py`), every model's prediction file is the one already scored, and
per-model numbers come from `score_predictions.score()` itself -- so they are the same numbers the
committed `*-metrics.json` files hold (asserted below), not a second implementation. What this
script ADDS is the paired analysis two separately-scored models need:

  * every rate with its denominator and Wilson 95% CI;
  * whether the two fine-tuned models' CIs overlap, computed, per metric;
  * McNemar's exact test on the paired TEST predictions (the correct test for two models on the
    SAME test set), overall and split by true label, with the discordant counts;
  * per-tier correct/n with CI, and per-tier discordant counts.

Output: `docs/learned/results/phase3-model-comparison.json`, and the generated tables are written
between the `BEGIN/END GENERATED` markers of `docs/learned/phase3-model-comparison.md` (the prose
outside the markers is hand-written and is never touched by this script).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_eval_view import TIER_ORDER  # noqa: E402
from pricepilot.matching.metrics import (  # noqa: E402
    intervals_overlap,
    mcnemar_exact_p,
    wilson_confidence_interval,
)
from score_predictions import (  # noqa: E402
    LEDGER_JSON,
    RESULTS_DIR,
    _load_eval_view,
    _test_entries,
    score,
)

PRED_DIR = RESULTS_DIR / "predictions"
OUTPUT_JSON = RESULTS_DIR / "phase3-model-comparison.json"
OUTPUT_MD = ROOT / "docs" / "learned" / "phase3-model-comparison.md"
BEGIN = "<!-- BEGIN GENERATED (scripts/compare_models.py) -->"
END = "<!-- END GENERATED -->"

# The two fine-tuned models the pre-registered decision rule compares; zero-shot is context only.
CROSS_ENCODER = "mmarco-mMiniLMv2-finetuned-ep6"
LLM = "qwen2.5-0.5b-lora-ep8"

MODELS: list[dict[str, str]] = [
    {
        "model_id": "mmarco-mMiniLMv2-zeroshot",
        "label": "Cross-encoder mMiniLMv2, zero-shot",
        "preds": "preds-zeroshot-test.json",
        # Facts below are hardcoded from the recorded runs (the annotator's Kaggle log, transcribed in
        # DECISIONS.md ADR-0028 #20 / #22; the log itself is not committed), not measured here;
        # each carries its source. UNVERIFIED / ESTIMATE labels are kept.
        "params_trained": "0 (no training)",
        "artefact": "n/a (no training artefact)",
        "wall_clock": "0 (no training)",
    },
    {
        "model_id": CROSS_ENCODER,
        "label": "Cross-encoder mMiniLMv2, fine-tuned (epoch 6)",
        "preds": "preds-finetuned-test.json",
        "params_trained": "all weights, ~0.1B (model card rounds; exact UNVERIFIED)",
        "artefact": "not recorded",
        "wall_clock": "~1 hour on Kaggle CPU (approximate; ADR-0028 #20; accelerator had reset)",
    },
    {
        "model_id": LLM,
        "label": "LoRA Qwen2.5-0.5B-Instruct (epoch 8)",
        "preds": "preds-llm-test.json",
        "params_trained": (
            "8,798,208 LoRA params (derived from architecture: r=16 on q/k/v/o/gate/up/down "
            "across 24 layers; not read from the run log)"
        ),
        "artefact": "35.24 MB LoRA adapter (run log); base weights not included",
        "wall_clock": "15.0 min real run on Kaggle T4 GPU (+36.6 s smoke run, excluded)",
    },
]


def _ledger_thresholds() -> dict[str, float]:
    ledger = json.loads(LEDGER_JSON.read_text(encoding="utf-8"))
    out: dict[str, float] = {}
    for entry in ledger["entries"]:
        out[entry["model_id"]] = float(entry["threshold"])
    return out


def _fmt(k: int, n: int) -> str:
    """value (k/n) [Wilson 95% CI]"""
    if n == 0:
        return "undefined (0/0)"
    ci = wilson_confidence_interval(k, n)
    return f"{k / n:.3f} ({k}/{n}) [{ci.lower:.3f}, {ci.upper:.3f}]"


def _ci(k: int, n: int) -> tuple[float, float]:
    ci = wilson_confidence_interval(k, n)
    return (ci.lower, ci.upper)


def main() -> int:
    view = _load_eval_view()
    entries = [e for e in _test_entries(view) if e["scored"]]
    thresholds = _ledger_thresholds()

    preds: dict[str, dict[str, float]] = {}
    results: dict[str, dict[str, Any]] = {}
    for m in MODELS:
        mid = m["model_id"]
        if mid not in thresholds:
            raise SystemExit(f"REFUSING: {mid!r} has no ledger entry, so no recorded threshold.")
        preds[mid] = json.loads((PRED_DIR / m["preds"]).read_text(encoding="utf-8"))
        results[mid] = score(_test_entries(view), preds[mid], thresholds[mid])
        # The committed metrics file must agree with what score() computes now -- the two
        # numbers are the same computation, so any difference means a file or a threshold drifted.
        stored = json.loads((RESULTS_DIR / f"{mid}-metrics.json").read_text(encoding="utf-8"))
        if stored["confusion_matrix"] != results[mid]["confusion_matrix"]:
            raise SystemExit(f"REFUSING: {mid} confusion matrix differs from its committed file.")

    def correct(mid: str, e: dict[str, Any]) -> bool:
        return bool(("M" if preds[mid][e["pair_id"]] >= thresholds[mid] else "N") == e["label"])

    # ---- Table 1: headline metrics, every rate with denominator and CI. ----
    rows = []
    for m in MODELS:
        mid = m["model_id"]
        r = results[mid]
        cm = r["confusion_matrix"]
        tp, fp, fn, tn = cm["tp"], cm["fp"], cm["fn"], cm["tn"]
        n_excl = r["recall_excluding_13_repeat_positives"]["n"]
        k_excl = round(r["recall_excluding_13_repeat_positives"]["value"] * n_excl)
        rows.append(
            {
                **m,
                "threshold": thresholds[mid],
                "confusion": cm,
                "precision": _fmt(tp, tp + fp),
                "recall": _fmt(tp, tp + fn),
                "recall_excl_repeats": _fmt(k_excl, n_excl),
                "accuracy": _fmt(tp + tn, r["n_scored"]),
                "f1": r["f1"]["value"],
            }
        )

    # ---- CI overlap between the two fine-tuned models, per metric. ----
    def cm_of(mid: str) -> dict[str, int]:
        return results[mid]["confusion_matrix"]  # type: ignore[no-any-return]

    ce, ll = cm_of(CROSS_ENCODER), cm_of(LLM)
    n_scored = results[CROSS_ENCODER]["n_scored"]
    excl = {
        mid: (
            round(
                results[mid]["recall_excluding_13_repeat_positives"]["value"]
                * results[mid]["recall_excluding_13_repeat_positives"]["n"]
            ),
            results[mid]["recall_excluding_13_repeat_positives"]["n"],
        )
        for mid in (CROSS_ENCODER, LLM)
    }
    metric_pairs = {
        "precision": ((ce["tp"], ce["tp"] + ce["fp"]), (ll["tp"], ll["tp"] + ll["fp"])),
        "recall": ((ce["tp"], ce["tp"] + ce["fn"]), (ll["tp"], ll["tp"] + ll["fn"])),
        "recall_excl_repeats": (excl[CROSS_ENCODER], excl[LLM]),
        "accuracy": ((ce["tp"] + ce["tn"], n_scored), (ll["tp"] + ll["tn"], n_scored)),
    }
    overlap = {
        name: {
            "cross_encoder": _fmt(*a),
            "llm": _fmt(*b),
            "overlap": intervals_overlap(_ci(*a), _ci(*b)),
        }
        for name, (a, b) in metric_pairs.items()
    }

    # ---- McNemar, paired on the SAME scored TEST pairs. ----
    def mcnemar(subset: list[dict[str, Any]]) -> dict[str, Any]:
        ce_only = sum(1 for e in subset if correct(CROSS_ENCODER, e) and not correct(LLM, e))
        llm_only = sum(1 for e in subset if correct(LLM, e) and not correct(CROSS_ENCODER, e))
        both = sum(1 for e in subset if correct(LLM, e) and correct(CROSS_ENCODER, e))
        neither = len(subset) - ce_only - llm_only - both
        return {
            "n": len(subset),
            "both_right": both,
            "cross_encoder_only_right": ce_only,
            "llm_only_right": llm_only,
            "both_wrong": neither,
            "p_exact_two_sided": mcnemar_exact_p(ce_only, llm_only),
        }

    mc_all = mcnemar(entries)
    mc_pos = mcnemar([e for e in entries if e["label"] == "M"])
    mc_neg = mcnemar([e for e in entries if e["label"] == "N"])

    # ---- Per tier. ----
    tier_rows: list[dict[str, Any]] = []
    for tier in TIER_ORDER:
        sub = [e for e in entries if e["tier"] == tier]
        if not sub:
            continue
        cells = {mid: sum(1 for e in sub if correct(mid, e)) for mid in preds}
        tier_rows.append(
            {
                "tier": tier,
                "n": len(sub),
                "n_pos": sum(1 for e in sub if e["label"] == "M"),
                "correct": cells,
                "mcnemar": mcnemar(sub),
            }
        )

    # The dominant hard negative (CLAUDE.md §7 Phase 1): the same product in a different size.
    # Only the two capacity-differs tiers hold it; they contain 1 positive between them, so F1 is
    # undefined and the honest metric is correct calls / n.
    size_tiers = ("capacity_differs_cross_shop", "capacity_differs_within_shop")
    sv = [e for e in entries if e["tier"] in size_tiers]
    size_variant: dict[str, Any] = {
        "tiers": list(size_tiers),
        "n": len(sv),
        "n_pos": sum(1 for e in sv if e["label"] == "M"),
        "correct": {mid: sum(1 for e in sv if correct(mid, e)) for mid in preds},
    }

    out = {
        "built_from": "scripts/compare_models.py",
        "generated_at": datetime.now(UTC).isoformat(),
        "n_scored_test_pairs": n_scored,
        "thresholds": {m["model_id"]: thresholds[m["model_id"]] for m in MODELS},
        "headline": rows,
        "ci_overlap_fine_tuned": overlap,
        "mcnemar_all": mc_all,
        "mcnemar_positives_only": mc_pos,
        "mcnemar_negatives_only": mc_neg,
        "per_tier": tier_rows,
        "size_variant": size_variant,
    }
    OUTPUT_JSON.write_text(json.dumps(out, indent=1), encoding="utf-8")

    # ---- Markdown ----
    md: list[str] = []
    md.append(
        f"### Headline TEST metrics ({n_scored} scored pairs; each: value (k/n) [Wilson 95% CI])\n"
    )
    md.append(
        "| model | val-selected threshold | precision | recall | recall excl. 13 repeat positives | accuracy | F1 |"
    )
    md.append("|---|---|---|---|---|---|---|")
    for r in rows:
        md.append(
            f"| {r['label']} | {r['threshold']} | {r['precision']} | {r['recall']} | "
            f"{r['recall_excl_repeats']} | {r['accuracy']} | {r['f1']:.4f} |"
        )
    md.append(
        "\nF1 carries no CI of its own (harmonic mean of two proportions; see the metrics files).\n"
    )
    md.append("### Cost columns\n")
    md.append("| model | parameters trained | artefact size | training wall clock |")
    md.append("|---|---|---|---|")
    for r in rows:
        md.append(f"| {r['label']} | {r['params_trained']} | {r['artefact']} | {r['wall_clock']} |")
    md.append(
        "\nThe two wall clocks are on DIFFERENT hardware (CPU vs GPU) and are not a like-for-like "
        "speed comparison.\n"
    )
    md.append("### Do the two fine-tuned models' confidence intervals overlap?\n")
    md.append("| metric | cross-encoder | LoRA | CIs overlap? |")
    md.append("|---|---|---|---|")
    for name, o in overlap.items():
        md.append(
            f"| {name} | {o['cross_encoder']} | {o['llm']} | **{'YES' if o['overlap'] else 'no'}** |"
        )

    def mc_line(label: str, mc: dict[str, Any]) -> str:
        return (
            f"| {label} | {mc['n']} | {mc['both_right']} | {mc['cross_encoder_only_right']} | "
            f"{mc['llm_only_right']} | {mc['both_wrong']} | {mc['p_exact_two_sided']:.4f} |"
        )

    md.append(
        "\n### McNemar's exact test (paired, same TEST pairs; correct = prediction matches label)\n"
    )
    md.append(
        "| subset | n | both right | cross-encoder only right | LoRA only right | both wrong | p (exact, two-sided) |"
    )
    md.append("|---|---|---|---|---|---|---|")
    md.append(mc_line("all scored pairs", mc_all))
    md.append(mc_line("true M only (recall side)", mc_pos))
    md.append(mc_line("true N only (false-positive side)", mc_neg))
    md.append("\n### Per tier: correct/n [Wilson 95% CI], and discordant pairs\n")
    md.append(
        "| tier | n | zero-shot | cross-encoder | LoRA | cross-encoder-only right | "
        "LoRA-only right | McNemar p (post-hoc, uncorrected) |"
    )
    md.append("|---|---|---|---|---|---|---|---|")
    for t in tier_rows:
        c = t["correct"]
        mc = t["mcnemar"]
        md.append(
            f"| {t['tier']} | {t['n']} ({t['n_pos']} M) | "
            f"{_fmt(c['mmarco-mMiniLMv2-zeroshot'], t['n'])} | {_fmt(c[CROSS_ENCODER], t['n'])} | "
            f"{_fmt(c[LLM], t['n'])} | {mc['cross_encoder_only_right']} | {mc['llm_only_right']} | "
            f"{mc['p_exact_two_sided']:.3f} |"
        )
    md.append(
        f"\n### Size-variant hard negatives (tiers {', '.join(size_tiers)}; "
        f"n={size_variant['n']}, {size_variant['n_pos']} positive -> F1 undefined)\n"
    )
    md.append("| model | correct calls / n [Wilson 95% CI] |")
    md.append("|---|---|")
    for m in MODELS:
        k = size_variant["correct"][m["model_id"]]
        md.append(f"| {m['label']} | {_fmt(k, size_variant['n'])} |")
    generated = "\n".join(md)

    block = f"{BEGIN}\n{generated}\n{END}"
    if OUTPUT_MD.exists():
        text = OUTPUT_MD.read_text(encoding="utf-8")
        if BEGIN in text and END in text:
            head = text[: text.index(BEGIN)]
            tail = text[text.index(END) + len(END) :]
            OUTPUT_MD.write_text(head + block + tail, encoding="utf-8")
        else:
            OUTPUT_MD.write_text(text.rstrip("\n") + "\n\n" + block + "\n", encoding="utf-8")
    else:
        OUTPUT_MD.write_text(
            "# Phase 3 model comparison (TEST)\n\n" + block + "\n", encoding="utf-8"
        )

    print(generated)
    print(f"\nwrote {OUTPUT_JSON.relative_to(ROOT)} and {OUTPUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
