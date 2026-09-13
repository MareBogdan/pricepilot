"""Phase 2 deterministic attribute extraction (CLAUDE.md §7, ADR-0026).

Regex and lookup tables only — no LLM, no network, no API key read (CLAUDE.md §7: "Regex and
lookup tables first... running an LLM over them is wasted money"; ADR-0006: the LLM transport
stays unimplemented). Every function here is pure: title text in, a typed result out, nothing
read from the database and nothing written to it. `scripts/normalize.py` is the only thing that
touches `raw_listings`/`norm_listings` — this package never does.

Build order (STEP 3, weight first because CLAUDE.md §7 says it's the highest-leverage field):
`quantity` (weight/volume/pack/bonus/dosage) -> `brand` -> `flavour` -> `attributes` (breed-size,
life stage, food form). `extract()` below composes all four into one `ExtractedAttributes`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

from pricepilot.normalize.attributes import (
    extract_breed_size,
    extract_food_form,
    extract_life_stage,
)
from pricepilot.normalize.brand import canonicalize_brand
from pricepilot.normalize.flavour import extract_flavour
from pricepilot.normalize.quantity import QuantityResult, extract_quantity

__all__ = [
    "ExtractedAttributes",
    "extract",
]

T = TypeVar("T")


@dataclass(frozen=True)
class ExtractedAttributes:
    """Mirrors `norm_listings`'s attribute columns exactly (ADR-0026) — one field per column,
    same nullability. `errors` is the source for `extraction_errors`: populated ONLY for a field
    an extractor function raised on, never for a field that is simply absent from the title."""

    brand: str | None = None
    product_line: str | None = None
    net_weight_g: int | None = None
    net_volume_ml: int | None = None
    pack_count: int | None = None
    bonus_weight_g: int | None = None
    breed_size_code: str | None = None
    life_stage: str | None = None
    flavour: str | None = None
    food_form: str | None = None
    dosage_band: str | None = None
    errors: dict[str, str] = field(default_factory=dict)


def extract(title: str, source_brand: str | None = None) -> ExtractedAttributes:
    """Run every deterministic extractor over one title. `source_brand` is the shop's own
    brand field when it exposes one (petmax, animax); pentruanimale/animax's structured brand,
    when present, is more reliable than parsing it back out of the title, so brand extraction
    prefers it and falls back to the title only when it's absent.

    Never raises: each sub-extractor's failure is caught and recorded in `.errors` under that
    field's name, so one broken field cannot lose the rest of the row (the same "one broken card
    doesn't lose the page" principle the scrapers already follow, ADR-0002)."""
    errors: dict[str, str] = {}

    quantity = _safe(errors, "quantity", extract_quantity, title) or QuantityResult()
    brand = _safe(errors, "brand", canonicalize_brand, title, source_brand)
    flavour = _safe(errors, "flavour", extract_flavour, title)
    breed_size = _safe(errors, "breed_size_code", extract_breed_size, title)
    life_stage = _safe(errors, "life_stage", extract_life_stage, title)
    food_form = _safe(errors, "food_form", extract_food_form, title)

    return ExtractedAttributes(
        brand=brand,
        product_line=None,  # not built this session — see STATE.md Open issues
        net_weight_g=quantity.net_weight_g,
        net_volume_ml=quantity.net_volume_ml,
        pack_count=quantity.pack_count,
        bonus_weight_g=quantity.bonus_weight_g,
        breed_size_code=breed_size,
        life_stage=life_stage,
        flavour=flavour,
        food_form=food_form,
        dosage_band=quantity.dosage_band,
        errors=errors,
    )


def _safe(errors: dict[str, str], field_name: str, fn: Callable[..., T], *args: object) -> T | None:
    try:
        return fn(*args)
    except Exception as exc:
        errors[field_name] = f"{type(exc).__name__}: {exc}"
        return None
