"""Phase 5 session 3b: serve-time matcher pieces -- OUR products vs competitor listings (ADR-0039).

Pure selection logic (testable offline) plus `CrossEncoderScorer`, the fine-tuned cross-encoder
served from its safetensors weights on CPU via torch. ONNX is deliberately NOT used here: it is a
Phase-7 serving-latency concern, and the fp32 torch weights give the same scores (the Phase 3
benchmark's own `preds-ce-ptfp32-*.json` are the reference). The faithfulness guarantee is
`check_reproduction`: before scoring anything, the loaded model must reproduce those committed
predictions, so "0.89" means what it meant when the threshold was chosen.

Scoring is directional, exactly as in Phase 3: `build_pair_text(left, right)` -> tokenizer pair
(text_a, text_b), `max_length=256`, `sigmoid(logits[:, 0])`. No symmetrisation was ever applied, so
none is applied here. Our product is always `left`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any

from pricepilot.matching.pair_text import ATTRIBUTE_FIELDS
from pricepilot.normalize import extract
from pricepilot.normalize.brand import brand_blocking_key

# ADR-0030: threshold chosen on validation in Phase 3 for the fine-tuned cross-encoder.
MATCH_THRESHOLD = 0.89
MAX_LENGTH = 256  # same truncation as training / the Phase 3 serving benchmark
# sha256 of models/ce-ft-best/model.safetensors, as recorded by the Phase 3 serving benchmark
# (docs/learned/results/serving/model-facts.json, ce_weights.expected_sha256).
CE_WEIGHTS_SHA256 = "e8843e39f154419de57c18fda3647434b0feebabf019659631fac8d0ee4dc1fc"
# Blocks above this are not scored in full: top-`TOP_K_BY_COSINE` by embedding cosine instead.
LARGE_BLOCK_THRESHOLD = 300
TOP_K_BY_COSINE = 100
# A competitor price older than this (relative to that shop's newest scrape) is not "current".
PRICE_MAX_AGE_DAYS = 7
# Pre-registered BEFORE the first reproduction run: scores must agree with the committed
# PyTorch-fp32 predictions to within this, with zero decision flips at MATCH_THRESHOLD.
REPRO_MAX_ABS_DIFF = 1e-3


@dataclass(frozen=True)
class OurListing:
    """One of OUR products as a listing record, shaped like a `norm_listings` row."""

    record: dict[str, Any]  # `title` + the ten ATTRIBUTE_FIELDS, for `build_pair_text`
    blocking_key: str | None
    embedding_fields: dict[str, Any]  # what `build_embeddings.embedding_text` reads


def product_to_listing(
    title: str,
    brand: str,
    net_weight_g: int | None,
    extractor: Callable[..., Any] = extract,
) -> OurListing:
    """Run OUR product through the SAME extractor competitors went through (`extract`), keyed by
    the shop-style `source_brand`. Our `products.net_weight_g` is the system of record for weight,
    so it overrides the extracted weight when present; otherwise the extracted value stands (e.g. a
    volume-only item such as a 0.3 L bowl)."""
    a = extractor(title, source_brand=brand)
    record: dict[str, Any] = {"title": title}
    for field in ATTRIBUTE_FIELDS:
        record[field] = getattr(a, field)
    if net_weight_g is not None:
        record["net_weight_g"] = net_weight_g
    return OurListing(
        record=record,
        blocking_key=brand_blocking_key(a.brand),
        embedding_fields={
            "brand": a.brand,
            "product_line": a.product_line,
            "sample_title": title,
            "net_weight_g": record["net_weight_g"],
            "net_volume_ml": a.net_volume_ml,
            "pack_count": a.pack_count,
            "life_stage": a.life_stage,
            "flavour": a.flavour,
            "breed_size_code": a.breed_size_code,
        },
    )


def norm_row_to_record(row: Any) -> dict[str, Any]:
    """A `norm_listings` row as the listing record `build_pair_text` reads -- the same shape
    Phase 3's `build_annotation_queue.py::listing_dict` fed the model: `sample_title` as the title
    plus the ten attributes."""
    record: dict[str, Any] = {"title": row.sample_title}
    for field in ATTRIBUTE_FIELDS:
        record[field] = getattr(row, field)
    return record


@dataclass(frozen=True)
class ScoredLink:
    product_id: int
    source: str
    score: float
    external_id: str  # tie-break only; makes the choice deterministic
    payload: Any = None


def select_best_per_shop(links: Sequence[ScoredLink], threshold: float) -> list[ScoredLink]:
    """Keep links with `score >= threshold`, then at most ONE per (product, shop): the highest
    score wins; an exact tie goes to the lowest `external_id` so the result is deterministic."""
    best: dict[tuple[int, str], ScoredLink] = {}
    for link in links:
        if link.score < threshold:
            continue
        key = (link.product_id, link.source)
        cur = best.get(key)
        if cur is None or (-link.score, link.external_id) < (-cur.score, cur.external_id):
            best[key] = link
    return sorted(best.values(), key=lambda link: (link.product_id, link.source))


def _price_rank(row: Mapping[str, Any]) -> tuple[Any, ...]:
    # newer first, in-stock first, cheaper first, then stable id
    return (
        -row["collected_date"].toordinal(),
        0 if row.get("in_stock") else 1,
        row["price"],
        row["external_id"],
    )


def select_current_prices(
    rows: Sequence[Mapping[str, Any]],
    source_latest: Mapping[str, date],
    max_age_days: int = PRICE_MAX_AGE_DAYS,
) -> dict[str, Mapping[str, Any]]:
    """For ONE listing identity (`content_hash`): its current observation per shop.

    `rows` are `raw_listings` observations (`source`, `external_id`, `collected_date`, `price`,
    `in_stock`). Per shop: the latest `collected_date`; if several shop SKUs share that title on
    that day (same normalized title, e.g. variants), prefer in-stock, then the lowest price, then
    the lowest `external_id`. A shop whose latest observation is older than `max_age_days` before
    that shop's newest scrape is dropped -- a delisted item has no current price."""
    chosen: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        src = row["source"]
        if src not in source_latest:
            continue
        if row["collected_date"] < source_latest[src] - timedelta(days=max_age_days):
            continue
        if src not in chosen or _price_rank(row) < _price_rank(chosen[src]):
            chosen[src] = row
    return chosen


def score_to_decimal(score: float) -> Decimal:
    """Round DOWN to 6 places: a kept score (>= threshold) can never round up across it, and a
    persisted score therefore always satisfies the table's `score >= threshold` CHECK."""
    return Decimal(repr(score)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class CrossEncoderScorer:
    """The fine-tuned mMiniLMv2 cross-encoder, fp32 on CPU, from its HuggingFace-format dir.

    Tokenisation uses the model's own `tokenizer.json` through the `tokenizers` library -- the
    same path as the Phase 3 serving benchmark's worker -- NOT `transformers.AutoTokenizer`.
    Verified 2026-10-04: with transformers 5.17 `AutoTokenizer` returns `XLMRobertaTokenizer`,
    which joins the two segments with `</s></s>`, while `tokenizer.json` (and therefore the
    benchmark, whose PyTorch and ONNX scores agree to 1e-5) joins them with a single `</s>`.
    Tokenising the 287 TEST inputs the AutoTokenizer way changed every sequence and moved scores by
    up to 0.19 (1 flip at 0.89); reading `tokenizer.json` directly is version-independent."""

    def __init__(self, model_dir: Path) -> None:
        from pricepilot.embeddings import ensure_sklearn_importable

        ensure_sklearn_importable()  # transformers imports sklearn; blocked on this machine
        import torch
        from tokenizers import Tokenizer
        from transformers import AutoModelForSequenceClassification

        actual = sha256_file(model_dir / "model.safetensors")
        if actual != CE_WEIGHTS_SHA256:
            raise RuntimeError(
                f"{model_dir}/model.safetensors sha256 {actual} is not the benchmarked "
                f"cross-encoder ({CE_WEIGHTS_SHA256})"
            )
        self._torch = torch
        self.weights_sha256 = actual
        self._tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self._tok.no_padding()
        self._tok.enable_truncation(max_length=MAX_LENGTH)
        pad_id = self._tok.token_to_id("<pad>")
        if pad_id is None:
            raise RuntimeError("tokenizer.json has no <pad> token")
        self._pad_id: int = pad_id
        self._model = AutoModelForSequenceClassification.from_pretrained(model_dir).eval()

    def score(self, pairs: Sequence[tuple[str, str]], batch_size: int = 32) -> list[float]:
        """`sigmoid(logits[:, 0])` per (text_a, text_b), input order preserved. Batched in
        length-sorted order for speed; padding is masked, so scores match batch-size-1."""
        torch = self._torch
        ids = [self._tok.encode(a, b).ids for a, b in pairs]
        order = sorted(range(len(ids)), key=lambda i: len(ids[i]))
        out = [0.0] * len(ids)
        for start in range(0, len(order), batch_size):
            idx = order[start : start + batch_size]
            width = max(len(ids[i]) for i in idx)
            input_ids = torch.full((len(idx), width), self._pad_id, dtype=torch.long)
            mask = torch.zeros((len(idx), width), dtype=torch.long)
            for row, i in enumerate(idx):
                input_ids[row, : len(ids[i])] = torch.tensor(ids[i])
                mask[row, : len(ids[i])] = 1
            with torch.no_grad():
                logits = self._model(input_ids=input_ids, attention_mask=mask).logits
                probs = torch.sigmoid(logits[:, 0].float())
            for i, p in zip(idx, probs.tolist(), strict=True):
                out[i] = float(p)
        return out


def check_reproduction(
    scores: Mapping[str, float],
    committed: Mapping[str, float],
    threshold: float = MATCH_THRESHOLD,
    max_abs_diff: float = REPRO_MAX_ABS_DIFF,
) -> dict[str, Any]:
    """Score-against-score vs the committed PyTorch-fp32 predictions. Reproduced iff the pair
    sets are identical, max |diff| <= `max_abs_diff`, and no pair flips across `threshold`."""
    if set(scores) != set(committed):
        raise ValueError("scored pair ids differ from the committed prediction file's")
    diffs = [abs(scores[k] - committed[k]) for k in committed]
    flips = [k for k in committed if (scores[k] >= threshold) != (committed[k] >= threshold)]
    worst = max(diffs)
    return {
        "pairs": len(committed),
        "max_abs_diff": worst,
        "mean_abs_diff": sum(diffs) / len(diffs),
        "flips_at_threshold": len(flips),
        "tolerance": max_abs_diff,
        "reproduced": worst <= max_abs_diff and not flips,
    }
