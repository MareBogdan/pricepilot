r"""STEP 3 — Phase 2 gate measurement: score the extractor against the hand-labelled gate sample.

    uv run python scripts/measure_gate.py

**Scores exactly ten fields — the ones an external model labelled without ever seeing this
repo or its code**: brand, net_weight_g, net_volume_ml, pack_count, bonus_weight_g,
breed_size_code, life_stage, flavour, food_form, dosage_band. `product_line` was labelled by the
architect session against a convention STEP 1 superseded — it carries no accuracy figure here and
is never read by this script's scoring loop, per the explicit instruction that produced this
script.

**Per-field breakdown, not just a pass/fail count.** A mismatch is one of three different bugs,
counted separately: the extractor found nothing where the label says something is stated
(`extractor_null`); the extractor found something where the label says nothing is stated
(`extractor_has_extra`); both sides have a value and they disagree (`both_present_different`).
Collapsing these into one "wrong" bucket would hide which failure mode dominates — exactly the
information STEP 5's fix-priority list needs.

**Comparison is case/whitespace-insensitive, decided before any number was computed, not after.**
The extractor's own documented convention stores every string field in a fixed casing (`"dry"`,
`"adult"`, `"brit"`); the external labeller wrote human-readable capitals (`"Dry"`, `"Adult"`,
`"Turkey"`) for the same values. Scoring case-sensitively would count that spelling difference as
an extraction bug, which it structurally cannot be — no downstream consumer of these fields reads
casing as meaningful. `dosage_band` additionally has the extractor's own space before "kg"
(`"12-25 kg"`) against the label's compact form (`"12-25kg"`); the same whitespace-insensitive
comparison absorbs that too. Numeric fields are compared as integers, not strings.

**Nothing here adjusts the extractor.** This script only reads `norm_listings` (already
re-extracted under EXTRACTOR_VERSION 2026-09-14-v4) and the labelled CSV; it changes neither.
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
    exact: Counter[str] = Counter()
    extractor_null: Counter[str] = Counter()
    extractor_has_extra: Counter[str] = Counter()
    both_present_different: Counter[str] = Counter()
    scored: Counter[str] = Counter()  # rows actually compared (row present in norm_listings)

    mismatches: list[
        tuple[str, int, str, str, str, str]
    ] = []  # field, id, title, source, expected, got

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
            if expected == got:
                exact[field] += 1
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

    print("\n" + "=" * 78)
    print("PER-FIELD BREAKDOWN (the ten fields carrying the gate)")
    print("=" * 78)
    total_exact = 0
    total_scored = 0
    for field in GATE_FIELDS:
        n = scored[field]
        e = exact[field]
        total_exact += e
        total_scored += n
        pct = (e / n * 100) if n else 0.0
        print(
            f"{field:18s} exact={e:3d}/{n:3d} ({pct:5.1f}%)  "
            f"extractor_null={extractor_null[field]:2d}  "
            f"extractor_extra={extractor_has_extra[field]:2d}  "
            f"both_diff={both_present_different[field]:2d}"
        )

    overall = total_exact / total_scored * 100 if total_scored else 0.0
    print("\n" + "=" * 78)
    print(
        f"OVERALL ACCURACY across the ten gate fields: {total_exact}/{total_scored} = {overall:.1f}%"
    )
    print("=" * 78)

    weight_n = scored["net_weight_g"]
    weight_e = exact["net_weight_g"]
    weight_pct = (weight_e / weight_n * 100) if weight_n else 0.0
    print("\nWEIGHT PARSING (net_weight_g), measured separately per CLAUDE.md §7:")
    print(f"  {weight_e}/{weight_n} = {weight_pct:.1f}%")

    print("\n" + "=" * 78)
    print(f"EVERY MISMATCH ({len(mismatches)} total)")
    print("=" * 78)
    for field, listing_id, title, kind, expected, got in mismatches:
        print(f"\n[{field}] listing_id={listing_id} ({kind})")
        print(f"  title:    {title}")
        print(f"  expected: {expected!r}")
        print(f"  got:      {got!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
