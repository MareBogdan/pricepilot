r"""STEP 3 — Phase 2 gate measurement: score the extractor against the hand-labelled gate sample.

    uv run python scripts/measure_gate.py

**Scores exactly ten fields — the ones an external model labelled without ever seeing this
repo or its code**: brand, net_weight_g, net_volume_ml, pack_count, bonus_weight_g,
breed_size_code, life_stage, flavour, food_form, dosage_band. `product_line` was labelled by the
architect session against a convention STEP 1 superseded — it carries no accuracy figure here and
is never read by this script's scoring loop.

**Four different denominators, reported explicitly, none hidden behind the others.** A first
version of this script reported one number — 966/1000 = 96.6% — scored against all 1,000 cells
(100 rows x 10 fields). That number is real but inflated: most fields are null on most rows (a
plain "Royal Canin Mini Adult 8 kg" correctly has no `dosage_band`, no `pack_count`, no
`bonus_weight_g`), so "both sides correctly produced nothing" dominates the count and drowns out
the cells that actually test something. `dosage_band` alone contributes 1 labelled cell and 99
such free points. A second version then scored only labelled cells (label non-empty) — closer,
but that denominator **cannot penalise a false positive** (the extractor inventing a value where
the label is empty): there is no label to compare against, so the cell is simply excluded from
both numerator and denominator, and the extractor gets no penalty for having been wrong. Two real
titles in this exact sample show why that matters: `"Hrana semi-umeda ... Semi-moist ..."`
(listing_id 28159, label empty, extractor said `"wet"`) and `"... Turkey Jerky ..."` (listing_id
28860, label empty, extractor said `"dry"`) — both real category errors, both invisible to a
labelled-cells-only score, and the first was gate-derived fix #3 in this same session. A
denominator that cannot see the error class a fix was written for is not measuring what matters.
So this script now reports four figures, in increasing order of how much they penalise a
mismatch:

1. **All cells** (1,000) — transparency only, never the headline.
2. **Labelled cells only** (label non-empty) — "recall on stated values": can the extractor
   reproduce a value a human said is actually stated? Cannot penalise a false positive (see
   above). Reported both across all ten fields and with `brand` excluded.
3. **Symmetric** (label non-empty OR extractor non-empty) — **the gate figure**: every cell where
   either side claims something is stated counts in the denominator, so a false positive lowers
   the score exactly as a miss does. Same numerator as (2) — a false-positive cell was never
   "correct" — larger denominator. Reported both across all ten fields and with `brand` excluded
   (the second is the headline).
4. **Weight parsing** (`net_weight_g`), on its own non-empty-label count, per CLAUDE.md §7.

Every per-field line prints its own labelled-cell count and symmetric-cell count alongside the
score, so a field with 1 labelled cell (`dosage_band`) can never be mistaken for one that was
actually measured 100 times.

**`brand` is excluded from every headline figure, deliberately, not just because its score is
lowest.** 12 of `brand`'s 15 mismatches (2026-09-14 session) come from the labeller seeing only
`title` text while `canonicalize_brand()` correctly prefers the shop's own structured brand field
when one exists — two different inputs to the same question, so this sample cannot grade that
field either way. It is neither an extractor bug nor a bad label. `brand`'s own correctness is
already checked a different, better way: STEP 1's cross-shop comparability test (same product,
different shops, same canonical brand — see DECISIONS.md ADR-0027).

**Comparison is case/whitespace-insensitive, decided before any number was computed, not after.**
The extractor's own documented convention stores every string field in a fixed casing (`"dry"`,
`"adult"`, `"brit"`); the external labeller wrote human-readable capitals (`"Dry"`, `"Adult"`,
`"Turkey"`) for the same values. Scoring case-sensitively would count that spelling difference as
an extraction bug, which it structurally cannot be — no downstream consumer of these fields reads
casing as meaningful. `dosage_band` additionally has the extractor's own space before "kg"
(`"12-25 kg"`) against the label's compact form (`"12-25kg"`); the same whitespace-insensitive
comparison absorbs that too. Numeric fields are compared as integers, not strings.

**A mismatch is one of three different bugs, counted separately**, per field: the extractor found
nothing where the label says something is stated (`extractor_null`); the extractor found
something where the label says nothing is stated (`extractor_has_extra` — a **false positive**,
worse than a miss because it writes a wrong value instead of an honest null); both sides have a
value and they disagree (`both_present_different`). `extractor_has_extra` cells are excluded from
the "labelled cells" (recall) denominator — there is no label to check them against — but they
ARE included in the "symmetric" denominator (the gate figure, see above), which is precisely why
that denominator exists: a metric that can never see a false positive can never penalise one.

**Nothing here adjusts the extractor.** This script only reads `norm_listings` and the labelled
CSV; it changes neither. Per the explicit instruction that produced this script's second version:
**do not re-run this after implementing gate-derived fixes and report a post-fix accuracy figure**
— once a fix is derived from a sample mismatch, re-scoring the same 100 rows is tuning on the test
set, and any number it produces is not comparable to the one that passed the gate. The number this
script prints is the measurement of record; see DECISIONS.md ADR-0027 for why it stays frozen.
"""

from __future__ import annotations

import csv
import io
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.models import NormListing, RawListing  # noqa: E402

LABELED_CSV = ROOT / "docs" / "learned" / "phase2-gate-sample-labeled.csv"

# The ten fields an independent, code-blind model labelled — these carry the gate.
# `product_line` is deliberately excluded: labelled by the architect session against a
# convention STEP 1 superseded, not part of this measurement.
GATE_FIELDS: tuple[str, ...] = (
    "brand",
    "net_weight_g",
    "net_volume_ml",
    "pack_count",
    "bonus_weight_g",
    "breed_size_code",
    "life_stage",
    "flavour",
    "food_form",
    "dosage_band",
)
# Excluded from every headline figure — see the module docstring for why (two different inputs,
# not an extractor bug or a bad label).
HEADLINE_FIELDS: tuple[str, ...] = tuple(f for f in GATE_FIELDS if f != "brand")
NUMERIC_FIELDS = frozenset({"net_weight_g", "net_volume_ml", "pack_count", "bonus_weight_g"})


def _normalize(field: str, raw: str | int | None) -> str | int | None:
    """Same normalization for both sides of the comparison — see the module docstring for why
    string fields are folded case/whitespace-insensitively and numeric fields as integers."""
    if raw is None:
        return None
    if field in NUMERIC_FIELDS:
        text = str(raw).strip()
        return int(text) if text else None
    text = str(raw).strip()
    if not text:
        return None
    return text.lower().replace(" ", "")


def main() -> int:
    if not LABELED_CSV.exists():
        print(f"labelled CSV not found: {LABELED_CSV}", file=sys.stderr)
        return 2
    if not check_database():
        print("database UNREACHABLE — run `docker compose up -d db`", file=sys.stderr)
        return 2

    with LABELED_CSV.open(encoding="utf-8-sig", newline="") as f:
        labeled_rows = list(csv.DictReader(f))
    print(f"labelled rows: {len(labeled_rows)}")

    listing_ids = [int(row["listing_id"]) for row in labeled_rows]

    with session_scope() as session:
        raw_by_id: dict[int, str] = {
            listing_id: content_hash
            for listing_id, content_hash in session.execute(
                select(RawListing.id, RawListing.content_hash).where(RawListing.id.in_(listing_ids))
            )
        }
        content_hashes = list(raw_by_id.values())
        norm_by_hash: dict[str, NormListing] = {
            row.content_hash: row
            for row in session.execute(
                select(NormListing).where(NormListing.content_hash.in_(content_hashes))
            ).scalars()
        }

    missing_norm = [lid for lid in listing_ids if raw_by_id.get(lid) not in norm_by_hash]
    if missing_norm:
        print(f"WARNING: {len(missing_norm)} listing_ids have no norm_listings row: {missing_norm}")

    # Per-field tallies.
    all_cells_exact: Counter[str] = Counter()  # correct among ALL 100 rows (incl. both-empty)
    labelled_n: Counter[str] = Counter()  # rows where the LABEL is non-empty
    labelled_correct: Counter[str] = Counter()  # correct among those labelled rows
    extractor_null: Counter[str] = Counter()  # label present, extractor null (miss)
    extractor_has_extra: Counter[str] = Counter()  # label empty, extractor non-null (false pos.)
    both_present_different: Counter[str] = Counter()  # both present, disagree
    scored: Counter[str] = Counter()  # rows actually compared (row present in norm_listings)

    mismatches: list[
        tuple[str, int, str, str, str, str]
    ] = []  # field, id, title, kind, expected, got

    for row in labeled_rows:
        listing_id = int(row["listing_id"])
        title = row["title"]
        content_hash = raw_by_id.get(listing_id)
        norm = norm_by_hash.get(content_hash) if content_hash else None
        if norm is None:
            continue

        for field in GATE_FIELDS:
            expected_raw = row.get(field, "")
            got_raw = getattr(norm, field)
            expected = _normalize(field, expected_raw)
            got = _normalize(field, got_raw)

            scored[field] += 1
            if expected is not None:
                labelled_n[field] += 1
            if expected == got:
                all_cells_exact[field] += 1
                if expected is not None:
                    labelled_correct[field] += 1
                continue

            if expected is not None and got is None:
                extractor_null[field] += 1
                kind = "extractor_null_label_has_value"
            elif expected is None and got is not None:
                extractor_has_extra[field] += 1
                kind = "extractor_has_value_label_null"
            else:
                both_present_different[field] += 1
                kind = "both_present_different"

            mismatches.append(
                (
                    field,
                    listing_id,
                    title,
                    kind,
                    "" if expected_raw is None else str(expected_raw),
                    "" if got_raw is None else str(got_raw),
                )
            )

    print("\n" + "=" * 88)
    print("PER-FIELD BREAKDOWN — labelled_n is the count of rows where a human stated a value;")
    print("the score is correct/labelled_n, NOT correct/100 (see module docstring)")
    print("=" * 88)
    for field in GATE_FIELDS:
        ln = labelled_n[field]
        lc = labelled_correct[field]
        sn = ln + extractor_has_extra[field]  # symmetric denominator: either side non-empty
        pct = (lc / ln * 100) if ln else float("nan")
        sym_pct = (lc / sn * 100) if sn else float("nan")
        marker = " (excluded from headline)" if field == "brand" else ""
        print(
            f"{field:18s} labelled_n={ln:3d}  correct={lc:3d}  "
            f"recall={pct:5.1f}%  symmetric_n={sn:3d}  symmetric={sym_pct:5.1f}%  "
            f"[all-cells exact={all_cells_exact[field]:3d}/{scored[field]:3d}]  "
            f"extractor_null={extractor_null[field]:2d}  "
            f"extractor_extra(false pos.)={extractor_has_extra[field]:2d}  "
            f"both_diff={both_present_different[field]:2d}{marker}"
        )

    # (1) All cells, all ten fields — transparency figure, never the headline.
    all_cells_total = sum(scored.values())
    all_cells_correct = sum(all_cells_exact.values())
    all_cells_pct = all_cells_correct / all_cells_total * 100 if all_cells_total else 0.0

    # (2) Labelled cells only ("recall on stated values") — cannot penalise a false positive;
    # see the module docstring for why that matters. Reported both with brand included and
    # excluded, but neither is the gate figure any more.
    labelled_all_total = sum(labelled_n.values())
    labelled_all_correct = sum(labelled_correct.values())
    labelled_all_pct = (
        labelled_all_correct / labelled_all_total * 100 if labelled_all_total else 0.0
    )
    headline_total = sum(labelled_n[f] for f in HEADLINE_FIELDS)
    headline_correct = sum(labelled_correct[f] for f in HEADLINE_FIELDS)
    headline_pct = headline_correct / headline_total * 100 if headline_total else 0.0

    # (3) Symmetric (labelled cells + false-positive cells) — THE GATE FIGURE. Same numerator as
    # (2); a false-positive cell adds to the denominator without ever being "correct", so it
    # lowers the score exactly as a miss does.
    all_false_positives = sum(extractor_has_extra.values())
    symmetric_all_total = labelled_all_total + all_false_positives
    symmetric_all_pct = (
        labelled_all_correct / symmetric_all_total * 100 if symmetric_all_total else 0.0
    )
    headline_false_positives = sum(extractor_has_extra[f] for f in HEADLINE_FIELDS)
    symmetric_headline_total = headline_total + headline_false_positives
    symmetric_headline_pct = (
        headline_correct / symmetric_headline_total * 100 if symmetric_headline_total else 0.0
    )

    print("\n" + "=" * 88)
    print("GATE FIGURES")
    print("=" * 88)
    print(
        f"  all cells (10 fields x 100 rows):                     {all_cells_correct}/{all_cells_total} = {all_cells_pct:.1f}%  (transparency only)"
    )
    print(
        f"  recall on stated values, brand included:              {labelled_all_correct}/{labelled_all_total} = {labelled_all_pct:.1f}%  (cannot penalise false positives)"
    )
    print(
        f"  recall on stated values, brand excluded:              {headline_correct}/{headline_total} = {headline_pct:.1f}%  (cannot penalise false positives)"
    )
    print(
        f"  symmetric (labelled + false positives), brand incl.:  {labelled_all_correct}/{symmetric_all_total} = {symmetric_all_pct:.1f}%"
    )
    print(
        f"  symmetric, brand EXCLUDED — THE GATE FIGURE:          {headline_correct}/{symmetric_headline_total} = {symmetric_headline_pct:.1f}%"
    )

    weight_n = labelled_n["net_weight_g"]
    weight_c = labelled_correct["net_weight_g"]
    weight_pct = (weight_c / weight_n * 100) if weight_n else 0.0
    print("\nWEIGHT PARSING (net_weight_g), measured separately per CLAUDE.md §7,")
    print(f"on its {weight_n} non-empty labels: {weight_c}/{weight_n} = {weight_pct:.1f}%")

    print("\n" + "=" * 88)
    print(f"EVERY MISMATCH ({len(mismatches)} total, across all ten fields including brand)")
    print("=" * 88)
    for field, listing_id, title, kind, expected, got in mismatches:
        print(f"\n[{field}] listing_id={listing_id} ({kind})")
        print(f"  title:    {title}")
        print(f"  expected: {expected!r}")
        print(f"  got:      {got!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
