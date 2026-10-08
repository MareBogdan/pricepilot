"""Public-facing shop aliases.

The deployed dashboard and its JSON API never show a retailer's real name or a link to its pages.
Real names stay in the database, the scrapers, the docs and the README; this module is the one
place that maps them to the aliases the public surface uses (`docs/LEGAL.md`).
"""

from __future__ import annotations

import hashlib

# Fixed, not derived from sort order: a shop keeps its letter (and its chart colour) forever.
_ALIASES = {"animax_ro": "shop_a", "pentruanimale_ro": "shop_b", "petmax_ro": "shop_c"}


def public_shop(source: str) -> str:
    """`petmax_ro` -> `shop_c`. A source with no fixed alias gets a short stable hash instead,
    so a newly added shop is anonymous by default rather than leaking its name."""
    alias = _ALIASES.get(source)
    if alias is not None:
        return alias
    return "shop_" + hashlib.sha256(source.encode()).hexdigest()[:4]


def shop_label(alias: str) -> str:
    """`shop_c` -> `Shop C`."""
    return "Shop " + alias.removeprefix("shop_").upper()
