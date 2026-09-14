r"""STEP 3 — Phase 2 gate measurement: score the extractor against the hand-labelled gate sample.

    uv run python scripts/measure_gate.py

**Scores exactly ten fields — the ones an external model labelled without ever seeing this
repo or its code**: brand, net_weight_g, net_volume_ml, pack_count, bonus_weight_g,
breed_size_code, life_stage, flavour, food_form, dosage_band. `product_line` was labelled by the
architect session against a convention STEP 1 superseded — it carries no accuracy figure here and
is never read by this script's scoring loop.

**Three different denominators, reported explicitly, none hidden behind the others.** A first
version of this script reported one number — 966/1000 = 96.6% — scored against all 1,000 cells
(100 rows x 10 fields). That number is real but inflated: most fields are null on most rows (a
plain "Royal Canin Mini Adult 8 kg" correctly has no `dosage_band`, no `pack_count`, no
`bonus_weight_g`), so "both sides correctly produced nothing" dominates the count and drowns out
the cells that actually test something. `dosage_band` alone contributes 1 labelled cell and 99
such free points. So this script now reports:

1. **All cells** (1,000) — kept for transparency, never the headline.
2. **Labelled cells only** (label non-empty) — the real test: can the extractor reproduce a
   value a human said is actually stated? This is reported both across all ten fields and with
   `brand` excluded (see below) — the second is the headline.
3. **Weight parsing** (`net_weight_g`), on its own non-empty-label count, per CLAUDE.md §7.

Every per-field line prints its own labelled-cell count alongside the score, so a field with 1
labelled cell (`dosage_band`) can never be mistaken for one that was actually measured 100 times.

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
worse than a miss because it writes a wrong value instead of an honest null, and specifically NOT
included in the "labelled cells" denominator since there is no label to check it against — that
denominator only ever answers "did the extractor reproduce a stated value", never "did the
extractor stay silent when it should have"; false positives are caught by population-level checks
instead, e.g. `scripts/measure_gate.py`'s STEP 5 fix list); both sides have a value and they
disagree (`both_present_different`).

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
        pct = (lc / ln * 100) if ln else float("nan")
        marker = " (excluded from headline)" if field == "brand" else ""
        print(
            f"{field:18s} labelled_n={ln:3d}  correct={lc:3d}  "
            f"score={pct:5.1f}%  "
            f"[all-cells exact={all_cells_exact[field]:3d}/{scored[field]:3d}]  "
            f"extractor_null={extractor_null[field]:2d}  "
            f"extractor_extra(false pos.)={extractor_has_extra[field]:2d}  "
            f"both_diff={both_present_different[field]:2d}{marker}"
        )

    # (1) All cells, all ten fields — transparency figure, never the headline.
    all_cells_total = sum(scored.values())
    all_cells_correct = sum(all_cells_exact.values())
    all_cells_pct = all_cells_correct / all_cells_total * 100 if all_cells_total else 0.0

    # (2) Labelled cells only, all ten fields (brand included) — the honest denominator, but
    # still mixes in the un-gradeable brand field.
    labelled_all_total = sum(labelled_n.values())
    labelled_all_correct = sum(labelled_correct.values())
    labelled_all_pct = (
        labelled_all_correct / labelled_all_total * 100 if labelled_all_total else 0.0
    )

    # (3) Labelled cells only, brand excluded — THE HEADLINE GATE NUMBER.
    headline_total = sum(labelled_n[f] for f in HEADLINE_FIELDS)
    headline_correct = sum(labelled_correct[f] for f in HEADLINE_FIELDS)
    headline_pct = headline_correct / headline_total * 100 if headline_total else 0.0

    print("\n" + "=" * 88)
    print("GATE FIGURES")
    print("=" * 88)
    print(
        f"  all cells (10 fields x 100 rows):            {all_cells_correct}/{all_cells_total} = {all_cells_pct:.1f}%  (transparency only — NOT the gate number)"
    )
    print(
        f"  labelled cells only, brand included:         {labelled_all_correct}/{labelled_all_total} = {labelled_all_pct:.1f}%"
    )
    print(
        f"  labelled cells only, brand EXCLUDED (HEADLINE, the gate number): {headline_correct}/{headline_total} = {headline_pct:.1f}%"
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
