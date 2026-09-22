"""The single canonical pair-text builder for every Phase 3 matching model (CLAUDE.md §7 items 5
and 6; ADR-0028 addendum #19).

Both the classical cross-encoder baseline and the LoRA fine-tune MUST call `build_pair_text()`
for their model inputs. If the baseline and the fine-tune constructed their input text
differently, any gap between their scores could come from prompt formatting rather than the
model itself, and the whole comparison would be measuring the wrong thing. This is the ONLY
place any model input text may be constructed anywhere in this codebase.

HARD RULE (also enforced by `tests/test_pair_text.py`): `build_pair_text()` reads ONLY a
listing's raw title and the ten normalised attributes named in `ATTRIBUTE_FIELDS` below. It must
never read (and this module never even accepts as a distinguished argument) a label, a tier, a
split, a pair_id, or a shop/source name — any of those would leak either the answer or the
sampling design into what a model "reads" as content. A caller may pass in a mapping that
happens to carry those keys too (e.g. a raw annotation-queue listing record, which also has
`content_hash` and `source`) — this module simply never reads them, by construction, since it
only ever looks up the fixed field list below.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Bumped whenever the text format changes, so a stale comparison (baseline scored under v1,
# fine-tune trained under v2) can never happen silently. Recorded in every artefact this harness
# writes — the train/validation split, the exported model inputs, and the scoring results.
PAIR_TEXT_VERSION = "pair-text-v1"

# Fixed order: the same order every time, so a diff between two runs' model inputs reflects a
# real data change, never a dict's iteration order. CLAUDE.md §7's ten normalised attributes that
# "carry the decision" — deliberately excludes `species` and `breed_size_class` (not named by the
# task that specified this list) and excludes anything label-, tier-, split- or source-shaped.
ATTRIBUTE_FIELDS: tuple[str, ...] = (
    "brand",
    "product_line",
    "net_weight_g",
    "net_volume_ml",
    "pack_count",
    "bonus_weight_g",
    "breed_size_code",
    "life_stage",
    "food_form",
    "flavour",
)

# Short, stable labels for the text -- not the same string as the JSON field name in every case,
# so the pair text reads like a compact record, not a dumped dict.
_FIELD_LABELS: dict[str, str] = {
    "brand": "brand",
    "product_line": "line",
    "net_weight_g": "weight_g",
    "net_volume_ml": "volume_ml",
    "pack_count": "pack",
    "bonus_weight_g": "bonus_g",
    "breed_size_code": "breed_size",
    "life_stage": "life_stage",
    "food_form": "food_form",
    "flavour": "flavour",
}

# An explicit marker for "this attribute was not extracted" -- distinct from any real value a
# field could hold, including the empty string or the number 0. A missing net_weight_g and a
# net_weight_g of 0 must never render as the same text.
MISSING_VALUE_MARKER = "<missing>"


def _format_value(value: object) -> str:
    if value is None:
        return MISSING_VALUE_MARKER
    return str(value)


def _listing_text(listing: Mapping[str, Any]) -> str:
    if "title" not in listing or listing["title"] is None:
        raise ValueError("build_pair_text(): listing is missing a non-null 'title'")
    parts = [f"title: {listing['title']}"]
    for field in ATTRIBUTE_FIELDS:
        parts.append(f"{_FIELD_LABELS[field]}: {_format_value(listing.get(field))}")
    return " | ".join(parts)


def build_pair_text(left: Mapping[str, Any], right: Mapping[str, Any]) -> tuple[str, str]:
    """Build the two strings a cross-encoder (or any pairwise text model) scores for one
    candidate pair.

    `left`/`right` are listing records shaped like
    `docs/learned/phase3-annotation-queue.json`'s own `pairs[i]["left"/"right"]` — any mapping
    carrying `title` and (optionally, missing ones become `MISSING_VALUE_MARKER`) the ten
    `ATTRIBUTE_FIELDS` is accepted. Extra keys such as `content_hash`, `source`, `species` or
    `breed_size_class` are present in that real record but are never read here.

    Returns `(text_a, text_b)` — `text_a` built from `left`, `text_b` from `right`, in that
    order. Swapping `left`/`right` swaps the two returned strings; callers that need an
    order-invariant score must symmetrise at the model layer, not here.
    """
    return _listing_text(left), _listing_text(right)
