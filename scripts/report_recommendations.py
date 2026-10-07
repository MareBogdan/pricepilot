r"""Phase 5 gate report: 50 real recommendations, zero margin violations (ADR-0042).

    $env:PRICEPILOT_DB_DRIVER = "pg8000"      # if psycopg is blocked (ADR-0038)
    .venv\Scripts\python scripts/report_recommendations.py [--run-label s5-real] [--no-write]

Reads `recommendations` rows with `is_mock = false` for the run label, re-checks every APPROVE
against `config/pricing-policy.toml` independently of the guard (`decision.report.evaluate`), prints
the verdict and writes `docs/learned/results/phase5/fifty-recommendations.md`. Exit code 0 only if
the gate passed; any margin violation or an incomplete set exits 1.
"""

from __future__ import annotations

import argparse
import io
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func, select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.decision.report import GateReport, evaluate  # noqa: E402
from pricepilot.models import LlmCall, Recommendation  # noqa: E402
from pricepilot.policy.guard import margin  # noqa: E402
from pricepilot.policy.thresholds import load_thresholds  # noqa: E402

OUT = ROOT / "docs" / "learned" / "results" / "phase5" / "fifty-recommendations.md"


def pct(d: Decimal) -> str:
    return f"{(d * 100):.1f}%"


def counts(c: object) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(c.items())) or "-"  # type: ignore[attr-defined]


def render(rows: list[Recommendation], report: GateReport, model_calls: int) -> str:
    t = load_thresholds()
    verdict = "PASSED" if report.passed else "FAILED"
    spend = sum((r.llm_cost_usd for r in rows), Decimal("0"))
    latencies = [r.llm_latency_ms for r in rows if r.llm_latency_ms is not None]
    models = sorted({r.llm_model for r in rows})
    lines = [
        "# Phase 5 gate: 50 recommendations, zero margin violations",
        "",
        f"**Result: {verdict}.** {report.total} real recommendations "
        f"({report.distinct} distinct product/scenario pairs), "
        f"**{len(report.margin_violations)} margin violations** among "
        f"{report.status_counts.get('APPROVE', 0)} APPROVE rows.",
        "",
        "Counted: `recommendations` rows with `is_mock = false` for this run only. Every APPROVE is "
        "re-checked here from the stored cost, applied price and category against "
        "`config/pricing-policy.toml`, independently of the guard's own verdict "
        "(`decision/report.py::evaluate`, tested). Reproduce: "
        "`scripts/report_recommendations.py`.",
        "",
        "## What is real and what is not",
        "",
        "| Input | Status |",
        "|---|---|",
        "| Our cost, price, stock | the mock store's seeded catalogue (a fixture, not a live shop) |",
        "| Competitor prices, baseline rows | real scraped prices for guarded cross-encoder matches |",
        "| Competitor prices, scenario rows | **HYPOTHETICAL**: observed price x 0.85 (`undercut_15`) "
        "or x 0.70 (`undercut_30`), a what-if test of the guard; the prompt says so |",
        "| `price_7d_ago` | **SYNTHETIC** mock-store history, includes its promo windows |",
        "| Elasticity | a labelled placeholder with no value (Phase 4 POSTPONED) |",
        "| Proposed price and rationale | the real LLM (`" + ", ".join(models) + "`) |",
        "",
        "## Verdicts",
        "",
        f"Overall: {counts(report.status_counts)}.",
        "",
        "| Scenario | Rows | APPROVE | REJECT | FLAG |",
        "|---|---|---|---|---|",
    ]
    for name in ("baseline", "undercut_15", "undercut_30"):
        c = report.by_scenario.get(name)
        if c:
            lines.append(
                f"| {name} | {sum(c.values())} | {c['APPROVE']} | {c['REJECT']} | {c['FLAG']} |"
            )
    lines += ["", "## Why the non-APPROVE rows are not APPROVE", ""]
    if report.cause_counts:
        lines += ["| Cause | Rows |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in report.cause_counts.most_common()]
        synthetic = sum(v for k, v in report.cause_counts.items() if "SYNTHETIC" in k)
        lines += [
            "",
            f"{synthetic} of {sum(report.cause_counts.values())} non-APPROVE rows exist only "
            "because of the synthetic 7-day reference (replaying the guard with the reference set "
            "to the current price would have approved them); the rest are the LLM's own move or "
            "reply. A FLAG is a correct refusal, not a violation.",
        ]
    else:
        lines.append("None: every row was APPROVE.")
    lines += [
        "",
        "## Checks",
        "",
        f"- Margin violations (APPROVE below its category floor): **{len(report.margin_violations)}**",
        f"- Status/applied-price mismatches (price present iff APPROVE): "
        f"{len(report.structure_violations)}",
        f"- Direction contradictions (ADR-0043: applied price on the wrong side of current): "
        f"{len(report.direction_violations)}",
        f"- Rows: {report.total}/{report.expected_total}, distinct {report.distinct}",
    ]
    for v in report.margin_violations + report.structure_violations + report.direction_violations:
        lines.append(
            f"  - VIOLATION product {v.product_id} ({v.scenario or 'baseline'}): {v.detail}"
        )
    lines += [
        "",
        "## Cost and latency (actual)",
        "",
        f"- LLM spend for these rows: **${spend}** over {model_calls} `llm_calls` rows",
        f"- Mean latency: {sum(latencies) / len(latencies):.0f} ms"
        if latencies
        else "- Latency: n/a",
        "",
        "## All rows",
        "",
        "| # | Product | Category | Scenario | Cost | Current | Proposed | Applied | Margin | Floor | "
        "Verdict | Reason |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows, key=lambda x: (x.scenario is not None, x.scenario or "", x.product_id)):
        floor = Decimal(str(t.margin_floor[r.category]))  # type: ignore[index]
        applied = r.guard_final_price
        m = pct(margin(applied, r.cost)) if applied is not None else "-"
        reason = (r.guard_reason or "").replace("|", "/")[:90]
        lines.append(
            f"| {r.id} | {r.product_id} | {r.category} | {r.scenario or 'baseline'} | {r.cost} | "
            f"{r.current_price} | {r.llm_proposed_price if r.llm_proposed_price is not None else '-'}"
            f" | {applied if applied is not None else '-'} | {m} | {pct(floor)} | "
            f"{r.guard_status} | {reason} |"
        )
    lines += [
        "",
        "## Caveats",
        "",
        "- 30 rows use real inputs; 20 use hypothetical competitor prices. Do not read the "
        "APPROVE/FLAG mix as a market result.",
        "- The gate proves the guard holds on 50 LLM proposals, not that the proposed prices are "
        "good business decisions: elasticity is a placeholder and no sales feedback exists.",
        "- The applied price comes only from `guard.enforce`; the LLM price is a suggestion.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-label", default="s5-real")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    if not check_database():
        print("database unreachable (if psycopg is blocked, set PRICEPILOT_DB_DRIVER=pg8000)")
        return 1
    with session_scope() as session:
        rows = list(
            session.execute(
                select(Recommendation)
                .where(
                    Recommendation.run_label == args.run_label, Recommendation.is_mock.is_(False)
                )
                .order_by(Recommendation.id)
            ).scalars()
        )
        model_calls = session.execute(
            select(func.count()).select_from(LlmCall).where(LlmCall.phase == "phase5")
        ).scalar_one()
    report = evaluate(rows, thresholds=load_thresholds())
    text = render(rows, report, int(model_calls))
    if not args.no_write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {OUT.relative_to(ROOT)}")
    print(
        f"rows {report.total} (distinct {report.distinct}); status {dict(report.status_counts)}; "
        f"margin violations {len(report.margin_violations)}; "
        f"direction contradictions {len(report.direction_violations)}; "
        f"GATE {'PASSED' if report.passed else 'FAILED'}"
    )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
