r"""STEP 4 — Phase 2 coverage report: per field, per source, what fraction of `norm_listings`
got a non-null value, plus the worst fields' top failure shapes with real example titles.

    uv run python scripts/normalize_coverage.py

**Coverage, not accuracy.** The Phase 2 gate (CLAUDE.md §7: >=85% attribute accuracy on 100
manually verified listings) waits on Bogdan labelling `docs/learned/phase2-gate-sample.csv` — that
sample is frozen and unlabelled, so there is nothing to score against yet. This script answers a
different, honest question instead: for every field, on every already-extracted row, how often did
the extractor produce *something*? A field can have 100% coverage and still be wrong on every row
(coverage is not correctness) — the gate sample is what will eventually say which fields are
right, not this report. This report exists so weak fields are visible before the labelled numbers
arrive, not after.
"""

from __future__ import annotations

import io
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.models import NormListing  # noqa: E402

FIELDS: tuple[str, ...] = (
    "brand",
    "product_line",
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

# net_weight_g and net_volume_ml are mutually exclusive by construction (ADR-0026) — reporting
# them separately would understate "quantity found at all" for the many volume-based listings
# that correctly leave net_weight_g null. Combined coverage answers the field's real question.
COMBINED_QUANTITY_FIELDS = ("net_weight_g", "net_volume_ml")

# Fields deliberately left OUT of "worst fields" failure-shape analysis, because low coverage
# there is the structurally expected outcome, not a signal of a broken extractor:
#   - product_line: not built this session (STATE.md Open issues) — 0% is documented, not a
#     surprise a report should be "discovering".
#   - bonus_weight_g, dosage_band, pack_count: most listings genuinely have no bonus pack, no
#     dosage band, no multipack — a plain "Royal Canin Mini Adult 8 kg" correctly leaves all
#     three null, and listing it as a "failure shape" would be misleading, not diagnostic.
# The quantity/flavour/food_form/breed_size/life_stage fields below are where a title plausibly
# *does* carry the signal and coverage gaps are worth explaining.
_EXCLUDED_FROM_FAILURE_ANALYSIS = frozenset(
    {"product_line", "bonus_weight_g", "dosage_band", "pack_count"}
)

TOP_SHAPES_PER_FIELD = 5
EXAMPLES_PER_SHAPE = 3

# Word-boundary, not a bare substring check: an early version of this used `"g " in title.lower()`
# and matched "Viking Roll" (the "g " inside "Viking") as if it were a weight unit — a bug in this
# diagnostic bucketing only (the real extractor's own regex was never affected, it already used
# `\b`), caught by checking one of its own flagged examples before trusting the bucket label.
_UNIT_HINT_PATTERN = re.compile(r"\b(kg|g|ml|l|gr)\b")


def _quantity_shape(title: str) -> str:
    folded = title.lower()
    if any(ch.isdigit() for ch in title):
        if _UNIT_HINT_PATTERN.search(folded):
            return (
                "has a number and a recognizable unit word, but the quantity regex still missed it"
            )
        return "has a number, no recognizable unit — likely no stated quantity at all"
    return "no digits at all in the title — no quantity possible"


def _cross_field_shape(other_field_present: bool, other_field_name: str) -> str:
    """For flavour/food_form specifically: a null here is a real gap only if the *other* of the
    pair is present (a food item, correctly identified as such, that still lacks a flavour or
    form word) — the far more common case is a non-food listing (toy, litter, accessory) where
    neither field applies, which is not a failure at all."""
    if other_field_present:
        return (
            f"likely a real food item ({other_field_name} was found) — this field's word was missed"
        )
    return f"{other_field_name} is also null — likely not a food item at all, not a real gap"


def main() -> int:
    if not check_database():
        print("database UNREACHABLE — run `docker compose up -d db`", file=sys.stderr)
        return 2

    with session_scope() as session:
        rows = session.execute(
            select(
                NormListing.sample_source,
                NormListing.sample_title,
                NormListing.brand,
                NormListing.product_line,
                NormListing.net_weight_g,
                NormListing.net_volume_ml,
                NormListing.pack_count,
                NormListing.bonus_weight_g,
                NormListing.breed_size_code,
                NormListing.life_stage,
                NormListing.flavour,
                NormListing.food_form,
                NormListing.dosage_band,
            )
        ).all()

    if not rows:
        print("norm_listings is empty — run `uv run python scripts/normalize.py` first.")
        return 1

    total_by_source: Counter[str] = Counter()
    non_null_by_source_field: dict[str, Counter[str]] = defaultdict(Counter)
    non_null_overall_field: Counter[str] = Counter()
    quantity_non_null_overall = 0
    quantity_non_null_by_source: Counter[str] = Counter()
    null_examples: dict[str, list[tuple[str, str]]] = defaultdict(list)
    null_shape_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for row in rows:
        source = row.sample_source
        title = row.sample_title
        values = dict(zip(FIELDS, row[2:], strict=True))

        total_by_source[source] += 1
        quantity_found = any(values[f] is not None for f in COMBINED_QUANTITY_FIELDS)
        if quantity_found:
            quantity_non_null_overall += 1
            quantity_non_null_by_source[source] += 1

        for field_name, value in values.items():
            if value is not None:
                non_null_by_source_field[field_name][source] += 1
                non_null_overall_field[field_name] += 1

        # Failure-shape analysis, one entry per ROW per field (not per sub-field), so a row
        # missing both net_weight_g and net_volume_ml is counted once under "quantity", not
        # twice — double-counting there would inflate the shape totals to 2x the real row count.
        if not quantity_found:
            shape = _quantity_shape(title)
            null_shape_counts["quantity"][shape] += 1
            if len(null_examples["quantity"]) < 200:
                null_examples["quantity"].append((shape, title))

        for field_name in FIELDS:
            if (
                field_name in COMBINED_QUANTITY_FIELDS
                or field_name in _EXCLUDED_FROM_FAILURE_ANALYSIS
            ):
                continue
            if values[field_name] is not None:
                continue
            if field_name == "flavour":
                shape = _cross_field_shape(values["food_form"] is not None, "food_form")
            elif field_name == "food_form":
                shape = _cross_field_shape(values["flavour"] is not None, "flavour")
            else:
                shape = "no sub-shape built for this field — raw examples only"
            null_shape_counts[field_name][shape] += 1
            if len(null_examples[field_name]) < 200:
                null_examples[field_name].append((shape, title))

    total = len(rows)
    sources = sorted(total_by_source)

    print(f"norm_listings rows: {total:,}\n")

    print("quantity found (net_weight_g OR net_volume_ml non-null):")
    print(
        f"  overall: {quantity_non_null_overall:,}/{total:,} ({quantity_non_null_overall / total:.1%})"
    )
    for source in sources:
        n = quantity_non_null_by_source[source]
        d = total_by_source[source]
        print(f"    {source}: {n:,}/{d:,} ({n / d:.1%})")
    print()

    print(f"{'field':<20} {'overall':>16}  " + "  ".join(f"{s:>22}" for s in sources))
    for field_name in FIELDS:
        overall_n = non_null_overall_field[field_name]
        overall_pct = f"{overall_n:,}/{total:,} ({overall_n / total:.1%})"
        per_source = []
        for source in sources:
            n = non_null_by_source_field[field_name][source]
            d = total_by_source[source]
            per_source.append(f"{n:,}/{d:,} ({n / d:.1%})")
        print(f"{field_name:<20} {overall_pct:>16}  " + "  ".join(f"{p:>22}" for p in per_source))

    print("\n" + "=" * 78)
    print("Worst fields — top failure shapes with real examples")
    print("=" * 78)
    print(
        f"(excluded from this section: {', '.join(sorted(_EXCLUDED_FROM_FAILURE_ANALYSIS))} — "
        "low coverage there is the structurally expected outcome, not a diagnostic signal; "
        "see the field-coverage table above for their numbers)"
    )

    analyzable_fields = ["quantity", *(f for f in FIELDS if f not in COMBINED_QUANTITY_FIELDS)]
    analyzable_fields = [f for f in analyzable_fields if f not in _EXCLUDED_FROM_FAILURE_ANALYSIS]
    coverage_for_ranking = {
        "quantity": quantity_non_null_overall,
        **{f: non_null_overall_field[f] for f in analyzable_fields if f != "quantity"},
    }
    worst_fields = sorted(analyzable_fields, key=lambda f: coverage_for_ranking[f])[:6]

    for field_name in worst_fields:
        coverage = coverage_for_ranking[field_name] / total
        print(f"\n{field_name}: {coverage:.1%} coverage")
        for shape, count in null_shape_counts[field_name].most_common(TOP_SHAPES_PER_FIELD):
            print(f"  [{count:,}] {shape}")
            examples = [t for s, t in null_examples[field_name] if s == shape][:EXAMPLES_PER_SHAPE]
            for example in examples:
                print(f"      e.g. {example}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
