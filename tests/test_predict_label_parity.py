"""Phase 3 (DECISIONS.md ADR-0028 addendum #13, review finding #8) -- locks the claim
`scripts/split_annotation_queue.py`'s own module docstring makes ("predict_label(), ported
verbatim from build_annotation_queue.py ... so the two can never disagree") with an actual test,
not just a comment and an ad-hoc session-only check. The two copies are duplicated by hand
(dict-keyed vs. dataclass-attribute-keyed, for `split_annotation_queue.py`'s DB-free operation on
the frozen queue's raw JSON) and now ~9 ladder rules deep; nothing else in the repo would catch a
future rule landing in only one of them.

Runs both implementations over every one of the frozen queue's real 997 pairs and asserts an
identical `(label, rule)` for all of them -- read-only against the committed files, no database
needed (`build_annotation_queue.py` only imports `pricepilot.db` names at module load, which is
lazy -- see `pricepilot.db.get_engine()` -- so importing it here never opens a connection).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QUEUE_JSON = ROOT / "docs" / "learned" / "phase3-annotation-queue.json"

FROZEN_QUEUE_SHA256 = "696e983392628b868c4becd92db400735a52498a4994b5b7c8651b160a087011"


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


baq = _load_module(
    "build_annotation_queue_under_test", ROOT / "scripts" / "build_annotation_queue.py"
)
saq = _load_module(
    "split_annotation_queue_under_test", ROOT / "scripts" / "split_annotation_queue.py"
)

_LISTING_FIELDS = [
    "content_hash",
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
    "source",
    "title",
    "species",
    "breed_size_class",
]


def _to_listing(d: dict[str, Any]) -> Any:
    # `category`/`brand_blocking_key` aren't persisted per-listing in the frozen queue (checked
    # directly, not assumed -- same gap split_annotation_queue.py's own module docstring notes);
    # every queue row is already known in-scope by construction (build_annotation_queue.py's
    # main() filters to food/litter before writing the frozen file), so "food" here can never
    # change which rule fires for real queue data.
    kwargs = {f: d.get(f) for f in _LISTING_FIELDS}
    kwargs["category"] = "food"
    kwargs["brand_blocking_key"] = None
    return baq.Listing(**kwargs)


def test_predict_label_parity_over_the_real_frozen_queue() -> None:
    raw = QUEUE_JSON.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_QUEUE_SHA256, (
        "frozen queue does not match FROZEN_QUEUE_SHA256 -- something edited the 'frozen' file"
    )
    pairs = json.loads(raw.decode("utf-8"))["pairs"]
    assert len(pairs) == 997

    mismatches = []
    for pair in pairs:
        left_dict, right_dict = pair["left"], pair["right"]
        left_obj, right_obj = _to_listing(left_dict), _to_listing(right_dict)
        label_a, rule_a = baq.predict_label(left_obj, right_obj)
        label_b, rule_b = saq.predict_label(left_dict, right_dict)
        if (label_a, rule_a) != (label_b, rule_b):
            mismatches.append((pair["pair_id"], (label_a, rule_a), (label_b, rule_b)))

    assert mismatches == [], (
        f"{len(mismatches)} pair(s) disagree between build_annotation_queue.py's and "
        f"split_annotation_queue.py's predict_label(): {mismatches[:5]}"
    )
