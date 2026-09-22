"""Freeze the Phase 3 label dataset (DECISIONS.md ADR-0028 addendum #15).

    uv run python scripts/freeze_labels.py            # report: current hash + frozen/unfrozen
    uv run python scripts/freeze_labels.py --freeze   # ONE-TIME: record the hash

`--freeze` refuses unless (1) the dataset has 997 decisions and (2) the mechanical checker has no
class a/b/c/d/f finding left (class e is a stored-data defect, not a label problem). On success it
writes the SHA-256 of docs/learned/phase3-labels.json into `FROZEN_LABELS_SHA256` in
tests/test_labels_frozen.py and into the marker line in STATE.md. Run it only AFTER the annotator's
final review pass has been ingested. Once frozen, no label may change without a stated reason
recorded in STATE.md first; the test then fails on any change, and re-freezing needs a manual edit
of the constant back to UNFROZEN -- deliberately not a flag.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_label_rule_consistency as clc  # noqa: E402

LABELS_JSON = ROOT / "docs" / "learned" / "phase3-labels.json"
TEST_FILE = ROOT / "tests" / "test_labels_frozen.py"
STATE_MD = ROOT / "STATE.md"
UNFROZEN = "UNFROZEN"
ACK_JSON = ROOT / "docs" / "learned" / "phase3-freeze-acknowledgements.json"
EXPECTED_DECISIONS = 997
_CONST_RE = re.compile(r'^(FROZEN_LABELS_SHA256\s*=\s*)"[^"]*"', re.MULTILINE)
_STATE_RE = re.compile(r"^(Frozen labels SHA-256:\s*)`[^`]*`", re.MULTILINE)


def labels_sha256(path: Path = LABELS_JSON) -> str:
    # CRLF->LF so a Windows worktree and a Linux CI checkout (.gitattributes eol=lf) agree.
    return clc.sha256_lf(path.read_bytes())


def blocking_findings() -> dict[str, int]:
    """Findings still open. An occurrence listed in ACK_JSON ({occurrence_id: reason}) was reviewed
    and its label deliberately kept -- the checker never overrides the annotator."""
    queue_sha = clc.sha256_lf(clc.QUEUE_JSON.read_bytes())
    if queue_sha != clc.FROZEN_QUEUE_SHA256:
        raise SystemExit("REFUSING: frozen queue hash mismatch.")
    acked: dict[str, str] = (
        json.loads(ACK_JSON.read_text(encoding="utf-8")) if ACK_JSON.exists() else {}
    )
    queue = json.loads(clc.QUEUE_JSON.read_text(encoding="utf-8"))["pairs"]
    pairs_by_occ = dict(zip(clc.derive_occurrence_ids(queue), queue, strict=True))
    decisions = json.loads(LABELS_JSON.read_text(encoding="utf-8"))["decisions"]
    counts: dict[str, int] = {}
    for f in clc.check(pairs_by_occ, decisions):
        if f.cls != "e" and not acked.get(f.occurrence_id):
            counts[f.cls] = counts.get(f.cls, 0) + 1
    return counts


def write_hash(digest: str, test_file: Path = TEST_FILE, state_md: Path = STATE_MD) -> None:
    test_text = test_file.read_text(encoding="utf-8")
    if not _CONST_RE.search(test_text):
        raise SystemExit(f"FROZEN_LABELS_SHA256 not found in {test_file}")
    test_file.write_text(_CONST_RE.sub(rf'\g<1>"{digest}"', test_text, count=1), encoding="utf-8")
    state_text = state_md.read_text(encoding="utf-8")
    if not _STATE_RE.search(state_text):
        raise SystemExit(f"'Frozen labels SHA-256:' marker line not found in {state_md}")
    state_md.write_text(_STATE_RE.sub(rf"\g<1>`{digest}`", state_text, count=1), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--freeze", action="store_true", help="record the hash (one-time)")
    args = ap.parse_args()

    digest = labels_sha256()
    current = _CONST_RE.search(TEST_FILE.read_text(encoding="utf-8"))
    recorded = current.group(0).split('"')[1] if current else "?"
    print(f"labels SHA-256: {digest}")
    print(f"recorded:       {recorded}")
    if not args.freeze:
        print(
            "status:",
            "FROZEN, unchanged"
            if recorded == digest
            else "UNFROZEN"
            if recorded == UNFROZEN
            else "FROZEN BUT CHANGED -- investigate",
        )
        return 0
    if recorded != UNFROZEN:
        print(
            "REFUSING: already frozen. Edit the constant back to UNFROZEN by hand, with a "
            "reason recorded in STATE.md first.",
            file=sys.stderr,
        )
        return 1
    n = len(json.loads(LABELS_JSON.read_text(encoding="utf-8"))["decisions"])
    if n != EXPECTED_DECISIONS:
        print(f"REFUSING: {n} decisions, expected {EXPECTED_DECISIONS}.", file=sys.stderr)
        return 1
    blocking = blocking_findings()
    if blocking:
        print(f"REFUSING: unresolved checker findings {blocking}.", file=sys.stderr)
        return 1
    write_hash(digest)
    print("frozen. Commit tests/test_labels_frozen.py and STATE.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
