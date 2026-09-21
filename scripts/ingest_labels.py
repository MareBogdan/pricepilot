r"""Phase 3 STEP 8 (ADR-0028 addendum #12, TASK 3) -- turns `tools/annotate.html` label exports
into the verified, committed dataset (`docs/learned/phase3-labels.json`) plus a QA report.

This is the ONLY path from a browser export into the committed dataset. It is written to be
STRUCTURALLY UNABLE TO ACCEPT AN AI-PRODUCED LABEL: every decision must carry the exact
provenance shape the real tool emits (`pair_id`/`tier`/`split`/`answer`/`source`/`ms`/
`decided_at`/`engine_prediction`/`corrected`/`flagged`/`s_reason`, cross-checked field-by-field
against the canonical FROZEN queue and the committed split file -- not just present, but equal to
what the queue/split actually say for that `occurrence_id`), a `source` the tool itself assigns
from which key the annotator pressed (never free text), and a TEST decision's `source` pinned to
"blind" (the tool structurally never shows a suggestion on a TEST pair -- see
`tools/annotate.html`'s own three independent guards, ADR-0028 addendum #10). This does NOT
cryptographically prove a human typed each answer -- no export format can. What it does mean:
producing an export this script accepts requires faithfully reproducing the real tool's entire
state machine and cross-checking every field against the frozen data, not just writing
`{"label": "M"}` 997 times. Stated plainly so this limitation is never overclaimed.

    uv run python scripts/ingest_labels.py <export.json> [<export2.json> ...]
    uv run python scripts/ingest_labels.py docs/learned/labels/*.json --resolve=latest

REFUSES (clear message on stderr, exit 1) and writes NOTHING on:
  - queue SHA-256 mismatch (an export's `queue_sha256` != the frozen queue's actual hash)
  - split-file SHA-256 mismatch (an export's `split_sha256` != the committed split file's hash)
  - an occurrence_id in an export that is not present in the frozen queue
  - a label (`answer`) outside {M, N, S}
  - a decision with no `source` field
  - a `source` value other than blind/override/confirm
  - a TEST decision whose `source` is not "blind" (and, symmetrically, a TRAIN_VAL decision whose
    `source` IS "blind" -- the tool can never produce either shape)
  - a decision whose recorded pair_id/tier/split disagrees with the frozen queue/split for that
    occurrence_id
  - a TEST decision carrying a non-null `engine_prediction` (the real tool never attaches one)
  - a "confirm"-sourced decision whose `answer` differs from the rules engine's own suggestion, or
    a `corrected` flag that doesn't match what `decide()` would have computed for that
    source/suggestion/answer combination

MERGES multiple exports (several sittings, possibly overlapping). A genuine conflict -- the same
occurrence_id labelled DIFFERENTLY across exports -- is never silently resolved: both are printed
with their timestamps and the run exits non-zero, unless `--resolve=latest` is passed, in which
case the decision with the later `decided_at` wins (also printed). Handles a PARTIAL export (e.g.
the first 100 pilot decisions) with no special-casing needed: coverage in the QA report just shows
fewer decided than total.

Writes `docs/learned/phase3-labels.json` (queue/split SHA-256s, ingest timestamp, per-file
provenance, and per-occurrence_id: label, split, tier, source, corrected, ms, decided_at) and
`docs/learned/phase3-label-qa-<date>.md` (same content also printed to stdout).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

QUEUE_JSON = ROOT / "docs" / "learned" / "phase3-annotation-queue.json"
SPLIT_JSON = ROOT / "docs" / "learned" / "phase3-annotation-split.json"
TEST_REFERENCE_JSON = ROOT / "docs" / "learned" / "phase3-test-split-reference-predictions.json"
REPEAT_LOOKUP_JSON = ROOT / "docs" / "learned" / "phase3-repeat-first-occurrence.json"
LABELS_JSON = ROOT / "docs" / "learned" / "phase3-labels.json"

# Recorded the moment the queue was frozen (ADR-0028 addendum #9) -- same constant as
# scripts/split_annotation_queue.py and tests/test_annotation_split.py.
FROZEN_QUEUE_SHA256 = "696e983392628b868c4becd92db400735a52498a4994b5b7c8651b160a087011"

VALID_ANSWERS = {"M", "N", "S"}
VALID_SOURCES = {"blind", "override", "confirm"}
REQUIRED_DECISION_FIELDS = {
    "pair_id",
    "tier",
    "split",
    "answer",
    "source",
    "engine_prediction",
    "corrected",
    "flagged",
    "s_reason",
    "ms",
    "decided_at",
}
REQUIRED_EXPORT_FIELDS = {"queue_sha256", "split_sha256", "decision_count", "exported_at", "state"}


def refuse(message: str) -> None:
    print(f"REFUSING: {message}", file=sys.stderr)
    sys.exit(1)


def derive_occurrence_ids(pairs: list[dict[str, Any]]) -> list[str]:
    """Same rule as `scripts/split_annotation_queue.py::derive_occurrence_ids()` and
    `tools/annotate.html::deriveOccurrenceIds()` -- duplicated here deliberately (not imported),
    same discipline as `tests/test_annotation_split.py`'s own duplicate."""
    counts: dict[str, int] = {}
    ids = []
    for p in pairs:
        pid = p["pair_id"]
        k = counts.get(pid, 0)
        ids.append(f"{pid}_{k}")
        counts[pid] = k + 1
    return ids


def wilson_ci(x: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Wilson score interval -- same formula as scripts/measure_recall_at_20.py's own."""
    if n == 0:
        return 0.0, 0.0, 0.0
    p_hat = x / n
    denom = 1 + z**2 / n
    centre = p_hat + z**2 / (2 * n)
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2))
    return p_hat, (centre - margin) / denom, (centre + margin) / denom


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))
    return s[idx]


def fmt_ms(ms: float | None) -> str:
    return "-" if ms is None else f"{ms / 1000:.1f}s"


def fmt_pct_ci(x: int, n: int) -> str:
    if n == 0:
        return "n=0 (no decisions yet)"
    p_hat, lo, hi = wilson_ci(x, n)
    return f"{x}/{n} = {p_hat * 100:.1f}% [{lo * 100:.1f}%, {hi * 100:.1f}%]"


@dataclass
class CanonicalRow:
    pair_id: str
    tier: str
    split: str
    engine_prediction_label: str | None  # None for TEST (never shown), else "M"/"N"/"S"


def load_canonical() -> tuple[str, str, dict[str, CanonicalRow]]:
    """Returns (actual_queue_sha256, actual_split_sha256, occurrence_id -> CanonicalRow), built
    the same way the tool merges queue + split (ADR-0028 addendum #10/#11) and the same way
    scripts/compute_repeat_first_occurrence.js merges them."""
    if not QUEUE_JSON.exists():
        refuse(f"frozen queue not found: {QUEUE_JSON}")
    if not SPLIT_JSON.exists():
        refuse(f"split file not found: {SPLIT_JSON} -- run scripts/split_annotation_queue.py first")

    queue_raw = QUEUE_JSON.read_bytes()
    actual_queue_sha256 = hashlib.sha256(queue_raw).hexdigest()
    if actual_queue_sha256 != FROZEN_QUEUE_SHA256:
        refuse(
            f"the committed frozen queue itself does not match FROZEN_QUEUE_SHA256 "
            f"(expected {FROZEN_QUEUE_SHA256}, got {actual_queue_sha256}) -- something edited the "
            f"'frozen' file; investigate before ingesting anything against it"
        )

    split_raw = SPLIT_JSON.read_bytes()
    actual_split_sha256 = hashlib.sha256(split_raw).hexdigest()

    queue = json.loads(queue_raw.decode("utf-8"))
    split = json.loads(split_raw.decode("utf-8"))
    pairs = queue["pairs"]
    occurrence_ids = derive_occurrence_ids(pairs)

    canonical: dict[str, CanonicalRow] = {}
    test_reference: dict[str, Any] = {}
    if TEST_REFERENCE_JSON.exists():
        test_reference = json.loads(TEST_REFERENCE_JSON.read_text(encoding="utf-8"))["predictions"]

    for occ_id, p in zip(occurrence_ids, pairs, strict=True):
        a = split["assignments"].get(occ_id)
        if a is None:
            refuse(
                f"queue/split out of sync: {occ_id} has no assignment in {SPLIT_JSON.name} -- "
                f"re-run scripts/split_annotation_queue.py"
            )
        assert a is not None
        if a["split"] == "train_val":
            forecast_label = a["engine_prediction"]["label"]
        else:
            ref = test_reference.get(occ_id)
            forecast_label = ref["engine_prediction"]["label"] if ref else None
        canonical[occ_id] = CanonicalRow(
            pair_id=p["pair_id"],
            tier=p["tier"],
            split=a["split"],
            engine_prediction_label=forecast_label,
        )

    return actual_queue_sha256, actual_split_sha256, canonical


@dataclass
class LoadedExport:
    path: Path
    exported_at: str
    decision_count_claimed: int
    decisions: dict[str, dict[str, Any]]  # occurrence_id -> validated raw decision dict


def load_and_validate_export(
    path: Path,
    canonical: dict[str, CanonicalRow],
    actual_queue_sha256: str,
    actual_split_sha256: str,
) -> LoadedExport:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        refuse(f"{path}: could not read file ({e})")
        raise  # unreachable, refuse() exits; satisfies type checker
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as e:
        refuse(f"{path}: not valid JSON ({e})")
        raise

    if not isinstance(payload, dict):
        refuse(
            f"{path}: top level is not a JSON object -- not a real export from tools/annotate.html"
        )
    missing_top = REQUIRED_EXPORT_FIELDS - set(payload.keys())
    if missing_top:
        refuse(
            f"{path}: missing required top-level field(s) {sorted(missing_top)} -- not a real "
            f"export from tools/annotate.html's Export (E) button"
        )

    if payload["queue_sha256"] != actual_queue_sha256:
        refuse(
            f"{path}: queue SHA-256 mismatch -- this export was recorded against a different "
            f"queue file (export: {payload['queue_sha256']}, current frozen queue: "
            f"{actual_queue_sha256}). Refusing to ingest."
        )
    if payload["split_sha256"] != actual_split_sha256:
        refuse(
            f"{path}: split-file SHA-256 mismatch -- this export was recorded against a "
            f"different split file (export: {payload['split_sha256']}, current split file: "
            f"{actual_split_sha256}). Refusing to ingest."
        )

    state = payload["state"]
    if not isinstance(state, dict):
        refuse(f"{path}: 'state' is not a JSON object")

    validated: dict[str, dict[str, Any]] = {}
    for occ_id, decision in state.items():
        if occ_id not in canonical:
            refuse(f"{path}: occurrence_id {occ_id!r} is not present in the frozen queue")
        if not isinstance(decision, dict):
            refuse(f"{path}: decision for {occ_id!r} is not a JSON object")

        if "source" not in decision:
            refuse(f"{path}: decision for {occ_id!r} has no 'source' field")

        missing = REQUIRED_DECISION_FIELDS - set(decision.keys())
        if missing:
            refuse(
                f"{path}: decision for {occ_id!r} is missing field(s) {sorted(missing)} -- not "
                f"the shape tools/annotate.html's decide() actually writes"
            )

        answer = decision["answer"]
        if answer not in VALID_ANSWERS:
            refuse(f"{path}: decision for {occ_id!r} has label {answer!r}, outside {{M, N, S}}")

        source = decision["source"]
        if source not in VALID_SOURCES:
            refuse(
                f"{path}: decision for {occ_id!r} has source {source!r}, must be one of "
                f"blind/override/confirm"
            )

        canon = canonical[occ_id]
        if canon.split == "test" and source != "blind":
            refuse(
                f"{path}: TEST decision for {occ_id!r} has source {source!r} -- TEST pairs are "
                f"never shown a suggestion, so a TEST decision's source must always be 'blind'"
            )
        if canon.split == "train_val" and source == "blind":
            refuse(
                f"{path}: TRAIN_VAL decision for {occ_id!r} has source 'blind' -- only TEST "
                f"pairs are blind; the tool structurally cannot produce this shape"
            )

        # The module docstring claims every provenance field is cross-checked against what the
        # queue/split actually say, "not just present, but equal" -- these three close the gap a
        # review found: pair_id/tier/split were checked (below), but engine_prediction/corrected
        # were only presence-checked, which let a hand-crafted export claim a "confirm" for a
        # label the rules engine never suggested, or a populated engine_prediction on a TEST row
        # (impossible for the real tool -- decide() always writes null there).
        if canon.split == "test" and decision["engine_prediction"] is not None:
            refuse(
                f"{path}: TEST decision for {occ_id!r} carries a non-null engine_prediction -- "
                f"the real tool never attaches one to a TEST row (see tools/annotate.html's "
                f"three independent TEST-blindness guards)"
            )
        if source == "confirm" and answer != canon.engine_prediction_label:
            refuse(
                f"{path}: decision for {occ_id!r} has source 'confirm' but answer {answer!r} != "
                f"the rules engine's own suggestion {canon.engine_prediction_label!r} -- "
                f"confirmSuggestion() can only ever record the suggested label itself"
            )
        # TASK 4 (ADR-0028 addendum #13) -- a review-mode revision ALWAYS carries a null
        # engine_prediction (GUARD 1, tools/annotate.html's initReviewMode()), so decide() always
        # computes corrected=False for one, regardless of what the CANONICAL split file's
        # engine_prediction says for that occurrence_id -- there was no suggestion on screen to be
        # "corrected" relative to. Checking against the canonical suggestion here (as an ordinary,
        # non-review decision must) would refuse a legitimate TRAIN_VAL review revision whenever
        # the canonical prediction disagrees with the revised answer -- found on review, before
        # this shipped with only TEST-split revisions ever exercised.
        if "revised_at" in decision:
            expected_corrected = False
        else:
            expected_corrected = source == "override" and canon.engine_prediction_label not in (
                None,
                answer,
            )
        if decision["corrected"] != expected_corrected:
            refuse(
                f"{path}: decision for {occ_id!r} has corrected={decision['corrected']!r}, but "
                f"given source={source!r} and the rules engine's suggestion "
                f"{canon.engine_prediction_label!r}, decide() would have computed "
                f"{expected_corrected!r}"
            )

        for field, canon_value in (
            ("pair_id", canon.pair_id),
            ("tier", canon.tier),
            ("split", canon.split),
        ):
            if decision[field] != canon_value:
                refuse(
                    f"{path}: decision for {occ_id!r} has {field}={decision[field]!r}, but the "
                    f"frozen queue/split says {field}={canon_value!r}"
                )

        validated[occ_id] = decision

    return LoadedExport(
        path=path,
        exported_at=payload["exported_at"],
        decision_count_claimed=payload["decision_count"],
        decisions=validated,
    )


def _is_legitimate_revision(newer: dict[str, Any]) -> bool:
    """TASK 4 (ADR-0028 addendum #13) -- a review-mode re-decision changes an occurrence_id's
    answer BY DESIGN (that is the whole point of `tools/annotate.html`'s review mode). Two exports
    disagreeing on an occurrence_id's answer must therefore not always be treated as a genuine
    conflict: whenever the chronologically LATER decision carries a `revised_from` at all, it was
    produced by review mode -- the only code path that ever sets this field (`decide()`) -- so it
    is trusted as an intentional, audited revision.

    Deliberately does NOT also require `newer["revised_from"] == older["answer"]`: review mode's
    own documented workflow supports revising the SAME occurrence_id more than once in one
    sitting (`undo()` steps back so a mis-press can be re-decided again), and each further
    revision's `revised_from` names the PREVIOUS revision's answer, not the original pre-review
    one. A chain M -> N -> S merged from two separate exports (one holding the original "M", the
    other the final "S" with `revised_from: "N"`) would fail a strict equality check even though
    it is exactly the two-revision case the tool supports -- found on review before it shipped
    with only ever a single revision exercised."""
    return newer.get("revised_from") is not None


def merge_exports(
    loaded: list[LoadedExport], resolve_latest: bool
) -> tuple[
    dict[str, tuple[dict[str, Any], Path]],
    list[tuple[str, dict[str, Any], Path, dict[str, Any], Path]],
]:
    merged: dict[str, tuple[dict[str, Any], Path]] = {}
    conflicts: list[tuple[str, dict[str, Any], Path, dict[str, Any], Path]] = []
    revisions: list[tuple[str, dict[str, Any], Path, dict[str, Any], Path]] = []

    for export in loaded:
        for occ_id, decision in export.decisions.items():
            if occ_id not in merged:
                merged[occ_id] = (decision, export.path)
                continue
            existing_decision, existing_path = merged[occ_id]
            if existing_decision["answer"] != decision["answer"]:
                # Order the two chronologically first -- a revision is only legitimate in the
                # direction OLD ANSWER -> NEW ANSWER, regardless of which export file happened to
                # be passed on the command line first.
                if existing_decision["decided_at"] <= decision["decided_at"]:
                    older, older_path, newer, newer_path = (
                        existing_decision,
                        existing_path,
                        decision,
                        export.path,
                    )
                else:
                    older, older_path, newer, newer_path = (
                        decision,
                        export.path,
                        existing_decision,
                        existing_path,
                    )
                if _is_legitimate_revision(newer):
                    revisions.append((occ_id, older, older_path, newer, newer_path))
                    merged[occ_id] = (newer, newer_path)
                    continue
                conflicts.append((occ_id, existing_decision, existing_path, decision, export.path))
                if resolve_latest and decision["decided_at"] >= existing_decision["decided_at"]:
                    merged[occ_id] = (decision, export.path)
                continue
            # Same label across files -- not a conflict; keep the more recent record (metadata
            # such as flagged/s_reason may have been updated after the label was first set).
            if decision["decided_at"] >= existing_decision["decided_at"]:
                merged[occ_id] = (decision, export.path)

    if conflicts and not resolve_latest:
        print(
            f"REFUSING: {len(conflicts)} genuine conflict(s) -- same occurrence_id, different "
            f"label, across exports (not an audited review-mode revision -- see "
            f"revised_from/ADR-0028 addendum #13). Pass --resolve=latest to resolve by "
            f"most-recent decided_at.",
            file=sys.stderr,
        )
        for occ_id, d1, p1, d2, p2 in conflicts:
            print(
                f"  {occ_id}: {p1.name} @ {d1['decided_at']} -> {d1['answer']!r}   vs.   "
                f"{p2.name} @ {d2['decided_at']} -> {d2['answer']!r}",
                file=sys.stderr,
            )
        sys.exit(1)

    if conflicts:
        print(
            f"RESOLVED {len(conflicts)} conflict(s) via --resolve=latest (most recent decided_at kept):"
        )
        for occ_id, d1, p1, d2, p2 in conflicts:
            kept, kept_path = merged[occ_id]
            print(
                f"  {occ_id}: {p1.name} @ {d1['decided_at']} -> {d1['answer']!r}   vs.   "
                f"{p2.name} @ {d2['decided_at']} -> {d2['answer']!r}   ==> kept "
                f"{kept_path.name} -> {kept['answer']!r}"
            )

    if revisions:
        print(f"\n{len(revisions)} audited review-mode revision(s) merged (not conflicts):")
        for occ_id, older, older_path, newer, newer_path in revisions:
            print(
                f"  {occ_id}: {older_path.name} @ {older['decided_at']} -> {older['answer']!r}   "
                f"REVISED TO   {newer_path.name} @ {newer['decided_at']} -> {newer['answer']!r} "
                f"(rule: {newer.get('revision_rule')})"
            )

    return merged, revisions


def build_qa_report(
    canonical: dict[str, CanonicalRow],
    decisions: dict[str, dict[str, Any]],
    loaded: list[LoadedExport],
    repeat_lookup: dict[str, Any],
    revisions: list[tuple[str, dict[str, Any], Path, dict[str, Any], Path]] | None = None,
) -> str:
    lines: list[str] = []
    add = lines.append

    total_by_split = {"test": 0, "train_val": 0}
    total_by_tier: dict[str, int] = {}
    for row in canonical.values():
        total_by_split[row.split] += 1
        total_by_tier[row.tier] = total_by_tier.get(row.tier, 0) + 1

    decided_by_split = {"test": 0, "train_val": 0}
    decided_by_tier: dict[str, int] = {}
    label_counts_overall = {"M": 0, "N": 0, "S": 0}
    label_counts_by_split = {
        "test": {"M": 0, "N": 0, "S": 0},
        "train_val": {"M": 0, "N": 0, "S": 0},
    }
    label_counts_by_tier: dict[str, dict[str, int]] = {}
    forecast_counts_overall = {"M": 0, "N": 0, "S": 0}
    forecast_counts_by_split = {
        "test": {"M": 0, "N": 0, "S": 0},
        "train_val": {"M": 0, "N": 0, "S": 0},
    }
    ms_by_split: dict[str, list[float]] = {"test": [], "train_val": []}
    ms_by_tier: dict[str, list[float]] = {}
    flagged: list[tuple[str, str]] = []
    s_decisions: list[tuple[str, str, str]] = []

    confirmed = corrected = overrode_agreed = 0
    corrected_by_tier: dict[str, int] = {}
    trainval_by_tier: dict[str, int] = {}
    ms_confirmed: list[float] = []
    ms_corrected: list[float] = []

    for occ_id, decision in decisions.items():
        canon = canonical[occ_id]
        answer = decision["answer"]
        decided_by_split[canon.split] += 1
        decided_by_tier[canon.tier] = decided_by_tier.get(canon.tier, 0) + 1
        label_counts_overall[answer] += 1
        label_counts_by_split[canon.split][answer] += 1
        label_counts_by_tier.setdefault(canon.tier, {"M": 0, "N": 0, "S": 0})[answer] += 1

        if canon.engine_prediction_label is not None:
            forecast_counts_overall[canon.engine_prediction_label] += 1
            forecast_counts_by_split[canon.split][canon.engine_prediction_label] += 1

        if isinstance(decision["ms"], int | float):
            ms_by_split[canon.split].append(decision["ms"])
            ms_by_tier.setdefault(canon.tier, []).append(decision["ms"])

        if decision["flagged"]:
            flagged.append((occ_id, canon.pair_id))
        if answer == "S":
            s_decisions.append((occ_id, canon.pair_id, decision["s_reason"] or "unspecified"))

        # TASK 4 (ADR-0028 addendum #13) -- a review-mode revision is excluded from the assisted
        # flow entirely: it always carries source="override"/corrected=False (GUARD 1 nulls the
        # prediction, so there was never a suggestion to be "corrected" relative to), and counting
        # it here would land it in "overrode but agreed w/ suggestion" and inflate
        # `trainval_by_tier`'s denominator with a decision the correction-rate metric was never
        # about. Counted instead in the "Review-mode revisions" section below.
        if canon.split == "train_val" and "revised_at" not in decision:
            trainval_by_tier[canon.tier] = trainval_by_tier.get(canon.tier, 0) + 1
            if decision["source"] == "confirm":
                confirmed += 1
                if isinstance(decision["ms"], int | float):
                    ms_confirmed.append(decision["ms"])
            elif decision["source"] == "override":
                if decision["corrected"]:
                    corrected += 1
                    corrected_by_tier[canon.tier] = corrected_by_tier.get(canon.tier, 0) + 1
                    if isinstance(decision["ms"], int | float):
                        ms_corrected.append(decision["ms"])
                else:
                    overrode_agreed += 1

    add("# Phase 3 label QA report")
    add("")
    add(f"Generated: {datetime.now(UTC).isoformat()}")
    add(f"Source files ({len(loaded)}):")
    for export in loaded:
        add(
            f"  - {export.path.name}: {len(export.decisions)} decisions in file "
            f"(claimed {export.decision_count_claimed}), exported_at={export.exported_at}"
        )
    add("")

    add("## Coverage")
    add("")
    add(f"Overall: {fmt_pct_ci(sum(decided_by_split.values()), sum(total_by_split.values()))}")
    for split in ("test", "train_val"):
        add(f"  {split}: {fmt_pct_ci(decided_by_split[split], total_by_split[split])}")
    add("")
    add("Per tier:")
    for tier in sorted(total_by_tier):
        add(f"  {tier}: {fmt_pct_ci(decided_by_tier.get(tier, 0), total_by_tier[tier])}")
    add("")

    add("## Label distribution (M/N/S)")
    add("")
    add(
        "Rules-engine forecast is shown SIDE BY SIDE as a DIAGNOSTIC only -- it is never a "
        "correctness judgement of Bogdan's labels. It is computed over the SAME decided "
        "occurrence_ids as the observed counts (not the whole population), for a fair comparison."
    )
    add("")
    for scope_name, observed, forecast, n in (
        ("overall", label_counts_overall, forecast_counts_overall, sum(decided_by_split.values())),
        (
            "test",
            label_counts_by_split["test"],
            forecast_counts_by_split["test"],
            decided_by_split["test"],
        ),
        (
            "train_val",
            label_counts_by_split["train_val"],
            forecast_counts_by_split["train_val"],
            decided_by_split["train_val"],
        ),
    ):
        add(f"### {scope_name} (n={n} decided)")
        for label in ("M", "N", "S"):
            obs = fmt_pct_ci(observed[label], n) if n else "n=0"
            fc = forecast[label]
            add(f"  {label}: observed {obs}   |   forecast {fc}/{n if n else 0}")
        add("")
    add("Per tier (observed only, n too small for forecast to be meaningful tier-by-tier):")
    for tier in sorted(label_counts_by_tier):
        n = decided_by_tier.get(tier, 0)
        counts = label_counts_by_tier[tier]
        add(f"  {tier} (n={n}): M={counts['M']} N={counts['N']} S={counts['S']}")
    add("")

    add("## Self-agreement (repeated pairs, both occurrences decided)")
    add("")
    add(
        "TRAIN_VAL repeats are both ASSISTED -- the annotator saw a suggestion both times, so "
        "agreement there is anchored by the rules engine and is a weaker signal than TEST "
        "self-agreement, where neither occurrence was ever shown a suggestion."
    )
    add("")
    for split_name in ("test", "train_val"):
        eligible = 0
        agree = 0
        total_repeats_in_split = sum(1 for e in repeat_lookup.values() if e["split"] == split_name)
        for entry in repeat_lookup.values():
            if entry["split"] != split_name:
                continue
            d1 = decisions.get(entry["first_occurrence_id"])
            d2 = decisions.get(entry["second_occurrence_id"])
            if d1 is None or d2 is None:
                continue
            eligible += 1
            if d1["answer"] == d2["answer"]:
                agree += 1
        add(
            f"  {split_name}: {eligible}/{total_repeats_in_split} repeated pairs have both "
            f"occurrences decided; of those, {fmt_pct_ci(agree, eligible) if eligible else 'n=0'} agree"
        )
    add("")

    add("## Assisted flow (TRAIN_VAL only)")
    add("")
    trainval_decided = decided_by_split["train_val"]
    add(f"TRAIN_VAL decisions: {trainval_decided}")
    add(f"  confirmed (pressed C): {confirmed}")
    add(f"  corrected (overrode, differs from suggestion): {corrected}")
    add(f"  overrode but agreed with suggestion: {overrode_agreed}")
    add(
        f"  correction rate (overall): {fmt_pct_ci(corrected, trainval_decided) if trainval_decided else 'n=0'}"
    )
    add("  correction rate per tier:")
    for tier in sorted(trainval_by_tier):
        add(f"    {tier}: {fmt_pct_ci(corrected_by_tier.get(tier, 0), trainval_by_tier[tier])}")
    add(f"  median decision time, confirmed: {fmt_ms(percentile(ms_confirmed, 50))}")
    add(f"  median decision time, corrected: {fmt_ms(percentile(ms_corrected, 50))}")
    add("")

    add("## Throughput")
    add("")
    add(
        "First real measurement of CLAUDE.md §7's untested '200 pairs/hour' claim "
        "(sub-18s median decision)."
    )
    add("")
    all_ms = ms_by_split["test"] + ms_by_split["train_val"]
    for scope_name, values in (
        ("overall", all_ms),
        ("test", ms_by_split["test"]),
        ("train_val", ms_by_split["train_val"]),
    ):
        med = percentile(values, 50)
        p90 = percentile(values, 90)
        remaining = (
            (total_by_split["test"] - decided_by_split["test"])
            + (total_by_split["train_val"] - decided_by_split["train_val"])
            if scope_name == "overall"
            else total_by_split[scope_name] - decided_by_split[scope_name]
        )
        implied_hours = (
            "-" if med is None or med == 0 else f"{(remaining * med / 1000 / 3600):.1f}h"
        )
        add(
            f"  {scope_name} (n={len(values)}): median {fmt_ms(med)}, p90 {fmt_ms(p90)}, "
            f"{remaining} remaining -> implied {implied_hours} to finish (at this median pace)"
        )
    add("  Per-tier median decision time:")
    for tier in sorted(ms_by_tier):
        add(
            f"    {tier}: median {fmt_ms(percentile(ms_by_tier[tier], 50))} (n={len(ms_by_tier[tier])})"
        )
    add("")

    add("## Flagged pairs")
    add("")
    if flagged:
        for occ_id, pair_id in flagged:
            add(f"  - {occ_id} (pair_id={pair_id})")
    else:
        add("  (none flagged)")
    add("")

    add("## Skip (S) decisions and their stated reasons")
    add("")
    if s_decisions:
        for occ_id, pair_id, reason in s_decisions:
            add(f"  - {occ_id} (pair_id={pair_id}): {reason}")
    else:
        add("  (no S decisions yet)")
    add("")

    # TASK 4 (ADR-0028 addendum #13) -- review-mode revisions, counted by the rule that flagged
    # the pair in the first place (`revision_rule`, joined by comma when more than one class
    # fired -- see scripts/check_label_rule_consistency.py). These are audited label CHANGES, not
    # export conflicts (merge_exports()'s own distinction) -- reported here so the QA report is
    # the one place that shows how many mechanical-rule findings actually got corrected.
    add("## Review-mode revisions")
    add("")
    if revisions:
        by_rule: dict[str, int] = {}
        for _occ_id, _older, _older_path, newer, _newer_path in revisions:
            rule = newer.get("revision_rule") or "(unknown)"
            by_rule[rule] = by_rule.get(rule, 0) + 1
        add(f"Total revised: {len(revisions)}")
        add("By rule:")
        for rule in sorted(by_rule):
            add(f"  {rule}: {by_rule[rule]}")
        add("")
        add("Detail (old -> new):")
        for occ_id, older, _older_path, newer, _newer_path in revisions:
            add(
                f"  - {occ_id} (pair_id={newer['pair_id']}): {older['answer']!r} -> "
                f"{newer['answer']!r} (rule: {newer.get('revision_rule')}, "
                f"revised_at={newer.get('revised_at')})"
            )
    else:
        add("  (no revisions in this ingest)")
    add("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("files", nargs="+", help="one or more label export JSON files")
    parser.add_argument(
        "--resolve",
        choices=["latest"],
        default=None,
        help="resolve genuine label conflicts across exports by keeping the most recent decided_at",
    )
    args = parser.parse_args(argv)

    paths = [Path(f) for f in args.files]
    for p in paths:
        if not p.exists():
            refuse(f"file not found: {p}")

    actual_queue_sha256, actual_split_sha256, canonical = load_canonical()
    print(f"frozen queue SHA-256: {actual_queue_sha256} (matches FROZEN_QUEUE_SHA256)")
    print(f"split file SHA-256: {actual_split_sha256}")
    print(f"canonical occurrence_ids: {len(canonical)}")

    loaded = [
        load_and_validate_export(p, canonical, actual_queue_sha256, actual_split_sha256)
        for p in paths
    ]
    for export in loaded:
        print(f"{export.path}: {len(export.decisions)} valid decision(s)")

    merged, revisions = merge_exports(loaded, resolve_latest=args.resolve == "latest")
    decisions = {occ_id: decision for occ_id, (decision, _path) in merged.items()}
    print(
        f"\nmerged: {len(decisions)} distinct occurrence_id(s) decided across {len(loaded)} file(s)"
    )

    repeat_lookup: dict[str, Any] = {}
    if REPEAT_LOOKUP_JSON.exists():
        repeat_lookup = json.loads(REPEAT_LOOKUP_JSON.read_text(encoding="utf-8"))["lookup"]

    decisions_out = {
        occ_id: {
            "pair_id": d["pair_id"],
            "label": d["answer"],
            "split": d["split"],
            "tier": d["tier"],
            "source": d["source"],
            "corrected": d["corrected"],
            "ms": d["ms"],
            "decided_at": d["decided_at"],
            # TASK 4 (ADR-0028 addendum #13) -- present only on a review-mode re-decision; a
            # fresh (never-reviewed) decision carries none of these three, same as before.
            **({"revised_from": d["revised_from"]} if "revised_from" in d else {}),
            **({"revised_at": d["revised_at"]} if "revised_at" in d else {}),
            **({"revision_rule": d["revision_rule"]} if "revision_rule" in d else {}),
        }
        for occ_id, d in decisions.items()
    }

    out = {
        "built_from": "scripts/ingest_labels.py, merging tools/annotate.html label exports "
        "against the FROZEN queue + committed split file",
        "queue_sha256": actual_queue_sha256,
        "split_sha256": actual_split_sha256,
        "ingested_at": datetime.now(UTC).isoformat(),
        "source_files": [
            {
                "path": str(export.path.resolve().relative_to(ROOT)).replace("\\", "/")
                if _is_relative(export.path, ROOT)
                else str(export.path),
                "decision_count_in_file": len(export.decisions),
                "exported_at": export.exported_at,
            }
            for export in loaded
        ],
        "decision_count": len(decisions_out),
        "decisions": decisions_out,
    }
    LABELS_JSON.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nwritten: {LABELS_JSON.relative_to(ROOT)} ({len(decisions_out)} decisions)")

    qa_report = build_qa_report(canonical, decisions, loaded, repeat_lookup, revisions)
    date_stamp = datetime.now(UTC).strftime("%Y%m%d")
    qa_path = ROOT / "docs" / "learned" / f"phase3-label-qa-{date_stamp}.md"
    qa_path.write_text(qa_report, encoding="utf-8")
    print(f"written: {qa_path.relative_to(ROOT)}")
    print("\n" + qa_report)

    return 0


def _is_relative(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
