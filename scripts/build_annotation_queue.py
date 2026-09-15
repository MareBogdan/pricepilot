r"""Phase 3 STEP 6, rebuilt (ADR-0028 TASK 4) — annotation queue with a DESIGNED class balance,
not whatever a single SQL query happens to return.

    uv run python scripts/build_annotation_queue.py

**Why the first version (committed, ADR-0028 STEP 6) is replaced, not amended.** An architect
audit found it unusable: 894 of its 1,000 pairs had differing capacity, a class convention 1
decides as N with zero human judgment, and EVERY "hard" pair was in that group — because the SQL
that sourced the hard tier selected FOR differing capacity or flavour, making them negatives by
construction. Only ~36 pairs in the whole queue were genuinely uncertain. That is ~963 human
decisions to surface at most ~36 new positive examples, and a dataset where one feature (capacity
equality) predicts the great majority of the labels teaches a matcher to compare two numbers and
nothing else. Full finding: DECISIONS.md ADR-0028.

**This version draws from NAMED, QUOTA'D sources instead of one query the tier classifier sorted
after the fact.** Each source below is its own targeted SQL query, capped or floored to a designed
share of the queue:

1. **Positives (target >=25% of the queue), from two sources that don't depend on the retriever
   being measured:**
   - `proxy_key_collision` — the Phase 1 overlap proxy key (`overlap.py`, ADR-0023, ~96% precision
     on its own hand-checked sample) recomputed over the current in-scope population; cross-shop
     pairs sharing a key.
   - `blocked_retrieval` — TASK 2b's blocked candidate retrieval (rank by embedding distance
     *inside* the query row's own `brand_blocking_key` block) — the same mechanism
     `measure_recall_at_20.py` now uses, reused here as a candidate generator, not a truth source.
     Plausible, not guaranteed positives; the annotator's M/N decision is still the ground truth.
   (TASK 1's identical-title cross-shop collisions are NOT wired in here — those two listings
   collapse to a single `norm_listings` row under ADR-0026's global content_hash key, so there is
   no second row for the tool to show. ADR-0028 records the count and proposes, but does not
   implement, how to surface them; doing that is a data-model change, not a queue-composition one.)

2. **`capacity_differs`, capped at ~30% of the queue** (cross-shop and within-shop combined). The
   dominant REAL negative class — same brand+line, different net_weight_g/net_volume_ml/pack_count
   /bonus_weight_g — kept because it matters, capped so it cannot decide the dataset the way it did
   before.

3. **Four required negative/hard sub-classes, each its own targeted query with its own quota:**
   `same_capacity_diff_flavour`, `same_capacity_diff_lifestage` (flavour held equal), `same_
   capacity_diff_breedsize`, `diff_brand_similar_title` (same product_line text, different
   `brand_blocking_key` — could be a distributor-code artifact, rule 5, or a genuinely different
   manufacturer; deliberately ambiguous, that is why it is a good hard case).

4. **`reformulation_approx`** — same brand_blocking_key + product_line, one side's title carries a
   reformulation marker (`"noua formula"`, `"reformulat"`, `"new formula"`, generation wording).
   **Approximate, not authoritative** — no structured "generation" field exists yet, so this is a
   keyword search over `sample_title`, named as an approximation in its own query, not silently
   presented as reliable. Per the annotation conventions' rule 7 this tier is usually M-flagged,
   not N — it is a HARD case, not a guaranteed negative, included for that reason.

5. **`within_shop_hard`** — hard negatives where BOTH sides are the SAME source (`sample_source`
   equal), same brand+line, differing capacity. The 2026-09-13 diagnostic found ~1,919 of these in
   the population; the first queue version had zero (100% cross-shop). Given its own quota here so
   it cannot be crowded out by the cross-shop sourcing above.

**The guard (new, permanent).** Before writing anything, compute what fraction of the assembled
queue a SINGLE deterministic feature decides on its own: `capacity_differs` (forces N under
convention rule 1, unconditionally), `flavour_differs` (both sides stated, rule 4), `brand_differs`
(canonical `brand` string). Each is the same computation that produced "894 of 1,000" for the first
version's capacity feature. **If any one exceeds 40% of the queue, the script refuses to write the
file** and prints which feature dominates and by how much — a loud failure at build time, not a
finding an audit has to catch afterwards.

Output: `docs/learned/phase3-annotation-queue.json` (only on a passing guard) and a console report
— per-category counts vs quota, the predicted M/S/N-leaning composition, the guard figures, and
the revised wall-clock estimate. Writes nothing to the database and starts no annotation.
"""

from __future__ import annotations

import io
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text  # noqa: E402

from pricepilot.db import check_database, session_scope  # noqa: E402
from pricepilot.normalize.attributes import breed_size_overlaps  # noqa: E402
from pricepilot.overlap import overlap_key  # noqa: E402

OUTPUT_JSON = ROOT / "docs" / "learned" / "phase3-annotation-queue.json"

TOP_K = 20
QUEUE_SIZE_TARGET = 1000
SPOT_CHECK_TRIVIAL_COUNT = 50
SHUFFLE_SEED = 20260915
RNG_SEED = 20260915
SINGLE_FEATURE_DOMINANCE_LIMIT = 0.40

# Quotas as a share of QUEUE_SIZE_TARGET (non-trivial portion). Positives >=25% (28% designed in,
# for margin), capacity_differs capped at 30%, everything else a required, separately-sourced
# hard/negative sub-class. Sums to 1.00 over the non-trivial queue.
QUOTA_SHARES: dict[str, float] = {
    "proxy_key_collision": 0.25,
    "blocked_retrieval_candidate": 0.13,  # positives total: 38% (>=25% floor, margin for shortfall)
    "capacity_differs_cross_shop": 0.22,
    "capacity_differs_within_shop": 0.08,  # capacity_differs total: 30% (the cap)
    "same_capacity_diff_flavour": 0.09,
    "same_capacity_diff_lifestage": 0.07,
    "same_capacity_diff_breedsize": 0.05,
    "diff_brand_similar_title": 0.07,
    "reformulation_approx": 0.04,
}
assert abs(sum(QUOTA_SHARES.values()) - 1.0) < 1e-9, "QUOTA_SHARES must sum to 1.0"

ATTR_FIELDS = (
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
    "sample_source",
    "sample_title",
    "brand_blocking_key",
    "category",
    "species",
    "breed_size_class",
)

_ATTRS_SQL = text(
    f"select content_hash, {', '.join(ATTR_FIELDS)} from norm_listings where content_hash = any(:hashes)"
)

# --- Category queries -------------------------------------------------------------------------
# Each returns (a_hash, b_hash) pairs. Cross-shop vs within-shop is enforced in Python after
# fetching Listing objects (needs `.source`), same as the first version.

_CAPACITY_DIFFERS_SQL = text(
    """
    select a.content_hash, b.content_hash
    from norm_listings a
    join norm_listings b
      on a.brand_blocking_key = b.brand_blocking_key
     and a.brand_blocking_key is not null
     and lower(trim(a.product_line)) = lower(trim(b.product_line))
     and a.product_line is not null
     and a.content_hash < b.content_hash
     and (
           a.net_weight_g is distinct from b.net_weight_g
        or a.net_volume_ml is distinct from b.net_volume_ml
        or a.pack_count is distinct from b.pack_count
        or a.bonus_weight_g is distinct from b.bonus_weight_g
     )
    """
)

# NOTE: these three DELIBERATELY do not require product_line equality — requiring it
# alongside an exact quantity-tuple match and a differing flavour/life_stage/breed_size
# returned ZERO rows against the real population (checked, not assumed: STEP 3's
# product_line strips exactly the kind of qualifier these categories key on, so an
# identical product_line plus a differing flavour is nearly a contradiction in the data
# as it exists today). Same brand_blocking_key is kept as the one requirement tying the
# pair to a real shared manufacturer/line family.
_SAME_CAPACITY_DIFF_FLAVOUR_SQL = text(
    """
    select a.content_hash, b.content_hash
    from norm_listings a
    join norm_listings b
      on a.brand_blocking_key = b.brand_blocking_key
     and a.brand_blocking_key is not null
     and a.content_hash < b.content_hash
     and a.net_weight_g is not distinct from b.net_weight_g
     and a.net_volume_ml is not distinct from b.net_volume_ml
     and a.pack_count is not distinct from b.pack_count
     and a.bonus_weight_g is not distinct from b.bonus_weight_g
     and a.flavour is not null and b.flavour is not null and a.flavour <> b.flavour
    """
)

_SAME_CAPACITY_DIFF_LIFESTAGE_SQL = text(
    """
    select a.content_hash, b.content_hash
    from norm_listings a
    join norm_listings b
      on a.brand_blocking_key = b.brand_blocking_key
     and a.brand_blocking_key is not null
     and a.content_hash < b.content_hash
     and a.net_weight_g is not distinct from b.net_weight_g
     and a.net_volume_ml is not distinct from b.net_volume_ml
     and a.pack_count is not distinct from b.pack_count
     and a.bonus_weight_g is not distinct from b.bonus_weight_g
     and a.flavour is not distinct from b.flavour
     and a.life_stage is not null and b.life_stage is not null and a.life_stage <> b.life_stage
    """
)

_SAME_CAPACITY_DIFF_BREEDSIZE_SQL = text(
    """
    select a.content_hash, b.content_hash
    from norm_listings a
    join norm_listings b
      on a.brand_blocking_key = b.brand_blocking_key
     and a.brand_blocking_key is not null
     and a.content_hash < b.content_hash
     and a.net_weight_g is not distinct from b.net_weight_g
     and a.net_volume_ml is not distinct from b.net_volume_ml
     and a.pack_count is not distinct from b.pack_count
     and a.bonus_weight_g is not distinct from b.bonus_weight_g
     and a.breed_size_code is not null and b.breed_size_code is not null
     and a.breed_size_code <> b.breed_size_code
    """
)

_DIFF_BRAND_SIMILAR_TITLE_SQL = text(
    """
    select a.content_hash, b.content_hash
    from norm_listings a
    join norm_listings b
      on a.brand_blocking_key <> b.brand_blocking_key
     and a.brand_blocking_key is not null and b.brand_blocking_key is not null
     and lower(trim(a.product_line)) = lower(trim(b.product_line))
     and a.product_line is not null
     and a.content_hash < b.content_hash
     and a.net_weight_g is not distinct from b.net_weight_g
     and a.net_volume_ml is not distinct from b.net_volume_ml
     and a.pack_count is not distinct from b.pack_count
     and a.bonus_weight_g is not distinct from b.bonus_weight_g
    """
)

# Approximate — no structured "generation"/"reformulated" field exists. Keyword search over the
# raw sample_title, named as an approximation in the module docstring, not presented as reliable.
_REFORMULATION_MARKERS = (
    "%noua formula%",
    "%noua reteta%",
    "%reformulat%",
    "%new formula%",
    "%new recipe%",
    "%formula imbunatatita%",
    "%generatie noua%",
)
_REFORMULATION_APPROX_SQL = text(
    """
    select a.content_hash, b.content_hash
    from norm_listings a
    join norm_listings b
      on a.brand_blocking_key = b.brand_blocking_key
     and a.brand_blocking_key is not null
     and lower(trim(a.product_line)) = lower(trim(b.product_line))
     and a.product_line is not null
     and a.content_hash < b.content_hash
    where (
        lower(a.sample_title) like any(:markers) or lower(b.sample_title) like any(:markers)
    )
    """
)

_BLOCKED_RETRIEVAL_ANCHOR_SQL = text(
    "select content_hash, brand_blocking_key from norm_listings "
    "where embedding is not null and brand_blocking_key is not null "
    "and brand_is_distributor_code = false order by random() limit :n"
)
_BLOCKED_RETRIEVAL_CANDIDATES_SQL = text(
    """
    select content_hash
    from norm_listings
    where embedding is not null
      and content_hash != :self_hash
      and brand_blocking_key = :brand_key
      and brand_is_distributor_code = false
    order by embedding <=> (select embedding from norm_listings where content_hash = :self_hash)
    limit :k
    """
)

# Proxy-key source: needs the SHOP's raw brand text + title (overlap_key() is title/brand-only,
# independent of norm_listings/embeddings by construction, same independence STEP 1's eval set
# relies on) plus the content_hash to join back to norm_listings for display.
_RAW_FOR_PROXY_KEY_SQL = text(
    """
    select distinct on (rl.content_hash) rl.content_hash, rl.source, rl.title, rl.raw_payload
    from raw_listings rl
    join norm_listings nl on nl.content_hash = rl.content_hash
    where rl.excluded_reason is null
    order by rl.content_hash, rl.id
    """
)


@dataclass(frozen=True)
class Listing:
    content_hash: str
    brand: str | None
    product_line: str | None
    net_weight_g: int | None
    net_volume_ml: int | None
    pack_count: int | None
    bonus_weight_g: int | None
    breed_size_code: str | None
    life_stage: str | None
    flavour: str | None
    food_form: str | None
    source: str
    title: str
    brand_blocking_key: str | None
    category: str | None
    species: str | None
    breed_size_class: str | None


def _norm_line(s: str | None) -> str | None:
    return s.strip().lower() if s else None


def classify_tier(left: Listing, right: Listing) -> str:
    """Kept for the trivial/auto-label pass only (unrelated to the category sourcing above)."""
    same_brand = left.brand == right.brand and left.brand is not None
    same_line = bool(left.product_line) and _norm_line(left.product_line) == _norm_line(
        right.product_line
    )
    same_capacity = (
        left.net_weight_g == right.net_weight_g and left.net_volume_ml == right.net_volume_ml
    )
    same_pack = left.pack_count == right.pack_count
    same_bonus = left.bonus_weight_g == right.bonus_weight_g
    if same_brand and same_line and same_capacity and same_pack and same_bonus:
        return "trivial"
    return "candidate"


def _fetch_listings(session, hashes: set[str]) -> dict[str, Listing]:  # type: ignore[no-untyped-def]
    if not hashes:
        return {}
    rows = session.execute(_ATTRS_SQL, {"hashes": list(hashes)}).all()
    return {
        row.content_hash: Listing(
            content_hash=row.content_hash,
            brand=row.brand,
            product_line=row.product_line,
            net_weight_g=row.net_weight_g,
            net_volume_ml=row.net_volume_ml,
            pack_count=row.pack_count,
            bonus_weight_g=row.bonus_weight_g,
            breed_size_code=row.breed_size_code,
            life_stage=row.life_stage,
            flavour=row.flavour,
            food_form=row.food_form,
            source=row.sample_source,
            title=row.sample_title,
            brand_blocking_key=row.brand_blocking_key,
            category=row.category,
            species=row.species,
            breed_size_class=row.breed_size_class,
        )
        for row in rows
    }


def _dedup_pairs(rows: list[tuple[str, str]], seen: set[tuple[str, str]]) -> list[tuple[str, str]]:
    out = []
    for a, b in rows:
        key = (a, b) if a < b else (b, a)
        if key in seen:
            continue
        seen.add(key)
        out.append((a, b))
    return out


# --- TASK B (ADR-0028 architect-audit response #2) — a deterministic rules engine that applies
# `docs/learned/phase3-annotation-conventions.md` revision 2's ladder to every queue pair, so the
# queue's own headline statistic is a FORECAST of the annotator's actual workload (M-plausible /
# N-by-rule / S-likely), not a source-tier label that asserts nothing about how a pair will
# actually be decided. **This forecast is read-only** — it is never written into the pair, never
# used to auto-label anything beyond the pre-existing trivial-tier pass, and the annotator's own
# M/N/S decision remains the only ground truth this project trusts. Conservative by design: an
# N-rule only fires when BOTH sides state the field being compared (matches rule 6/8's own "don't
# guess on a one-sided field" discipline) — a one-sided field is scored `S`, not guessed either
# way, even though that under-counts how many pairs the ladder could *in principle* decide.

# Rule 2's life-stage equivalence: our schema's `life_stage` field only ever holds one of these
# four values (checked against the real population — no separate "kitten" or "7+" value exists,
# Phase 2's own extraction already folds them in). Grouped per this task's explicit instruction —
# puppy/junior collapse to one "young" class for this forecast, so the ladder does not fire on a
# distinction our structured data cannot actually see cleanly, keeping the N-count a defensible
# floor rather than an inflated one.
_LIFE_STAGE_GROUP = {"puppy": "young", "junior": "young", "adult": "adult", "senior": "senior"}

_IN_SCOPE_CATEGORIES = frozenset({"food", "litter"})


def _quantity_tuple(listing: Listing) -> tuple[int | None, int | None, int, int]:
    pack = listing.pack_count if listing.pack_count is not None else 1
    bonus = listing.bonus_weight_g if listing.bonus_weight_g is not None else 0
    return (listing.net_weight_g, listing.net_volume_ml, pack, bonus)


def _has_quantity(listing: Listing) -> bool:
    return listing.net_weight_g is not None or listing.net_volume_ml is not None


def predict_label(left: Listing, right: Listing) -> tuple[str, str]:
    """Applies the conventions-v3 ladder deterministically (`phase3-annotation-conventions.md`,
    revision 3 — species inserted as Rule 1, revision 2's rules 1-8 renumbered to 2-9). Returns
    (label, rule) where label is "M" | "N" | "S" and `rule` names which rule decided it (or
    "default_M" / "ambiguous_brand_rule6" for the fall-through cases). Order matches the ladder:
    the first rule that fires wins."""
    # Rule 0 — scope. Accessory/toy/unknown listings are out of round 1's scope entirely. As of
    # finding 8 (2026-09-15 reference labelling pass), the SOURCE SQL queries now filter to
    # category in ('food', 'litter') directly (main(), `in_scope_only()`) — this rule stays as a
    # forecast-only backstop for any row a source query somehow still let through, not the only
    # thing standing between an accessory and the queue the way it was before.
    if (left.category not in _IN_SCOPE_CATEGORIES) or (right.category not in _IN_SCOPE_CATEGORIES):
        return "S", "rule0_out_of_scope"

    # Rule 1 — species (revision 3, finding 4, 2026-09-15 session). Dog food and cat food are
    # never the same product, and this is the single most certain, cheapest N-rule available once
    # both sides state a species (`normalize.species.classify_species`) — ahead of quantity
    # because a species mismatch makes the quantity comparison moot, and it's what the
    # conventions doc's own revision-3 ladder now says explicitly. Conservative like every other
    # rule here: fires only when BOTH sides resolve to a species; a one-sided/unknown species
    # falls through untouched (may still land on `S` via rule 7 below if quantity is also
    # missing, or ride an otherwise-M pair through unaffected).
    if left.species and right.species and left.species != right.species:
        return "N", "rule1_species_differs"

    # Rule 7 — quantity not stated on one side: cannot even test rule 2. Checked here, ahead of
    # rule 2 in execution order, for the same reason it always was: you cannot compare a tuple
    # against a missing one. (The conventions doc lists it at ladder position 7, for a human
    # reading the rules in priority order — its necessary execution position doesn't move.)
    if not _has_quantity(left) or not _has_quantity(right):
        return "S", "rule7_no_quantity_stated"

    # Rule 2 — quantity tuple differs -> N, always, no exceptions.
    if _quantity_tuple(left) != _quantity_tuple(right):
        return "N", "rule2_quantity_differs"

    # Rule 3 — life stage (formula-defining qualifier), grouped per this task's instruction.
    if left.life_stage and right.life_stage:
        lg = _LIFE_STAGE_GROUP.get(left.life_stage, left.life_stage)
        rg = _LIFE_STAGE_GROUP.get(right.life_stage, right.life_stage)
        if lg != rg:
            return "N", "rule3_lifestage_differs"

    # Rule 4 — breed size differs. Finding 5 (2026-09-15 session): compares the CANONICAL rank
    # interval (`breed_size_class`/`breed_size_overlaps`), not the raw string — "Medium" and "M"
    # are the same size (a real cross-shop match, pilot 12) and a raw-string check would wrongly
    # force this pair N. `breed_size_overlaps()` returns `False` only when both sides map to a
    # rank interval AND those intervals share no rank at all (confidently different sizes);
    # `None` (one/both unmapped) falls through to the one-sided check below, same as before.
    if breed_size_overlaps(left.breed_size_code, right.breed_size_code) is False:
        return "N", "rule4_breedsize_differs"

    # Rule 5 — flavour differs (both stated). Cross-language equivalence (Salmon/Somon etc.) is
    # already resolved upstream by `normalize/flavour.py` before this field is stored, so a plain
    # string-inequality check here is correct, not naive.
    if left.flavour and right.flavour and left.flavour != right.flavour:
        return "N", "rule5_flavour_differs"

    # Everything that forces N has now had its chance. A one-sided flavour/life_stage/breed_size
    # is a real gap the ladder can't close without a guess — score S, not M, per the "never guess"
    # discipline (rule 7/9).
    one_sided = (
        (left.flavour is None) != (right.flavour is None)
        or (left.life_stage is None) != (right.life_stage is None)
        or (left.breed_size_code is None) != (right.breed_size_code is None)
    )
    if one_sided:
        return "S", "one_sided_attribute"

    # Rule 6 — brand string differs. Could be M (distributor-code provenance) or a genuinely
    # different manufacturer; rule 6 explicitly requires reading the title/packaging to tell them
    # apart, which this forecast cannot automate. Scored S, not guessed as M.
    if left.brand != right.brand:
        return "S", "ambiguous_brand_rule6"

    return "M", "default_M"


def forecast_queue(
    human_pairs: list[tuple[str, str]], listings: dict[str, Listing]
) -> tuple[dict[str, int], dict[str, int]]:
    """Returns (label_counts, n_rule_counts) — the three-way M/N/S forecast and, for the N bucket
    only, which rule fired how often (so the headline print can show the breakdown, not just the
    total)."""
    label_counts: dict[str, int] = {"M": 0, "N": 0, "S": 0}
    n_rule_counts: dict[str, int] = {}
    for a, b in human_pairs:
        label, rule = predict_label(listings[a], listings[b])
        label_counts[label] += 1
        if label == "N":
            n_rule_counts[rule] = n_rule_counts.get(rule, 0) + 1
    return label_counts, n_rule_counts


def main() -> int:
    if not check_database():
        print("database UNREACHABLE", file=sys.stderr)
        return 2

    rng = random.Random(RNG_SEED)
    seen_pairs: set[tuple[str, str]] = set()
    pools: dict[str, list[tuple[str, str]]] = {}

    with session_scope() as session:
        # --- proxy_key_collision -------------------------------------------------------------
        raw_rows = session.execute(_RAW_FOR_PROXY_KEY_SQL).all()
        by_key: dict[object, list[tuple[str, str]]] = {}  # key -> [(content_hash, source), ...]
        for content_hash, source, title, raw_payload in raw_rows:
            brand = (raw_payload or {}).get("brand") if isinstance(raw_payload, dict) else None
            key = overlap_key(title, brand if isinstance(brand, str) else None)
            if key is None:
                continue
            by_key.setdefault(key, []).append((content_hash, source))
        proxy_pairs: list[tuple[str, str]] = []
        for entries in by_key.values():
            sources = {s for _, s in entries}
            if len(sources) < 2:
                continue
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    h1, s1 = entries[i]
                    h2, s2 = entries[j]
                    if s1 != s2 and h1 != h2:
                        proxy_pairs.append((h1, h2))
        pools["proxy_key_collision"] = _dedup_pairs(proxy_pairs, seen_pairs)

        # --- blocked_retrieval_candidate --------------------------------------------------------
        # Block 3 item 10 (2026-09-15 session): this draw was flagged, by this same session, as
        # the one unseeded piece of an otherwise fully-seeded queue build (`SHUFFLE_SEED`/
        # `RNG_SEED` control everything downstream in Python, but this `ORDER BY random()` runs
        # inside Postgres, outside Python's `random.Random` entirely). `setseed()` takes a float
        # in [-1, 1] — RNG_SEED folded into that range deterministically, not a fresh literal, so
        # changing RNG_SEED still changes this draw too. A queue that cannot be re-derived byte-
        # for-byte from its seed is not reproducible, and reproducibility is part of what this
        # project demonstrates.
        session.execute(text("select setseed(:s)"), {"s": (RNG_SEED % 2_000_000) / 1_000_000 - 1})
        anchors = session.execute(_BLOCKED_RETRIEVAL_ANCHOR_SQL, {"n": 600}).all()
        retrieval_pairs: list[tuple[str, str]] = []
        for anchor_hash, brand_key in anchors:
            cands = session.execute(
                _BLOCKED_RETRIEVAL_CANDIDATES_SQL,
                {"self_hash": anchor_hash, "brand_key": brand_key, "k": TOP_K},
            ).all()
            for (cand,) in cands:
                retrieval_pairs.append((anchor_hash, cand))
        # Raw blocked-retrieval candidates are dominated by same-brand DIFFERENT-weight siblings —
        # the exact crowding TASK 2 diagnosed, still present within a block, not just across
        # blocks. Filtering to matching quantity tuples here (checked, not assumed: unfiltered
        # this category alone pushed the guard's capacity_differs figure to ~49%) keeps this
        # category's job to what its name says — a plausible-POSITIVE source — and leaves
        # capacity-differing hard negatives to the dedicated capacity_differs categories, which
        # exist to hold that class deliberately, not have it leak in from every direction.
        pools["blocked_retrieval_candidate_raw"] = _dedup_pairs(retrieval_pairs, seen_pairs)

        # --- capacity_differs (split cross/within shop after fetching Listings) ---------------
        capacity_rows = session.execute(_CAPACITY_DIFFERS_SQL).all()
        capacity_pairs_all = _dedup_pairs([tuple(r) for r in capacity_rows], seen_pairs)

        # --- required sub-classes ---------------------------------------------------------------
        flavour_rows = session.execute(_SAME_CAPACITY_DIFF_FLAVOUR_SQL).all()
        pools["same_capacity_diff_flavour"] = _dedup_pairs(
            [tuple(r) for r in flavour_rows], seen_pairs
        )

        lifestage_rows = session.execute(_SAME_CAPACITY_DIFF_LIFESTAGE_SQL).all()
        pools["same_capacity_diff_lifestage"] = _dedup_pairs(
            [tuple(r) for r in lifestage_rows], seen_pairs
        )

        breedsize_rows = session.execute(_SAME_CAPACITY_DIFF_BREEDSIZE_SQL).all()
        pools["same_capacity_diff_breedsize"] = _dedup_pairs(
            [tuple(r) for r in breedsize_rows], seen_pairs
        )

        diffbrand_rows = session.execute(_DIFF_BRAND_SIMILAR_TITLE_SQL).all()
        pools["diff_brand_similar_title"] = _dedup_pairs(
            [tuple(r) for r in diffbrand_rows], seen_pairs
        )

        reform_rows = session.execute(
            _REFORMULATION_APPROX_SQL, {"markers": list(_REFORMULATION_MARKERS)}
        ).all()
        pools["reformulation_approx"] = _dedup_pairs([tuple(r) for r in reform_rows], seen_pairs)

        # Fetch all Listings needed across every pool, including capacity_pairs_all (not yet
        # source-split).
        needed_hashes: set[str] = set()
        for pool in [*pools.values(), capacity_pairs_all]:
            for a, b in pool:
                needed_hashes.add(a)
                needed_hashes.add(b)
        listings = _fetch_listings(session, needed_hashes)

    # Finding 8 (2026-09-15 reference labelling pass, pilot 86: "Covor absorbant pentru caini
    # figaro" — an accessory that reached the queue). Root cause checked, not assumed: `category`
    # was correctly "accessory" for that row all along — none of the 9 source queries above ever
    # filtered on it, so any pair a query's other join conditions (brand_blocking_key,
    # product_line, quantity tuple) happened to match could carry an out-of-scope category
    # straight into the queue. `predict_label`'s rule 0 caught it downstream (scored `S`), which
    # is why it only ever showed up as a forecast label and not as a visible bug — but scoring it
    # `S` after the fact is not the same as never sourcing it. Filtered here, once, for every
    # pool, rather than duplicating a `category` predicate into all 9 queries above.
    def in_scope_only(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return [
            (a, b)
            for a, b in pairs
            if listings[a].category in _IN_SCOPE_CATEGORIES
            and listings[b].category in _IN_SCOPE_CATEGORIES
        ]

    capacity_pairs_all = in_scope_only(capacity_pairs_all)
    for _name in list(pools):
        pools[_name] = in_scope_only(pools[_name])

    def cross_shop_only(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return [(a, b) for a, b in pairs if listings[a].source != listings[b].source]

    def within_shop_only(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return [(a, b) for a, b in pairs if listings[a].source == listings[b].source]

    def same_capacity(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        def eq(a: str, b: str) -> bool:
            la, lb = listings[a], listings[b]
            return (
                la.net_weight_g == lb.net_weight_g
                and la.net_volume_ml == lb.net_volume_ml
                and la.pack_count == lb.pack_count
                and la.bonus_weight_g == lb.bonus_weight_g
            )

        return [(a, b) for a, b in pairs if eq(a, b)]

    pools["capacity_differs_cross_shop"] = cross_shop_only(capacity_pairs_all)
    pools["capacity_differs_within_shop"] = within_shop_only(capacity_pairs_all)
    pools["blocked_retrieval_candidate"] = same_capacity(
        pools.pop("blocked_retrieval_candidate_raw")
    )

    # All other pools: keep them cross-shop for the positive/hard-negative sub-classes (the
    # matching problem this project targets), except capacity_differs_within_shop above, which
    # exists specifically to cover the within-shop gap the 2026-09-13 diagnostic found.
    for name in (
        "proxy_key_collision",
        "blocked_retrieval_candidate",
        "same_capacity_diff_flavour",
        "same_capacity_diff_lifestage",
        "same_capacity_diff_breedsize",
        "diff_brand_similar_title",
        "reformulation_approx",
    ):
        pools[name] = cross_shop_only(pools[name])

    for pool in pools.values():
        rng.shuffle(pool)

    print("=" * 78)
    print("CATEGORY POOLS (available, after dedup + cross/within-shop split)")
    print("=" * 78)
    for name, pool in pools.items():
        print(f"  {name:32s} {len(pool)}")

    # --- Trivial pass (unrelated to category sourcing above): scan the SAME candidate hashes
    # for byte-identical-attribute pairs, auto-label M, spot-check a subset. Reuses whatever was
    # already fetched; does not consume category quota.
    all_candidate_pairs = [p for pool in pools.values() for p in pool] + capacity_pairs_all
    trivial_pairs = [
        (a, b)
        for a, b in all_candidate_pairs
        if classify_tier(listings[a], listings[b]) == "trivial"
    ]
    rng.shuffle(trivial_pairs)
    auto_labelled = trivial_pairs
    spot_check_hashes = auto_labelled[:SPOT_CHECK_TRIVIAL_COUNT]

    # --- Fill quotas -------------------------------------------------------------------------
    non_trivial_target = QUEUE_SIZE_TARGET - len(spot_check_hashes)
    quota_counts = {name: int(non_trivial_target * share) for name, share in QUOTA_SHARES.items()}

    selected: dict[str, list[tuple[str, str]]] = {}
    shortfalls: dict[str, int] = {}
    for name, quota in quota_counts.items():
        pool = pools.get(name, [])
        take = pool[:quota]
        selected[name] = take
        if len(take) < quota:
            shortfalls[name] = quota - len(take)

    # Redistribute any shortfall into whichever category still has surplus available, preferring
    # the positive sources first (keeps the >=25% positive floor from eroding), then the required
    # negative sub-classes, least of all capacity_differs (it is a cap, not a target — topping it
    # up further would undo the whole point of TASK 4).
    fill_priority = [
        "proxy_key_collision",
        "blocked_retrieval_candidate",
        "same_capacity_diff_flavour",
        "same_capacity_diff_lifestage",
        "same_capacity_diff_breedsize",
        "diff_brand_similar_title",
        "reformulation_approx",
        "capacity_differs_cross_shop",
        "capacity_differs_within_shop",
    ]
    total_shortfall = sum(shortfalls.values())
    if total_shortfall:
        for name in fill_priority:
            if total_shortfall <= 0:
                break
            pool = pools.get(name, [])
            already = len(selected[name])
            surplus = pool[already:]
            if not surplus:
                continue
            extra = surplus[:total_shortfall]
            selected[name] = selected[name] + extra
            total_shortfall -= len(extra)

    human_pairs: list[tuple[str, str]] = []
    category_labels: list[str] = []
    for name, pairs in selected.items():
        human_pairs.extend(pairs)
        category_labels.extend([name] * len(pairs))
    for h in spot_check_hashes:
        human_pairs.append(h)
        category_labels.append("trivial_spot_check")

    combined = list(zip(human_pairs, category_labels, strict=True))
    rng.shuffle(combined)
    human_pairs = [p for p, _ in combined]
    category_labels = [c for _, c in combined]

    print("\n" + "=" * 78)
    print(f"QUEUE COMPOSITION (target {QUEUE_SIZE_TARGET}, achieved {len(human_pairs)})")
    print("=" * 78)
    counts_by_category: dict[str, int] = {}
    for c in category_labels:
        counts_by_category[c] = counts_by_category.get(c, 0) + 1
    for name in [*quota_counts, "trivial_spot_check"]:
        n = counts_by_category.get(name, 0)
        pct = n / len(human_pairs) * 100 if human_pairs else 0.0
        quota = quota_counts.get(name, len(spot_check_hashes))
        short_note = f"  SHORT of quota {quota}" if name in shortfalls else ""
        print(f"  {name:32s} {n:5d} ({pct:5.1f}%){short_note}")

    positive_total = counts_by_category.get("proxy_key_collision", 0) + counts_by_category.get(
        "blocked_retrieval_candidate", 0
    )
    capacity_total = counts_by_category.get(
        "capacity_differs_cross_shop", 0
    ) + counts_by_category.get("capacity_differs_within_shop", 0)
    print(
        f"\nsource-tier totals — NOT a label prediction, see the forecast below "
        f"(proxy_key_collision + blocked_retrieval_candidate): "
        f"{positive_total} ({positive_total / len(human_pairs) * 100:.1f}% of queue)"
    )
    print(
        f"capacity_differs total (cross + within shop): {capacity_total} "
        f"({capacity_total / len(human_pairs) * 100:.1f}% of queue)"
    )

    # --- TASK B headline: the three-way predicted-label forecast, not a source-tier count -----
    label_counts, n_rule_counts = forecast_queue(human_pairs, listings)
    n_total_forecast = len(human_pairs)
    print("\n" + "=" * 78)
    print("PREDICTED LABEL DISTRIBUTION (rules-engine forecast, conventions.md revision 2)")
    print("=" * 78)
    print(
        "Applies the deterministic ladder to every pair. NOT used to auto-label anything beyond "
        "the existing trivial-tier pass — this is a forecast of the annotator's workload, not a "
        "substitute for the annotator."
    )
    for label in ("M", "N", "S"):
        n = label_counts[label]
        pct = n / n_total_forecast * 100 if n_total_forecast else 0.0
        tag = "  <- M-plausible" if label == "M" else ""
        print(
            f"  {label}-{'plausible' if label == 'M' else ('by-rule' if label == 'N' else 'likely'):10s} {n:5d} ({pct:5.1f}%){tag}"
        )
    print("\n  N, by which rule fired:")
    for rule, n in sorted(n_rule_counts.items(), key=lambda x: -x[1]):
        print(f"    {rule:28s} {n:5d} ({n / n_total_forecast * 100:5.1f}% of queue)")

    m_fraction = label_counts["M"] / n_total_forecast if n_total_forecast else 0.0
    if m_fraction < 0.25:
        print(
            f"\nWARNING: M-plausible ({m_fraction * 100:.1f}%) is below the 25% floor. "
            "See REBALANCE below."
        )

    # --- Guard: single-feature dominance ------------------------------------------------------
    def differs_capacity(left: Listing, right: Listing) -> bool:
        return (
            left.net_weight_g != right.net_weight_g
            or left.net_volume_ml != right.net_volume_ml
            or left.pack_count != right.pack_count
            or left.bonus_weight_g != right.bonus_weight_g
        )

    def differs_flavour(left: Listing, right: Listing) -> bool:
        if left.flavour is None or right.flavour is None:
            return False
        return left.flavour != right.flavour

    def differs_brand(left: Listing, right: Listing) -> bool:
        return left.brand != right.brand

    n_total = len(human_pairs)
    n_cap_differs = sum(1 for a, b in human_pairs if differs_capacity(listings[a], listings[b]))
    n_flavour_differs = sum(1 for a, b in human_pairs if differs_flavour(listings[a], listings[b]))
    n_brand_differs = sum(1 for a, b in human_pairs if differs_brand(listings[a], listings[b]))

    feature_fractions = {
        "capacity_differs": n_cap_differs / n_total if n_total else 0.0,
        "flavour_differs (both stated)": n_flavour_differs / n_total if n_total else 0.0,
        "brand_differs": n_brand_differs / n_total if n_total else 0.0,
    }

    print("\n" + "=" * 78)
    print("GUARD: single-deterministic-feature dominance (limit 40%)")
    print("=" * 78)
    dominant = None
    for feature, fraction in feature_fractions.items():
        flag = "  <-- EXCEEDS LIMIT" if fraction > SINGLE_FEATURE_DOMINANCE_LIMIT else ""
        print(f"  {feature:32s} {fraction * 100:5.1f}%{flag}")
        if fraction > SINGLE_FEATURE_DOMINANCE_LIMIT:
            dominant = (feature, fraction)

    if dominant is not None:
        feature, fraction = dominant
        print(
            f"\nREFUSED: {feature} alone decides {fraction * 100:.1f}% of the queue "
            f"(limit {SINGLE_FEATURE_DOMINANCE_LIMIT * 100:.0f}%). Nothing written. "
            "Adjust QUOTA_SHARES (or the category queries feeding it) and re-run."
        )
        return 1

    # --- Write ---------------------------------------------------------------------------------
    def listing_dict(listing: Listing) -> dict[str, object]:
        return {
            "content_hash": listing.content_hash,
            "source": listing.source,
            "title": listing.title,
            "brand": listing.brand,
            "product_line": listing.product_line,
            "net_weight_g": listing.net_weight_g,
            "net_volume_ml": listing.net_volume_ml,
            "pack_count": listing.pack_count,
            "bonus_weight_g": listing.bonus_weight_g,
            "breed_size_code": listing.breed_size_code,
            "life_stage": listing.life_stage,
            "flavour": listing.flavour,
            "food_form": listing.food_form,
            "species": listing.species,
            "breed_size_class": listing.breed_size_class,
        }

    pairs_out = []
    for (a, b), category in zip(human_pairs, category_labels, strict=True):
        left, right = listings[a], listings[b]
        pair_id = f"{left.content_hash[:12]}_{right.content_hash[:12]}"
        pairs_out.append(
            {
                "pair_id": pair_id,
                "occurrence_id": f"{pair_id}_0",
                "tier": category,
                "left": listing_dict(left),
                "right": listing_dict(right),
            }
        )

    queue_json = {
        "shuffle_seed": SHUFFLE_SEED,
        "built_from": "scripts/build_annotation_queue.py (ADR-0028 TASK 4 rebuild)",
        "auto_labelled_count": len(auto_labelled),
        "category_quotas": quota_counts,
        # Block 3 item 10 (2026-09-15 session): the forecast now lives in the artifact itself,
        # not only in this script's transient console output, so the queue's own headline
        # statistic is re-derivable from the committed file.
        "predicted_label_forecast": {
            "labels": label_counts,
            "n_by_rule": n_rule_counts,
        },
        "pairs": pairs_out,
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(queue_json, ensure_ascii=False, indent=1), encoding="utf-8")

    est_hours = len(human_pairs) / 200
    print(f"\nestimated wall-clock for the human queue at 200 pairs/hour: {est_hours:.1f} hours")
    print(
        f"trivial pairs auto-labelled M (not in human queue beyond the spot-check): "
        f"{len(auto_labelled) - len(spot_check_hashes)}"
    )
    print(f"\nwritten: {OUTPUT_JSON.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
