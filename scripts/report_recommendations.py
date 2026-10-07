r"""Phase 5 gate report: 50 real recommendations, zero margin violations (ADR-0042/0044/0045).

    $env:PRICEPILOT_DB_DRIVER = "pg8000"      # if psycopg is blocked (ADR-0038)
    .venv\Scripts\python scripts/report_recommendations.py [--run-label s5-real] [--no-write]

Reads `recommendations` rows with `is_mock = false` for the run label, re-checks every APPROVE
against `config/pricing-policy.toml` independently of the guard (`decision.report.evaluate`), prints
the verdict and writes `docs/learned/results/phase5/fifty-recommendations.md`. Exit code 0 only if
the gate passed; any margin violation or an incomplete set exits 1. Superseded rows (relabelled
`s5-superseded` by the s5b refresh) are not read: one row per (product, scenario).
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
from pricepilot.decision.report import (  # noqa: E402
    GateReport,
    MoveSummary,
    evaluate,
    summarise_moves,
)
from pricepilot.decision.scenarios import is_stress  # noqa: E402
from pricepilot.models import Recommendation  # noqa: E402
from pricepilot.policy.guard import margin  # noqa: E402
from pricepilot.policy.thresholds import load_thresholds  # noqa: E402

OUT = ROOT / "docs" / "learned" / "results" / "phase5" / "fifty-recommendations.md"
STRESS_LABEL = "GUARD STRESS-TEST -- synthetic competitor prices, not a market recommendation"
IGNORE_WORDS = re.compile(r"hypothetical|what-if|not market|not real|synthetic scenario", re.I)


def pct(d: Decimal) -> str:
    return f"{(d * 100):.1f}%"


def counts(c: object) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(c.items())) or "-"  # type: ignore[attr-defined]


def move_row(name: str, m: MoveSummary) -> str:
    return (
        f"| {name} | {m.total} | {m.proposed_move} | {m.proposed_over_cap} | "
        f"{m.proposed_below_floor} | {m.approve_moved} | {m.approve_unchanged} | {m.flag} | "
        f"{m.reject} | **{m.applied_below_floor}** |"
    )


def render(rows: list[Recommendation], report: GateReport) -> str:
    t = load_thresholds()
    verdict = "PASSED" if report.passed else "FAILED"
    baseline = [r for r in rows if not r.scenario]
    stress = [r for r in rows if is_stress(r.scenario)]
    other = [r for r in rows if r.scenario and not is_stress(r.scenario)]
    matched = [r for r in baseline if r.competitor_prices]
    unmatched = [r for r in baseline if not r.competitor_prices]
    s_stress = summarise_moves(stress, thresholds=t)
    s_matched = summarise_moves(matched, thresholds=t)
    s_unmatched = summarise_moves(unmatched, thresholds=t)
    s_all = summarise_moves(rows, thresholds=t)
    stress_ignored = sum(1 for r in stress if IGNORE_WORDS.search(r.llm_rationale or ""))
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
        f"| Competitor prices, baseline rows | real scraped prices for the {len(matched)} matched "
        f"products; the other {len(unmatched)} had NO competitor data (decided from cost and policy "
        "alone) |",
        f"| Competitor prices, stress-test rows ({len(stress)}) | **{STRESS_LABEL}**: the observed "
        "price x 0.85 (`stress_undercut_15`) or x 0.70 (`stress_undercut_30`). The prompt presents "
        "them as the pricing input to respond to (the model is not told they are synthetic); the "
        "trace keeps the real `observed_price` |",
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
    for name in sorted(report.by_scenario, key=lambda n: (n != "baseline", n)):
        c = report.by_scenario[name]
        lines.append(
            f"| {name} | {sum(c.values())} | {c['APPROVE']} | {c['REJECT']} | {c['FLAG']} |"
        )
    lines += [
        "",
        "## What actually exercised the guard",
        "",
        "Counts of the MODEL's proposals before the guard touched them, and what the guard let "
        "through. `proposed over cap` = the model asked for a move bigger than the daily cap; "
        "`proposed below floor` = the model's own price would breach the margin floor if applied; "
        "`applied below floor` = what the guard APPROVED under a floor (must be 0).",
        "",
        "| Group | Rows | Proposed a move | Proposed over cap | Proposed below floor | APPROVE moved "
        "| APPROVE unchanged | FLAG | REJECT | Applied below floor |",
        "|---|---|---|---|---|---|---|---|---|---|",
        move_row(f"stress-tests ({STRESS_LABEL.split(' --')[0]})", s_stress),
        move_row("baseline, matched (real competitor prices)", s_matched),
        move_row("baseline, no competitor data", s_unmatched),
        move_row("ALL", s_all),
        "",
        f"- Stress-test rows whose rationale says the competitor price was hypothetical / ignored: "
        f"**{stress_ignored} of {len(stress)}**"
        + (" (the earlier framing's failure mode; it should now be ~0)." if stress else "."),
        f"- Of the 50 rows, **{s_all.approve_moved} APPROVEs move the price** and "
        f"{s_all.approve_unchanged} keep it. A no-change keeps today's margin, so the floor claim "
        "rests on the moved rows, the proposals the guard stopped, and the guard's unit tests and "
        "sweeps.",
    ]
    if other:
        lines.append(
            f"- {len(other)} row(s) carry an unrecognised scenario name: {sorted({str(r.scenario) for r in other})}"
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
        f"(product(s) {', '.join(str(v.product_id) for v in report.truncated) or '-'}). A reply cut "
        "off at the token cap is a harness fault; the engine FLAGs such a reply (ADR-0044).",
    ]
    for v in report.margin_violations + report.structure_violations + report.direction_violations:
        lines.append(
            f"  - VIOLATION product {v.product_id} ({v.scenario or 'baseline'}): {v.detail}"
        )
    lines += [
        "",
        "## Cost and latency (actual, rows in this report)",
        "",
        f"- LLM spend recorded on these {len(rows)} rows: **${spend}** (rows superseded by the s5b "
        "refresh are excluded; see docs/COSTS.md for the full spend)",
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
        name = (
            "baseline"
            if not r.scenario
            else r.scenario + (" (STRESS)" if is_stress(r.scenario) else "")
        )
        lines.append(
            f"| {r.id} | {r.product_id} | {r.category} | {name} | {r.cost} | "
            f"{r.current_price} | {r.llm_proposed_price if r.llm_proposed_price is not None else '-'}"
            f" | {applied if applied is not None else '-'} | {m} | {pct(floor)} | "
            f"{r.guard_status} | {reason} |"
        )
    lines += [
        "",
        "## Caveats",
        "",
        f"- {len(baseline)} rows are baseline ({len(matched)} with real competitor prices, "
        f"{len(unmatched)} without any) and {len(stress)} are {STRESS_LABEL}. Do not read the "
        "APPROVE/FLAG mix as a market result.",
        "- The gate proves the guard holds on 50 LLM proposals, not that the proposed prices are "
        "good business decisions: elasticity is a placeholder and no sales feedback exists.",
        "- The daily cap (5%) keeps a single step far from the floors in this catalogue (margins "
        "28-56% against floors of 12-30%), so a live model that obeys the cap cannot reach a floor "
        "in one move; the floor itself is demonstrated by the guard's unit tests and sweeps.",
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
