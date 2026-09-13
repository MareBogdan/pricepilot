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

# STEP 4 (session note 2026-09-12): a shop that omits the space before the unit ("85g", "400g",
# "0,85kg") produces one combined alnum token that survives `line_tokens()`'s `_NOISE` filter
# (only the *bare* unit "g"/"kg" is filtered, not "85g") while the spaced form ("85 g") tokenizes
# to a bare digit (dropped by `isdigit()`) and a bare unit (dropped by `_NOISE`) — so the same
# product gets a different key purely from a shop's spacing convention. Measured impact: this
# single asymmetry alone hid 79 of 92 genuine cross-shop matches in the first real measurement.
# The decimal separator (`,` or `.`) is not part of this pattern because it already splits the
# token in two at the regex level (`[a-z0-9']+` does not include `,`/`.`), leaving only the
# fractional digits glued to the unit, e.g. "0,85kg" tokenizes to "0" and "85kg".
_WEIGHT_UNIT_TOKEN = re.compile(r"^\d+(?:kg|g|gr|grame|mg|ml|l)$")

# One alternation shared by the bonus/pack/plain weight-or-volume patterns below. "ml"/"l" added
# per STEP 4 — a liquid product (shampoo, supplement) previously returned no weight at all and
# was silently unkeyable. Longer unit names first so the alternation cannot short-match "gr" out
# of "grame" or "g" out of "gr".
_UNIT = r"(?:grame|kg|ml|gr|g|l)"


def _unit_multiplier(unit: str) -> Decimal:
    """Grams-equivalent per unit. `l`/`kg` are the only "x1000" units; a millilitre is treated
    as one gram (water-density proxy) — a floor-estimate key does not need more precision than
    that, and CLAUDE.md §7 asks for one canonical grams value, not an exact-density conversion."""
    return Decimal("1000") if unit in ("kg", "l") else Decimal("1")


# "8 kg + 1 kg gratuit" and "15 + 3 Kg Gratis" — the unit may sit only on the bonus, and the base
# number may have none at all ("8+1kg"). Named groups: `bonus`/`bonus_unit` feed
# `bonus_weight_grams()`, which is a DIFFERENT purchasable unit from the plain pack and must
# never collide with it — see `OverlapKey.bonus_g` and DECISIONS.md ADR-0021.
_BONUS = re.compile(
    rf"(?P<base>\d+(?:[.,]\d+)?)\s*(?P<base_unit>{_UNIT})?\s*\+\s*"
    rf"(?P<bonus>\d+(?:[.,]\d+)?)\s*(?P<bonus_unit>{_UNIT})\b",
)
# "24x85 g", "5 x 900 g" — pack count times unit weight. Both x and the multiplication sign occur.
_PACK = re.compile(rf"(\d+)\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*({_UNIT})\b")  # noqa: RUF001
_PLAIN: tuple[re.Pattern[str], ...] = (re.compile(rf"(\d+(?:[.,]\d+)?)\s*({_UNIT})\b"),)

# Characters `unicodedata` will not decompose, because they are letters in their own right
# rather than a base letter plus a combining mark. CLAUDE.md §7 names Smølke explicitly.
# The two apostrophes fold to the same character for the same reason CLAUDE.md §7 names Hill's:
# a shop writing the curly U+2019 and one writing the plain ASCII "'" must tokenize identically,
# or "Hill's" and "Hill's" become two different brand tokens.
_LETTER_FOLD = str.maketrans(
    {
        "ø": "o",
        "Ø": "O",
        "æ": "ae",
        "Æ": "AE",
        "ß": "ss",
        "đ": "d",
        "’": "'",  # curly right single quote  # noqa: RUF001
        "‘": "'",  # curly left single quote  # noqa: RUF001
    }
)


def strip_diacritics(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.translate(_LETTER_FOLD))
    return "".join(c for c in folded if not unicodedata.combining(c))


def net_weight_grams(title: str) -> int | None:
    """Net weight (or volume, converted to a grams-equivalent) in grams, or `None` when the
    title states neither. Handles the forms CLAUDE.md §7 names: "4.5 kg", "4,5 kg", "4500 g", a
    leading "12 kg", plus "ml"/"l" (STEP 4, session note 2026-09-12). Pack forms ("5 x 900 g")
    multiply out.

    **This is the BASE pack weight only — bonus grams are never added here.** "8 kg + 1 kg
    gratuit" resolves to 8000 g, not 9000 g: the base pack is what identifies the product line,
    and the bonus is a promotion on top of it. The bonus amount is a *separate* signal — see
    `bonus_weight_grams()` — encoded into `OverlapKey.bonus_g` specifically so a bonus-weight
    listing and its plain-pack counterpart do NOT collide just because this function returns the
    same base weight for both (ADR-0021; this replaces the earlier, now-reversed judgement call
    that merging them was an acceptable floor-estimate approximation).
    """
    text = strip_diacritics(title.lower())

    if (bonus := _BONUS.search(text)) is not None:
        unit = bonus.group("base_unit") or bonus.group("bonus_unit")
        return int(Decimal(bonus.group("base").replace(",", ".")) * _unit_multiplier(unit))

    if (pack := _PACK.search(text)) is not None:
        count = Decimal(pack.group(1))
        unit_weight = Decimal(pack.group(2).replace(",", "."))
        return int(count * unit_weight * _unit_multiplier(pack.group(3)))

    for pattern in _PLAIN:
        if (match := pattern.search(text)) is not None:
            return int(Decimal(match.group(1).replace(",", ".")) * _unit_multiplier(match.group(2)))
    return None


def bonus_weight_grams(title: str) -> int:
    """The bonus amount in a "+N kg/g/ml/l" promotion (e.g. "8 kg + 1 kg gratuit", "15 + 3 Kg
    Gratis"), in grams, or 0 for a plain pack with no bonus.

    STEP 4 (session note 2026-09-12): a bonus-weight listing is a genuinely different
    purchasable unit from the plain pack — different price, often a different SKU — and must
    not collide with it in `overlap_key()`. Encoding this as its own key component (rather than
    adding it into `net_weight_grams()`, or ignoring it as the earlier design did) means: a plain
    "15 kg" and a bonus "15 + 3 Kg Gratis" never share a key (0 vs 3000), while two listings
    expressing the *same* bonus — in either shop's word order or spacing — still do, because the
    comparison is on the normalized gram amount, not the raw text. See ADR-0021.
    """
    text = strip_diacritics(title.lower())
    match = _BONUS.search(text)
    if match is None:
        return 0
    return int(
        Decimal(match.group("bonus").replace(",", "."))
        * _unit_multiplier(match.group("bonus_unit"))
    )


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
    keep = [token for token in raw if _is_line_token(token)]
    return tuple(sorted(set(keep)))


def _is_line_token(token: str) -> bool:
    """A token that carries product-line identity — not shop prose, not a bare unit, not a
    weight-glued-to-unit artifact (STEP 4: "85g" must be excluded the same way "85 g" already
    is, or the two spellings of the same product key differently). Shared by `line_tokens` and
    `normalized_brand`'s no-brand-field fallback, so both filter identically."""
    return (
        token not in _STOPWORDS
        and token not in _NOISE
        and not token.isdigit()
        and not _WEIGHT_UNIT_TOKEN.match(token)
    )


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
        if _is_line_token(token):
            return token
    return ""


@dataclass(frozen=True)
class OverlapKey:
    brand: str
    line: tuple[str, ...]
    weight_g: int
    # STEP 4 / ADR-0021 (session note 2026-09-12): 0 for a plain pack, >0 for a bonus-weight
    # promotion ("+N kg/g gratuit/gratis"). Part of the key's identity (dataclass equality and
    # hash both include it) specifically so a plain pack and its bonus-weight counterpart never
    # collide, while two listings expressing the same bonus amount still do.
    bonus_g: int = 0

    def __str__(self) -> str:
        bonus = f" +{self.bonus_g}g" if self.bonus_g else ""
        return f"{self.brand} | {' '.join(self.line)} | {self.weight_g}g{bonus}"


def overlap_key(title: str, brand: str | None) -> OverlapKey | None:
    """The proxy key, or `None` when the listing cannot produce one.

    A listing with no weight (or volume) in the title cannot be keyed — `zoopoint.ro` does
    exactly this, which is why the count is a floor and not an estimate of the truth.
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
    return OverlapKey(
        brand=key_brand, line=tokens, weight_g=weight, bonus_g=bonus_weight_grams(title)
    )


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

    Quarantined rows (`excluded_reason IS NOT NULL`, ADR-0025 — a regulated product caught after
    the fact, never deleted) are excluded from both the "latest observation" computation and the
    final count. A product's `excluded_reason` does not vary by day (it is derived from the
    title/`product_type`, which do not change day to day for the same product), so this is
    equivalent to dropping the product entirely, not just its most recent row.
    """
    with session_scope() as session:
        in_scope = select(RawListing).where(RawListing.excluded_reason.is_(None)).subquery()
        latest = (
            select(
                in_scope.c.source,
                in_scope.c.source_product_id,
                func.max(in_scope.c.scraped_at).label("scraped_at"),
            )
            .group_by(in_scope.c.source, in_scope.c.source_product_id)
            .subquery()
        )
        rows = session.execute(
            select(in_scope.c.source, in_scope.c.title, in_scope.c.raw_payload).join(
                latest,
                (in_scope.c.source == latest.c.source)
                & (in_scope.c.source_product_id == latest.c.source_product_id)
                & (in_scope.c.scraped_at == latest.c.scraped_at),
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
