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
import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.decision.report import GateReport, evaluate  # noqa: E402
from pricepilot.models import Recommendation  # noqa: E402
from pricepilot.policy.guard import margin  # noqa: E402
from pricepilot.policy.thresholds import load_thresholds  # noqa: E402

OUT = ROOT / "docs" / "learned" / "results" / "phase5" / "fifty-recommendations.md"


def pct(d: Decimal) -> str:
    return f"{(d * 100):.1f}%"


def counts(c: object) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(c.items())) or "-"  # type: ignore[attr-defined]


WHATIF_WORDS = re.compile(r"hypothetical|what-if|not market|not real|not what the shops", re.I)


def render(rows: list[Recommendation], report: GateReport) -> str:
    t = load_thresholds()
    verdict = "PASSED" if report.passed else "FAILED"
    scenario_rows = [r for r in rows if r.scenario]
    scenario_total = len(scenario_rows)
    scenario_moved = sum(
        1 for r in scenario_rows if r.guard_final_price not in (None, r.current_price)
    )
    scenario_cited = sum(1 for r in scenario_rows if WHATIF_WORDS.search(r.llm_rationale or ""))
    baseline = [r for r in rows if not r.scenario]
    matched = [r for r in baseline if r.competitor_prices]
    matched_moved = sum(1 for r in matched if r.guard_final_price not in (None, r.current_price))
    matched_flag = sum(1 for r in matched if r.guard_status == "FLAG")
    matched_same = sum(
        1
        for r in matched
        if r.guard_final_price is not None and r.guard_final_price == r.current_price
    )
    unmatched = len(baseline) - len(matched)
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
        f"| Competitor prices, baseline rows | real scraped prices for the {len(matched)} matched products; "
        f"the other {unmatched} had NO competitor data (decided from cost and policy alone) |",
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
        f"**Of the {report.status_counts.get('APPROVE', 0)} APPROVE rows, "
        f"{report.approve_unchanged} keep the current price and only {report.approve_moved} move it.** "
        "A no-change keeps today's margin, so the zero-violation count rests on the moved rows "
        "(and on the guard's unit tests and sweeps) far more than on the 50.",
        "",
        "## How much of the run actually tested the floor",
        "",
        f"- **{unmatched} baseline rows had no competitor data**; nothing prompts a move there "
        f"({sum(1 for r in baseline if not r.competitor_prices and r.guard_final_price == r.current_price)} "
        "of them are no-change APPROVEs).",
        f"- **The {scenario_total} scenario rows moved the price in {scenario_moved} cases, and "
        f"{scenario_cited} of their {scenario_total} rationales cite the what-if label as the reason "
        "for ignoring the competitor price.** The prompt announced the prices were hypothetical, so "
        "the scenarios never pressed the floor: this is a property of the test design, not evidence "
        "that the model is robust.",
        f"- The {len(matched)} matched baseline rows are the real test: {matched_moved} moved the "
        f"price, {matched_same} kept it, {matched_flag} were FLAGged.",
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
            "to the current price would have approved them); the others are labelled by cause "
            "above. A FLAG is a correct refusal, not a violation.",
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
        f"- Replies cut off by max_tokens: **{len(report.truncated)}** "
        f"({sum(1 for v in report.truncated if v.detail.startswith('APPROVE'))} of them APPROVE, "
        f"product(s) {', '.join(str(v.product_id) for v in report.truncated) or '-'}). "
        "A reply cut off at the token cap is a harness fault, not model judgement. The stop_reason "
        "check that FLAGs such replies was added after the run (ADR-0044), so a truncated APPROVE "
        "row would be a FLAG under today's engine. Not margin-related.",
    ]
    for v in report.margin_violations + report.structure_violations + report.direction_violations:
        lines.append(
            f"  - VIOLATION product {v.product_id} ({v.scenario or 'baseline'}): {v.detail}"
        )
    lines += [
        "",
        "## Cost and latency (actual)",
        "",
        f"- LLM spend for these rows: **${spend}** over {len(rows)} recommendation rows",
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
        if not reason and r.llm_stop_reason == "max_tokens":
            reason = "reply cut at max_tokens (accepted at run time)"
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
        f"- {len(baseline)} rows are baseline ({len(matched)} with real competitor prices, {unmatched} "
        f"without any) and {scenario_total} use hypothetical competitor prices. Do not read the "
        "APPROVE/FLAG mix as a market result.",
        "- Read the headline with the section above: this run is weak evidence for the floor. The "
        "floor is demonstrated by the guard's tests and sweeps, not by these 50 rows.",
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
    report = evaluate(rows, thresholds=load_thresholds())
    text = render(rows, report)
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
