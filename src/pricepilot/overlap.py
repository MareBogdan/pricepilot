"""Cross-shop overlap — the Phase 1 gate metric (CLAUDE.md §7, DECISIONS.md ADR-0009).

Phase 3 is a matching problem. If the same product does not appear on two shops there is no
positive class, and Phases 3 to 6 are unfounded. This module answers one question, cheaply, from
SQL, so the answer is visible in `make status` from day one instead of discovered in week 6:

    how many products appear on two or more shops?

**It is a proxy, and deliberately a crude one.** The key is
`(brand, product-line tokens, net weight in grams)`, normalised. It will miss real matches the
Phase 3 model would find, and it will occasionally join two products that are not the same. Both
directions of error are accepted: this is a *floor estimate* used to make one decision — add a
source before leaving Phase 1, or don't. A floor is exactly the right instrument for that.

**What this is not.** It is not a matching model, it is not training data, and its output is never
reported as a matching result. Building a model to measure the overlap that justifies the model is
circular; that is the mistake this module exists to avoid.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select

from pricepilot.db import session_scope
from pricepilot.models import RawListing

# CLAUDE.md §7 Phase 1 gate.
OVERLAP_TARGET = 400

# Romanian shop prose that carries no product identity. Stripped before tokenising the line name
# so "Hrana uscata pentru caini Orijen Original Dog Adult Mini" and "Orijen Adult Original"
# have a chance of colliding.
_STOPWORDS = frozenset(
    [
        "hrana",
        "hrană",
        "uscata",
        "uscată",
        "umeda",
        "umedă",
        "pentru",
        "caini",
        "câini",
        "cainii",
        "pisici",
        "pisica",
        "pisică",
        "catel",
        "catei",
        "pui",
        "adult",
        "adulti",
        "adulți",
        "junior",
        "senior",
        "recompense",
        "delicioase",
        "conserva",
        "conserve",
        "plic",
        "plicuri",
        "punga",
        "pungă",
        "sac",
        "saci",
        "cu",
        "si",
        "și",
        "de",
        "la",
        "fara",
        "fără",
        "in",
        "în",
        "pe",
        "gratuit",
        "gratis",
        "bonus",
    ]
)

# Pack forms that some shops append and others do not.
_NOISE = frozenset({"kg", "g", "gr", "grame", "mg", "ml", "l", "buc", "x"})

# "8 kg + 1 kg gratuit" and "15 + 3 Kg Gratis" — the unit may sit only on the bonus.
_BONUS = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|g|gr)?\s*\+\s*\d+(?:[.,]\d+)?\s*(kg|g|gr)\b",
)
# "24x85 g", "5 x 900 g" — pack count times unit weight. Both x and the multiplication sign occur.
_PACK = re.compile(r"(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*(kg|g|gr)\b")  # noqa: RUF001
_PLAIN: tuple[tuple[re.Pattern[str], Decimal], ...] = (
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*kg\b"), Decimal("1000")),
    (re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:g|gr|grame)\b"), Decimal("1")),
)

# Characters `unicodedata` will not decompose, because they are letters in their own right
# rather than a base letter plus a combining mark. CLAUDE.md §7 names Smølke explicitly.
_LETTER_FOLD = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "đ": "d"})


def strip_diacritics(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.translate(_LETTER_FOLD))
    return "".join(c for c in folded if not unicodedata.combining(c))


def net_weight_grams(title: str) -> int | None:
    """Net weight in grams, or `None` when the title does not state one.

    Handles the four forms CLAUDE.md §7 names: "4.5 kg", "4,5 kg", "4500 g", and a leading
    "12 kg". Pack forms ("5 x 900 g") multiply out.

    **Bonus weights are not added.** "8 kg + 1 kg gratuit" resolves to 8000 g, not 9000 g: the
    base pack is what identifies the product line, and the bonus is a promotion on top of it.
    This is a judgement call, and it is the one that keeps petmax product 233 ("Mini Adult 8 kg")
    and 2542 ("Mini Adult 8 kg + 1 kg gratuit") in the same overlap bucket while their prices
    differ — which is correct for a floor estimate of overlap.
    """
    text = strip_diacritics(title.lower())

    if (bonus := _BONUS.search(text)) is not None:
        unit = bonus.group(2) or bonus.group(3)
        multiplier = Decimal("1000") if unit == "kg" else Decimal("1")
        return int(Decimal(bonus.group(1).replace(",", ".")) * multiplier)

    if (pack := _PACK.search(text)) is not None:
        count = Decimal(pack.group(1))
        unit_weight = Decimal(pack.group(2).replace(",", "."))
        multiplier = Decimal("1000") if pack.group(3) == "kg" else Decimal("1")
        return int(count * unit_weight * multiplier)

    for pattern, multiplier in _PLAIN:
        if (match := pattern.search(text)) is not None:
            return int(Decimal(match.group(1).replace(",", ".")) * multiplier)
    return None


def line_tokens(title: str, brand: str | None) -> tuple[str, ...]:
    """The product-line tokens: title minus brand, shop prose, weights and units, sorted.

    Sorted because CLAUDE.md §7 documents the same line written in reversed word order
    ("Orijen Original Dog Adult Mini" vs "Orijen Adult Original"). Order carries no identity
    across these shops, so discarding it is what makes the proxy work at all.
    """
    text = strip_diacritics(title.lower())
    if brand:
        for word in strip_diacritics(brand.lower()).split():
            text = text.replace(word, " ")
    raw = re.findall(r"[a-z0-9']+", text)
    keep = [
        token
        for token in raw
        if token not in _STOPWORDS and token not in _NOISE and not token.isdigit()
    ]
    return tuple(sorted(set(keep)))


def normalized_brand(brand: str | None, title: str) -> str:
    """Brand, lowercased and de-diacriticked.

    When the shop exposes no brand field, fall back to the title's first **meaningful** token —
    the first that is not shop prose. `magazindeanimale.ro` writes "Hrană uscată câini ORIJEN
    Original…", so taking the literal first token would key the brand as "hrana" and split the
    product away from the three shops that do expose a brand.
    """
    if brand and brand.strip():
        return " ".join(strip_diacritics(brand.lower()).split())
    tokens: list[str] = re.findall(r"[a-z0-9']+", strip_diacritics(title.lower()))
    for token in tokens:
        if token not in _STOPWORDS and token not in _NOISE and not token.isdigit():
            return token
    return ""


@dataclass(frozen=True)
class OverlapKey:
    brand: str
    line: tuple[str, ...]
    weight_g: int

    def __str__(self) -> str:
        return f"{self.brand} | {' '.join(self.line)} | {self.weight_g}g"


def overlap_key(title: str, brand: str | None) -> OverlapKey | None:
    """The proxy key, or `None` when the listing cannot produce one.

    A listing with no weight in the title cannot be keyed — `zoopoint.ro` does exactly this,
    which is why the count is a floor and not an estimate of the truth.
    """
    weight = net_weight_grams(title)
    if weight is None or weight <= 0:
        return None
    # Resolve the brand first, then strip *that* from the line tokens — otherwise a shop with no
    # brand field keeps the brand word inside its line and never collides with one that has it.
    key_brand = normalized_brand(brand, title)
    tokens = line_tokens(title, key_brand)
    if not key_brand or not tokens:
        return None
    return OverlapKey(brand=key_brand, line=tokens, weight_g=weight)


@dataclass
class OverlapReport:
    """`shared` is the gate number. The rest is there to make a low count diagnosable rather
    than merely disappointing."""

    sources: int
    listings_considered: int
    keys_built: int
    unkeyable: int
    shared: int
    target: int = OVERLAP_TARGET

    @property
    def met(self) -> bool:
        return self.shared >= self.target

    @property
    def keyable_share(self) -> float:
        return self.keys_built / self.listings_considered if self.listings_considered else 0.0


def compute_overlap(target: int = OVERLAP_TARGET) -> OverlapReport:
    """Count proxy keys that appear on two or more sources.

    Reads the **latest observation per (source, product)** rather than every historical row —
    `raw_listings` is append-only (ADR-0005), so counting rows would multiply the answer by the
    number of days collected.
    """
    with session_scope() as session:
        latest = (
            select(
                RawListing.source,
                RawListing.source_product_id,
                func.max(RawListing.scraped_at).label("scraped_at"),
            )
            .group_by(RawListing.source, RawListing.source_product_id)
            .subquery()
        )
        rows = session.execute(
            select(RawListing.source, RawListing.title, RawListing.raw_payload).join(
                latest,
                (RawListing.source == latest.c.source)
                & (RawListing.source_product_id == latest.c.source_product_id)
                & (RawListing.scraped_at == latest.c.scraped_at),
            )
        ).all()

    by_key: dict[OverlapKey, set[str]] = {}
    sources: set[str] = set()
    unkeyable = 0
    for source, title, payload in rows:
        sources.add(source)
        brand = (payload or {}).get("brand") if isinstance(payload, dict) else None
        key = overlap_key(title, brand if isinstance(brand, str) else None)
        if key is None:
            unkeyable += 1
            continue
        by_key.setdefault(key, set()).add(source)

    return OverlapReport(
        sources=len(sources),
        listings_considered=len(rows),
        keys_built=len(rows) - unkeyable,
        unkeyable=unkeyable,
        shared=sum(1 for shops in by_key.values() if len(shops) >= 2),
        target=target,
    )
