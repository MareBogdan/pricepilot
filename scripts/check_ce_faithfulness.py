r"""Phase 5 s3b Task 1 -- does the locally loaded cross-encoder reproduce the benchmarked one?

    .venv\Scripts\python scripts/check_ce_faithfulness.py [--model-dir models/ce-ft-best]

Scores the 287 committed TEST model inputs (`docs/learned/model-inputs/phase3-inputs-test.json`,
built by `build_pair_text`; NO labels in that file) with `CrossEncoderScorer` and compares to the
committed PyTorch-fp32 predictions (`docs/learned/results/serving/preds-ce-ptfp32-test.json`).
Reads no label, so it is not a TEST touch. Exit code 1 if NOT reproduced -- the matcher must not
score our products with a model this check cannot vouch for.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pricepilot.matching.serve import CrossEncoderScorer, check_reproduction  # noqa: E402

INPUTS = ROOT / "docs" / "learned" / "model-inputs" / "phase3-inputs-test.json"
COMMITTED = ROOT / "docs" / "learned" / "results" / "serving" / "preds-ce-ptfp32-test.json"
OUT = ROOT / "docs" / "learned" / "results" / "phase5" / "ce-faithfulness.json"


def run(model_dir: Path, scorer: CrossEncoderScorer | None = None) -> dict[str, Any]:
    pairs = json.loads(INPUTS.read_text(encoding="utf-8"))["pairs"]
    committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
    scorer = scorer or CrossEncoderScorer(model_dir)
    t0 = time.perf_counter()
    scores = scorer.score([(p["text_a"], p["text_b"]) for p in pairs])
    elapsed = time.perf_counter() - t0
    by_id = {p["pair_id"]: s for p, s in zip(pairs, scores, strict=True)}
    result = check_reproduction(by_id, committed)
    result.update(
        weights_sha256=scorer.weights_sha256,
        seconds=round(elapsed, 1),
        pairs_per_second=round(len(pairs) / elapsed, 1),
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models" / "ce-ft-best")
    args = parser.parse_args()
    result = run(args.model_dir)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print("REPRODUCED" if result["reproduced"] else "NOT_REPRODUCED")
    return 0 if result["reproduced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
