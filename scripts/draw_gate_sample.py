r"""Draw the frozen Phase 2 gate sample — CLAUDE.md §7: ">=85% attribute accuracy on 100
manually verified listings, with weight parsing measured separately".

    uv run python scripts/draw_gate_sample.py

Writes `docs/learned/phase2-gate-sample.csv` (valid CSV, header row first — no preamble) and
`docs/learned/phase2-gate-sample-README.md` (the five conventions and labelling instructions).
The two used to be one file, with the conventions as a "#" comment block on top of the CSV — fixed
same-day, before labelling started: line 1 of that block contained a comma, so Excel, Google
Sheets and pandas all read it as the header row and scrambled every column. Split so the CSV is
actually valid CSV.

Run **once**, before any extractor code exists (STEP 2 of this session, ahead of STEP 3) — the
same discipline CLAUDE.md applies to a baseline before fine-tuning: the 100 rows are drawn and the
labeller works from them before the thing being measured is written, so the gate cannot be
measured on data the extractor was tuned against.

Every extracted-attribute column in the export is written EMPTY. Filling any of them here would
mean the gate measures the extractor against itself.

**Population.** In-scope rows only (`excluded_reason IS NULL`), deduplicated to one row per
`content_hash` — the same key `norm_listings` uses (ADR-0026), so each of the 100 rows represents
a genuinely distinct extraction case rather than the same title reappearing across collection
days. Stratified across sources, roughly proportional to each source's share of that deduplicated,
in-scope population.

**Deliberate hard-case inclusion.** CLAUDE.md §7 names ten known-hard title forms this sample must
not miss by chance: no weight in the title at all, weight as a leading token, decimal comma vs
point, missing diacritics, bonus packs, multipacks, dosage bands, breed-size codes, Romanian
descriptive prefixes, and special-character brands (Smolke, Hill's). For each, a small number of
matching rows are drawn first (with the same seeded RNG, so still reproducible), then the
remainder of the 100 is filled by the proportional random draw above, from what's left. The
detection regexes below are for **sample selection only** — a deliberately loose, separate pass
that finds candidates to include, never a data source for `norm_listings` and never reused by the
STEP 3 extractor.
"""

from __future__ import annotations

import csv
import io
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.models import RawListing  # noqa: E402
from pricepilot.overlap import bonus_weight_grams, net_weight_grams, strip_diacritics  # noqa: E402

SEED = 20260913  # recorded again in the README — see CLAUDE.md's dates-as-seeds convention
SAMPLE_SIZE = 100
OUTPUT_PATH = ROOT / "docs" / "learned" / "phase2-gate-sample.csv"
README_PATH = ROOT / "docs" / "learned" / "phase2-gate-sample-README.md"

ATTRIBUTE_COLUMNS: tuple[str, ...] = (
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

README_BODY = f"""\
# Phase 2 gate sample — read this before labelling `phase2-gate-sample.csv`

Frozen **2026-09-13**, seed **{SEED}**. This file used to be a comment block at the top of the
CSV itself — moved out because a "#" preamble containing commas is invalid CSV: line 1 had a
comma in it, so Excel, Google Sheets and pandas all read that line as the header and scrambled
every column. The CSV now starts directly with its real header row. Same 100 rows, same order,
same ids, still empty — nothing about the sample itself changed, only where this text lives.

**Do not edit the CSV's rows.** Fill in the attribute columns and the final `ambiguous` column
only, per the five conventions below. If you're unsure a row's answer follows from these
conventions unambiguously, flag it in `ambiguous` rather than guessing — a hand-check of every
flagged row (plus a random 10 of the rest) is part of the plan.

CLAUDE.md §7's Phase 2 gate: **>=85% attribute accuracy on these 100 listings, with weight
parsing measured separately.**

## The five conventions (decided, ADR-0026)

Apply these exactly, so the labeller and the extractor cannot diverge on definitions:

1. **Multipack** `"12x85 g"`: `net_weight_g = 85` (the single unit), `pack_count = 12`. Total mass
   is derived, never the stored net weight — a 12-pouch box and a single pouch are different
   purchasable units, and `pack_count` is what distinguishes them.
2. **Bonus pack** `"12+2 kg"`: `net_weight_g = 12000` (base), `bonus_weight_g = 2000`, recorded
   separately. Reuses `OverlapKey.bonus_g`'s existing semantics exactly — not a second,
   conflicting convention.
3. `"1 x 85 g"`: `pack_count = 1`, `net_weight_g = 85`.
4. **Dosage bands** (`"10-25 kg"`) are the **ANIMAL's** weight, never the product's. These must
   NEVER populate `net_weight_g` — the highest-risk confusion in this field.
5. **`brand` is the manufacturer, lowercased, in its simplest form** — added same-day, before
   labelling started, once it became clear brand form was otherwise undefined and a mismatch
   there would fail the gate on a definition disagreement rather than on a real extraction error:
   - `"brit"` (not `"Brit Premium"`)
   - `"hill's"` (not `"HILL'S Science Plan"`)
   - `"royal canin"`, `"calibra"`
   - The sub-line ("Premium by Nature", "Science Plan", "Life", "Care") belongs in
     `product_line`, never in `brand`. STEP 3's brand canonicalization targets exactly this
     shape — every variant a source writes maps onto it.

A quantity is mass-based XOR volume-based: fill **at most one** of `net_weight_g` /
`net_volume_ml` per row, never both (ADR-0026's DB-enforced invariant). Leave **both** empty when
the title states no quantity at all — that is a real, expected answer, not a gap.

Leave every attribute column empty until you are labelling for real — if you pre-fill any column,
the gate measures the extractor against itself.
"""

# ---------------------------------------------------------------------------
# Hard-case detectors — sample-selection only, never extraction logic.
# ---------------------------------------------------------------------------


def _fold(text: str) -> str:
    """Reuses `overlap.strip_diacritics` rather than re-deriving diacritic folding here — it
    already folds Smolke's o and Hill's curly/straight apostrophe identically (CLAUDE.md §7
    names both explicitly), and re-deriving it separately risked exactly the bug this file's
    first draft had: a bespoke fold that didn't touch apostrophes at all, so "Hill's" matched
    neither "hill's" nor "hills" and the special-char-brand detector silently found nothing
    genuine — caught by checking real candidate counts before freezing, not assumed correct."""
    return strip_diacritics(text).lower()


_LEADING_WEIGHT = re.compile(r"^\s*\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l)\b")
_COMMA_DECIMAL = re.compile(r"\d+,\d+\s*(?:kg|g|ml|l)\b")
_POINT_DECIMAL = re.compile(r"\d+\.\d+\s*(?:kg|g|ml|l)\b")
_MISSING_DIACRITICS = re.compile(r"\b(uscata|umeda|caini|catel)\b")
_MULTIPACK = re.compile(r"\d+\s*[x×]\s*\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l)\b")  # noqa: RUF001
_DOSAGE_BAND = re.compile(r"\b\d+\s*-\s*\d+\s*kg\b")
_BREED_SIZE = re.compile(r"\b(mini|medium|maxi|junior|senior|xs-xl|xs|xl)\b")
_RO_PREFIX = re.compile(r"^(hrana|recompense)\b")
# `strip_diacritics` folds ø->o (Smolke) and both apostrophe styles to a plain "'" (Hill's),
# but leaves the apostrophe itself in place — so "hill's" is what a genuine match looks like
# post-fold, not "hills" (that hit only "Manitoba Hills" — a false positive, verified and fixed
# before freezing this sample; see the docstring on `_fold` above).
_SPECIAL_BRAND = re.compile(r"(smolke|hill's)")


def hard_case_labels(title: str) -> set[str]:
    """Which of the ten CLAUDE.md §7 hard-case categories this title matches, if any. A title
    can match more than one (e.g. a bonus pack with no diacritics) — that's a bonus, not a bug."""
    folded = _fold(title)
    labels: set[str] = set()
    if net_weight_grams(title) is None:
        labels.add("no_weight_in_title")
    if _LEADING_WEIGHT.match(folded):
        labels.add("weight_leading_token")
    if _COMMA_DECIMAL.search(folded):
        labels.add("decimal_comma")
    if _POINT_DECIMAL.search(folded):
        labels.add("decimal_point")
    if _MISSING_DIACRITICS.search(folded):
        labels.add("missing_diacritics")
    if bonus_weight_grams(title) > 0:
        labels.add("bonus_pack")
    if _MULTIPACK.search(folded):
        labels.add("multipack")
    if _DOSAGE_BAND.search(folded):
        labels.add("dosage_band")
    if _BREED_SIZE.search(folded):
        labels.add("breed_size_code")
    if _RO_PREFIX.match(folded):
        labels.add("ro_descriptive_prefix")
    if _SPECIAL_BRAND.search(folded):
        labels.add("special_char_brand")
    return labels


# ---------------------------------------------------------------------------


def main() -> int:
    if not check_database():
        print("database UNREACHABLE — run `docker compose up -d db`", file=sys.stderr)
        return 2

    if OUTPUT_PATH.exists() or README_PATH.exists():
        print(
            f"{OUTPUT_PATH.name} or {README_PATH.name} already exists — refusing to overwrite a "
            "frozen gate sample. Delete both by hand first if you really mean to re-draw it.",
            file=sys.stderr,
        )
        return 1

    with session_scope() as session:
        rows = session.execute(
            select(RawListing.id, RawListing.source, RawListing.title, RawListing.content_hash)
            .where(RawListing.excluded_reason.is_(None))
            .order_by(RawListing.id)
        ).all()

    # Dedup to one representative row per content_hash — the same key norm_listings uses
    # (ADR-0026), so each sample row is a genuinely distinct extraction case, not the same
    # title reappearing across collection days.
    by_hash: dict[str, tuple[int, str, str]] = {}
    for row_id, source, title, content_hash in rows:
        by_hash.setdefault(content_hash, (row_id, source, title))
    population = list(by_hash.values())  # (id, source, title)

    print(f"in-scope rows: {len(rows):,}")
    print(f"distinct content_hash (dedup population): {len(population):,}")

    rng = random.Random(SEED)

    # -- pass 1: deliberate hard-case inclusion ---------------------------------------------
    by_label: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for item in population:
        for label in hard_case_labels(item[2]):
            by_label[label].append(item)

    HARD_CASE_TARGET_PER_LABEL = 2
    selected: dict[int, tuple[int, str, str]] = {}
    for label in sorted(by_label):
        candidates = by_label[label]
        rng.shuffle(candidates)
        picked = 0
        for item in candidates:
            if item[0] in selected:
                continue
            selected[item[0]] = item
            picked += 1
            if picked >= HARD_CASE_TARGET_PER_LABEL:
                break
        print(f"  hard case '{label}': {len(candidates)} candidates, {picked} selected")

    # -- pass 2: stratified proportional random fill to reach SAMPLE_SIZE -------------------
    by_source: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for item in population:
        by_source[item[1]].append(item)

    remaining_slots = SAMPLE_SIZE - len(selected)
    total_pop = len(population)
    for source in sorted(by_source):
        candidates = [item for item in by_source[source] if item[0] not in selected]
        rng.shuffle(candidates)
        share = round(remaining_slots * len(by_source[source]) / total_pop)
        for item in candidates[:share]:
            selected[item[0]] = item

    # Top up / trim to exactly SAMPLE_SIZE from whatever's left, in case rounding under/overshot.
    remaining_pool = [item for item in population if item[0] not in selected]
    rng.shuffle(remaining_pool)
    while len(selected) < SAMPLE_SIZE and remaining_pool:
        item = remaining_pool.pop()
        selected[item[0]] = item
    if len(selected) > SAMPLE_SIZE:
        overflow = list(selected.items())
        rng.shuffle(overflow)
        selected = dict(overflow[:SAMPLE_SIZE])

    final_rows = list(selected.values())
    rng.shuffle(final_rows)  # so the labeller can't infer selection reason from row order

    by_source_count: dict[str, int] = defaultdict(int)
    for _id, source, _title in final_rows:
        by_source_count[source] += 1
    print(f"\nfinal sample: {len(final_rows)} rows")
    for source in sorted(by_source_count):
        print(f"  {source}: {by_source_count[source]}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["listing_id", "source", "title", *ATTRIBUTE_COLUMNS, "ambiguous"])
        for row_id, source, title in final_rows:
            writer.writerow([row_id, source, title, *([""] * len(ATTRIBUTE_COLUMNS)), ""])
    README_PATH.write_text(README_BODY, encoding="utf-8")

    print(f"\nwrote {OUTPUT_PATH}")
    print(f"wrote {README_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
