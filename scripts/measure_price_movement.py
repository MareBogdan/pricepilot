"""Phase 4 session 1: data-sufficiency measurement (READ-ONLY).

Implements `docs/phase4-data-sufficiency-rule.md` exactly (definitions and thresholds are
pre-registered there and committed before this script's first run). Reads the collection
database, prints a report, and writes `docs/learned/results/phase4/price-movement.json`.
No demand model, no simulator, no DB write of any kind: the connection is opened in a
`SET TRANSACTION READ ONLY` transaction and the script contains no INSERT/UPDATE/DDL.

Run:  .venv\\Scripts\\python scripts/measure_price_movement.py [--neon-limit-mb N --neon-limit-url URL]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RULE_FILE = ROOT / "docs" / "phase4-data-sufficiency-rule.md"
OUT_FILE = ROOT / "docs" / "learned" / "results" / "phase4" / "price-movement.json"

# --- thresholds: identical to the pre-registered rule file; never edit after seeing data ---
EVENT_PCT = Decimal("2")  # percent
PRE_DAYS = 7
HORIZON_DAYS = 7
HOLDOUT_COLLECTION_DAYS = 14
R1_MIN_DAYS = 28
R1_MAX_GAPS = 2
R1_MIN_SOURCES = 2
R2_MIN_HOLDOUT = 200
R2_CELL_MIN = 30
R2_MIN_CELLS = 3
R3_MIN_TRAIN = 200
PROJECTION_CAP_DAYS = 60
IN_SCOPE_CATEGORIES = ("food", "litter")

EVENT_TYPES = ("base_change", "promo_start", "promo_end", "promo_depth")

# ---------------------------------------------------------------------------
# Pure logic (no DB) -- unit-tested in tests/test_price_movement.py
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Obs:
    price: Decimal
    compare_at: Decimal | None


def _dec(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def make_obs(price: object, compare_at: object | None = None) -> Obs:
    return Obs(_dec(price), None if compare_at is None else _dec(compare_at))


def collapse_last_by_id(rows: Iterable[tuple[int, date, Obs]]) -> tuple[dict[date, Obs], int]:
    """One observation per date: the row with the highest id. Returns (series, n_multi_days)."""
    best: dict[date, tuple[int, Obs]] = {}
    count: dict[date, int] = defaultdict(int)
    for row_id, day, obs in rows:
        count[day] += 1
        if day not in best or row_id > best[day][0]:
            best[day] = (row_id, obs)
    return {d: v[1] for d, v in best.items()}, sum(1 for c in count.values() if c > 1)


def is_promo(o: Obs) -> bool:
    return o.compare_at is not None and o.compare_at > o.price


def base_price(o: Obs) -> Decimal:
    return o.compare_at if is_promo(o) and o.compare_at is not None else o.price


def _pct_at_least(cur: Decimal, prev: Decimal, pct: Decimal) -> bool:
    # |cur/prev - 1| >= pct/100, in exact decimal arithmetic (no float rounding at exactly 2%).
    return abs(cur - prev) * 100 >= pct * prev


def classify_pair(prev: Obs, cur: Obs) -> tuple[set[str], bool]:
    """(event types, sub_threshold) for the day pair (t-1, t). sub_threshold is True only when
    there is NO event but the base price moved (0<|d|<2%), or both days are promo and the
    price moved (0<|d|<2%): rounding noise, never an event."""
    types: set[str] = set()
    p_prev, p_cur = is_promo(prev), is_promo(cur)
    b_prev, b_cur = base_price(prev), base_price(cur)
    if _pct_at_least(b_cur, b_prev, EVENT_PCT):
        types.add("base_change")
    if not p_prev and p_cur:
        types.add("promo_start")
    if p_prev and not p_cur:
        types.add("promo_end")
    if p_prev and p_cur and _pct_at_least(cur.price, prev.price, EVENT_PCT):
        types.add("promo_depth")
    sub = False
    if not types:
        sub = b_cur != b_prev or (p_prev and p_cur and cur.price != prev.price)
    return types, sub


def find_events(series: Mapping[date, Obs]) -> tuple[dict[date, set[str]], int]:
    """({day: types} for every event day, sub_threshold count)."""
    events: dict[date, set[str]] = {}
    sub_count = 0
    for day in sorted(series):
        prev_day = day - timedelta(days=1)
        if prev_day not in series:
            continue
        types, sub = classify_pair(series[prev_day], series[day])
        if types:
            events[day] = types
        elif sub:
            sub_count += 1
    return events, sub_count


def _window(day: date, start: int, end: int) -> list[date]:
    return [day + timedelta(days=i) for i in range(start, end + 1)]


def is_evaluable(
    t: date, series: Mapping[date, Obs], events: Mapping[date, set[str]], lenient: bool
) -> bool:
    """Evaluable event at t (t must itself be an event day). Strict: observed on all of
    t-7..t-1 and t..t+6, and no event on any of t-7..t-1. Lenient: <=1 missing day per window."""
    if t not in events:
        return False
    pre = _window(t, -PRE_DAYS, -1)
    post = _window(t, 0, HORIZON_DAYS - 1)
    allowed_missing = 1 if lenient else 0
    if sum(1 for d in pre if d not in series) > allowed_missing:
        return False
    if sum(1 for d in post if d not in series) > allowed_missing:
        return False
    return not any(d in events for d in pre)


def evaluable_events(series: Mapping[date, Obs], lenient: bool) -> list[date]:
    events, _ = find_events(series)
    return [t for t in sorted(events) if is_evaluable(t, series, events, lenient)]


def gaps_between(collection_days: set[date]) -> list[date]:
    if not collection_days:
        return []
    first, last = min(collection_days), max(collection_days)
    return [
        first + timedelta(days=i)
        for i in range((last - first).days + 1)
        if first + timedelta(days=i) not in collection_days
    ]


def pctl(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(q * (len(s) - 1))))
    return s[idx]


def dist_summary(values: list[float]) -> dict[str, float | None]:
    return {
        "median": statistics.median(values) if values else None,
        "p90": pctl(values, 0.9),
        "max": max(values) if values else None,
    }


def project_remeasure(
    days_now: int,
    holdout_now: int,
    train_now: int,
    daily_rate: float,
    today: date,
) -> dict[str, Any]:
    """ESTIMATE: project the combined daily evaluable-event rate forward linearly. Returns the
    first date at which R1-R3 are projected to hold, or NEEDS ARCHITECT if R2 still fails at
    PROJECTION_CAP_DAYS collection days. Per-source R1 and the per-cell part of R2 are checked
    by the caller's verdict; this projection covers the counts (R1 length, R2/R3 totals)."""
    # The holdout is a fixed 14-collection-day window ending at the newest day, so evaluable
    # events in it scale with the rate: expected holdout events ~ rate * (14 - HORIZON + 1).
    holdout_span = HOLDOUT_COLLECTION_DAYS - HORIZON_DAYS + 1

    def holdout_at(days: int) -> float:
        return max(holdout_now, daily_rate * holdout_span) if days > days_now else holdout_now

    def train_at(days: int) -> float:
        extra = max(0, days - days_now)
        return train_now + daily_rate * extra

    for days in range(max(days_now, 1), PROJECTION_CAP_DAYS + 1):
        if days < R1_MIN_DAYS:
            continue
        if holdout_at(days) >= R2_MIN_HOLDOUT and train_at(days) >= R3_MIN_TRAIN:
            return {
                "label": "ESTIMATE",
                "collection_days_needed": days,
                "date": (today + timedelta(days=max(0, days - days_now))).isoformat(),
            }
    return {"label": "ESTIMATE", "flag": "NEEDS ARCHITECT: movement too rare"}


# ---------------------------------------------------------------------------
# DB access (read-only)
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _fmt(v: object) -> str:
    return "-" if v is None else (f"{v:.2f}" if isinstance(v, float) else str(v))


def measure(neon_limit_mb: float | None, neon_limit_url: str | None) -> dict[str, Any]:
    from sqlalchemy import text

    from pricepilot.db import connect_with_wakeup_retry, get_engine

    conn = connect_with_wakeup_retry(get_engine())
    try:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        # -- (a) collection days per source --------------------------------------------------
        runs = conn.execute(
            text(
                "SELECT source, status, (started_at AT TIME ZONE 'UTC')::date AS d FROM scrape_runs"
            )
        ).all()
        raw_days = conn.execute(
            text("SELECT DISTINCT source, collected_date FROM raw_listings")
        ).all()
        status_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        ok_days: dict[str, set[date]] = defaultdict(set)
        for src, status, d in runs:
            status_counts[src][status] += 1
            if status == "ok":
                ok_days[src].add(d)
        raw_by_src: dict[str, set[date]] = defaultdict(set)
        for src, d in raw_days:
            raw_by_src[src].add(d)
        collection_days = {s: ok_days[s] & raw_by_src[s] for s in raw_by_src}

        # -- listing series ------------------------------------------------------------------
        rows = conn.execute(
            text(
                "SELECT r.id, r.source, r.external_id, r.source_product_id, r.url, "
                "r.collected_date, r.price, r.compare_at_price, r.content_hash, n.category "
                "FROM raw_listings r LEFT JOIN norm_listings n ON n.content_hash = r.content_hash "
                "WHERE r.excluded_reason IS NULL ORDER BY r.id"
            )
        ).all()

        # -- (f) storage ---------------------------------------------------------------------
        db_size = conn.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
        tables = conn.execute(
            text(
                "SELECT c.relname, pg_total_relation_size(c.oid) AS bytes "
                "FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace "
                "WHERE c.relkind = 'r' AND ns.nspname = 'public' "
                "ORDER BY bytes DESC LIMIT 5"
            )
        ).all()
        table_rows = {
            name: conn.execute(text(f'SELECT count(*) FROM "{name}"')).scalar_one()
            for name, _ in tables
        }
    finally:
        conn.rollback()
        conn.close()

    # Listing identity: (source, external_id); the columns are NOT NULL, but report which key
    # the external_id actually is (source_product_id / url / other) as the rule asks.
    key_usage: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    per_listing: dict[tuple[str, str], list[tuple[int, date, Obs]]] = defaultdict(list)
    last_meta: dict[tuple[str, str], tuple[int, str | None]] = {}
    hash_first_day: dict[tuple[str, str], date] = {}
    for rid, src, ext, spid, url, d, price, cmp_, chash, cat in rows:
        lid = (src, ext)
        per_listing[lid].append((rid, d, make_obs(price, cmp_)))
        if lid not in last_meta or rid > last_meta[lid][0]:
            last_meta[lid] = (rid, cat)
        if ext == spid:
            key_usage[src]["source_product_id"].add(ext)
        elif ext == url:
            key_usage[src]["url"].add(ext)
        else:
            key_usage[src]["external_id_other"].add(ext)
        hk = (src, chash)
        if hk not in hash_first_day or d < hash_first_day[hk]:
            hash_first_day[hk] = d

    dropped_out_of_scope = 0
    multi_row_days = 0
    # source -> category -> per-listing stats
    stats: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(_new_cell))
    for lid, obs_rows in per_listing.items():
        src = lid[0]
        cat = last_meta[lid][1]
        if cat not in IN_SCOPE_CATEGORIES:
            dropped_out_of_scope += 1
            continue
        series, multi = collapse_last_by_id(obs_rows)
        multi_row_days += multi
        cell = stats[src][cat]
        events, sub = find_events(series)
        cell["listings"] += 1
        cell["listing_days"] += len(series)
        cell["promo_days"] += sum(1 for o in series.values() if is_promo(o))
        cell["sub_threshold"] += sub
        n_ev = len(events)
        cell["events_per_listing"][min(n_ev, 3)] += 1
        if n_ev:
            cell["listings_with_event"] += 1
        cell["events"] += n_ev
        for day, types in events.items():
            for ty in types:
                cell["by_type"][ty] += 1
            if "base_change" in types:
                prev = series[day - timedelta(days=1)]
                cur = series[day]
                cell["base_change_abs_pct"].append(
                    float(abs(base_price(cur) - base_price(prev)) / base_price(prev) * 100)
                )
        last14 = sorted(collection_days.get(src, set()))[-HOLDOUT_COLLECTION_DAYS:]
        holdout_start = last14[0] if last14 else date.max
        for lenient, key in ((False, "strict"), (True, "lenient")):
            for t in evaluable_events(series, lenient):
                cell[key]["holdout" if t >= holdout_start else "training"] += 1

    # -- serialise per-source x category ----------------------------------------------------
    sources = sorted(collection_days)
    per_source: dict[str, Any] = {}
    for src in sources:
        cd = collection_days[src]
        per_source[src] = {
            "first_collection_day": min(cd).isoformat() if cd else None,
            "last_collection_day": max(cd).isoformat() if cd else None,
            "collection_days": len(cd),
            "gaps": [d.isoformat() for d in gaps_between(cd)],
            "scrape_runs_status_counts": dict(status_counts[src]),
            "listing_key_usage": {k: len(v) for k, v in key_usage[src].items()},
            "categories": {},
        }
        for cat, cell in sorted(stats[src].items()):
            ld = cell["listing_days"]
            per_source[src]["categories"][cat] = {
                "listings": cell["listings"],
                "listings_with_event": cell["listings_with_event"],
                "events_per_listing_0_1_2_3plus": [cell["events_per_listing"][i] for i in range(4)],
                "events_union": cell["events"],
                "events_by_type": {t: cell["by_type"].get(t, 0) for t in EVENT_TYPES},
                "sub_threshold": cell["sub_threshold"],
                "base_change_abs_pct": dist_summary(cell["base_change_abs_pct"]),
                "promo_listing_day_share": (cell["promo_days"] / ld) if ld else None,
                "evaluable_strict": dict(cell["strict"]),
                "evaluable_lenient": dict(cell["lenient"]),
            }

    # -- (d) verdict --------------------------------------------------------------------------
    r1_sources = [
        s
        for s in sources
        if per_source[s]["collection_days"] >= R1_MIN_DAYS
        and len(per_source[s]["gaps"]) <= R1_MAX_GAPS
    ]
    holdout_total = sum(
        c["evaluable_strict"].get("holdout", 0)
        for s in sources
        for c in per_source[s]["categories"].values()
    )
    train_total = sum(
        c["evaluable_strict"].get("training", 0)
        for s in sources
        for c in per_source[s]["categories"].values()
    )
    cells_ok = [
        f"{s}/{cat}"
        for s in sources
        for cat, c in per_source[s]["categories"].items()
        if c["evaluable_strict"].get("holdout", 0) >= R2_CELL_MIN
    ]
    r1 = len(r1_sources) >= R1_MIN_SOURCES
    r2 = holdout_total >= R2_MIN_HOLDOUT and len(cells_ok) >= R2_MIN_CELLS
    r3 = train_total >= R3_MIN_TRAIN
    proceed = r1 and r2 and r3
    verdict: dict[str, Any] = {
        "R1": {"pass": r1, "sources_meeting": r1_sources, "need": R1_MIN_SOURCES},
        "R2": {
            "pass": r2,
            "holdout_evaluable_total": holdout_total,
            "need_total": R2_MIN_HOLDOUT,
            "cells_with_ge_30": cells_ok,
            "need_cells": R2_MIN_CELLS,
        },
        "R3": {"pass": r3, "training_evaluable_total": train_total, "need": R3_MIN_TRAIN},
        "overall": "PROCEED" if proceed else "POSTPONE",
    }
    if not proceed:
        union_days = set().union(*collection_days.values()) if collection_days else set()
        days_now = max((per_source[s]["collection_days"] for s in sources), default=0)
        # Daily evaluable-event rate: strict evaluable events (training+holdout) per collection
        # day, summed over sources (each source's observed rate, added). ESTIMATE input.
        rate = sum(
            sum(
                v
                for c in per_source[s]["categories"].values()
                for v in c["evaluable_strict"].values()
            )
            / max(per_source[s]["collection_days"], 1)
            for s in sources
        )
        today = max(union_days) if union_days else datetime.now(UTC).date()
        verdict["remeasure"] = project_remeasure(days_now, holdout_total, train_total, rate, today)
        verdict["remeasure"]["combined_daily_evaluable_rate"] = rate
        verdict["remeasure"]["basis_date"] = today.isoformat()

    # -- (e) D2: new content_hash per collection day per source -------------------------------
    d2: dict[str, Any] = {}
    for src in sources:
        days_sorted = sorted(collection_days[src])
        counts: dict[date, int] = {d: 0 for d in days_sorted}
        for (s, _h), d in hash_first_day.items():
            if s == src and d in counts:
                counts[d] += 1
        later = [
            float(counts[d]) for d in days_sorted[1:]
        ]  # first collection day is the initial load
        d2[src] = {
            "first_day_initial_load": counts[days_sorted[0]] if days_sorted else None,
            "days_measured": len(later),
            "new_hashes_per_day": dist_summary(later),
            "x100_daily_scorings": {
                k: (v * 100 if v is not None else None) for k, v in dist_summary(later).items()
            },
        }

    # -- (f) storage --------------------------------------------------------------------------
    union_days_n = len(set().union(*collection_days.values())) if collection_days else 0
    growth = db_size / union_days_n if union_days_n else None
    storage: dict[str, Any] = {
        "database_bytes": int(db_size),
        "collection_days_union": union_days_n,
        "avg_growth_bytes_per_collection_day_ESTIMATE": growth,
        "top5_tables": [
            {"table": n, "bytes": int(b), "rows": int(table_rows[n])} for n, b in tables
        ],
        "neon_free_tier_limit_mb": neon_limit_mb if neon_limit_url else "UNVERIFIED",
        "neon_limit_source_url": neon_limit_url,
    }
    if neon_limit_mb is not None and neon_limit_url and growth:
        remaining = neon_limit_mb * 1024 * 1024 - db_size
        days_left = remaining / growth
        storage["days_until_limit_ESTIMATE"] = days_left
        storage["limit_hit_date_ESTIMATE"] = (
            datetime.now(UTC).date() + timedelta(days=days_left)
        ).isoformat()
    else:
        storage["days_until_limit_ESTIMATE"] = "UNVERIFIED (limit not read this session)"

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "rule_file_sha256": _sha256(RULE_FILE),
        "dropped_out_of_scope_listings": dropped_out_of_scope,
        "multi_row_days_collapsed": multi_row_days,
        "per_source": per_source,
        "verdict": verdict,
        "d2_incremental_matching_volume": d2,
        "storage": storage,
    }


def _new_cell() -> dict[str, Any]:
    return {
        "listings": 0,
        "listings_with_event": 0,
        "listing_days": 0,
        "promo_days": 0,
        "sub_threshold": 0,
        "events": 0,
        "events_per_listing": defaultdict(int),
        "by_type": defaultdict(int),
        "base_change_abs_pct": [],
        "strict": defaultdict(int),
        "lenient": defaultdict(int),
    }


def print_report(rep: dict[str, Any]) -> None:
    print(f"Phase 4 price-movement measurement  {rep['generated_at']}  git {rep['git_sha'][:10]}")
    print(f"rule sha256 {rep['rule_file_sha256']}")
    print(
        f"dropped out-of-scope listings: {rep['dropped_out_of_scope_listings']}; "
        f"multi-row days collapsed: {rep['multi_row_days_collapsed']}"
    )
    for src, s in rep["per_source"].items():
        print(f"\n== {src}: {s['first_collection_day']} .. {s['last_collection_day']}")
        print(
            f"   collection days {s['collection_days']}, gaps {len(s['gaps'])} {s['gaps']}, "
            f"runs {s['scrape_runs_status_counts']}, key usage {s['listing_key_usage']}"
        )
        for cat, c in s["categories"].items():
            print(
                f"   [{cat}] listings {c['listings']}, with event {c['listings_with_event']}, "
                f"ev/listing 0/1/2/3+ {c['events_per_listing_0_1_2_3plus']}, "
                f"events {c['events_union']} by type {c['events_by_type']}"
            )
            bc = c["base_change_abs_pct"]
            print(
                f"        sub_threshold {c['sub_threshold']}, base_change |d|% median "
                f"{_fmt(bc['median'])} p90 {_fmt(bc['p90'])} max {_fmt(bc['max'])}, promo share "
                f"{_fmt(c['promo_listing_day_share'])}"
            )
            print(
                f"        evaluable strict {c['evaluable_strict']} lenient {c['evaluable_lenient']}"
            )
    v = rep["verdict"]
    print("\n== VERDICT (pre-registered rule)")
    print(
        f"   R1 {'PASS' if v['R1']['pass'] else 'FAIL'}: sources meeting >=28 days & <=2 gaps: {v['R1']['sources_meeting']} (need {v['R1']['need']})"
    )
    print(
        f"   R2 {'PASS' if v['R2']['pass'] else 'FAIL'}: holdout evaluable {v['R2']['holdout_evaluable_total']} (need {v['R2']['need_total']}); cells >=30: {v['R2']['cells_with_ge_30']} (need {v['R2']['need_cells']})"
    )
    print(
        f"   R3 {'PASS' if v['R3']['pass'] else 'FAIL'}: training evaluable {v['R3']['training_evaluable_total']} (need {v['R3']['need']})"
    )
    print(f"   OVERALL: {v['overall']}")
    if "remeasure" in v:
        print(f"   re-measure: {v['remeasure']}")
    print("\n== D2 new content_hash per collection day (x100 = daily scorings at K=100)")
    for src, d in rep["d2_incremental_matching_volume"].items():
        print(
            f"   {src}: initial load {d['first_day_initial_load']}, days {d['days_measured']}, {d['new_hashes_per_day']}, x100 {d['x100_daily_scorings']}"
        )
    st = rep["storage"]
    print("\n== Storage")
    print(
        f"   database {st['database_bytes'] / 1e6:.1f} MB over {st['collection_days_union']} collection days"
    )
    for t in st["top5_tables"]:
        print(f"   {t['table']}: {t['bytes'] / 1e6:.1f} MB, {t['rows']} rows")
    print(
        f"   growth/collection day (ESTIMATE): {st['avg_growth_bytes_per_collection_day_ESTIMATE']}"
    )
    print(
        f"   Neon free-tier limit: {st['neon_free_tier_limit_mb']}; until limit: {st['days_until_limit_ESTIMATE']}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--neon-limit-mb", type=float, default=None)
    ap.add_argument("--neon-limit-url", type=str, default=None)
    args = ap.parse_args()
    rep = measure(args.neon_limit_mb, args.neon_limit_url)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(rep, indent=2, default=str) + "\n", encoding="utf-8")
    print_report(rep)
    print(f"\nwritten: {OUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
