r"""Phase 3 mechanical rule-consistency check (DECISIONS.md ADR-0028 addendum #13) -- reads the
FROZEN queue + committed split + the ingested `docs/learned/phase3-labels.json` and flags every
DECIDED pair whose label contradicts a PURELY MECHANICAL rule of
`docs/learned/phase3-annotation-conventions.md` (revision 4). No judgement calls, no "looks
wrong" -- only the five classes below, each cheap enough to check with a plain field comparison:

    uv run python scripts/check_label_rule_consistency.py

  (a) rule 2   -- quantity tuple (net_weight_g/net_volume_ml, pack_count null==1, bonus_weight_g
                  null==0) differs between the two listings, but the label is `M`.
  (b) rule 1   -- both listings' `species` field is known and they differ, but the label is `M`.
  (c) rule 3b  -- both listings state a `food_form` and one is `dry` while the other is
                  `wet`/`tin`/`pouch`, but the label is `M`.
  (d) tier     -- a `trivial_spot_check` tier pair (built to be a trivially-obvious repeat of a
                  `proxy_key_collision` pair -- see `scripts/build_annotation_queue.py`) labelled
                  anything other than `M`.
  (e) data quality, reported SEPARATELY and NEVER as an annotator error -- a listing whose title
                  clearly states one species ("pentru pisici", "caini", ...) while its stored
                  `species` field says the other. This is a `normalize/species.py` extraction
                  defect, not a labelling mistake: the annotator reading the real title got it
                  right; the structured field is what is wrong. (One flagged pair overlaps class
                  (b) for exactly this reason -- see the printed note when it happens.)

  (f) self-agreement -- a pair shown twice (38 pair_ids repeat in the queue) whose two occurrences
                  were labelled DIFFERENTLY. Not a rule violation: the annotator must pick one label
                  per pair before the dataset is used for training. Reported with
                  `self_agreement: true` / `data_quality_only: false`.

Class (e) entries carry `revert_hint: true`: the flagged field is a stored-data defect, so a flag
of this class NEVER supports changing a label, and any label revision that rested on the stored
field instead of the title text should be reverted (see ARCHITECT_NOTES).

Exits non-zero if any class is non-empty (each is a real, actionable finding on a supposedly
mechanical rule -- there is no clean pass with a non-zero count here). Writes every flagged
occurrence_id, with its class and the rule/check that flagged it, to
`docs/learned/phase3-relabel-queue.json` -- the only input `tools/annotate.html`'s review mode
(`?review=docs/learned/phase3-relabel-queue.json`) reads. This script never edits
`phase3-labels.json` itself and never assigns a corrected label -- relabelling is a human decision,
made through the tool's review mode, never by a script.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    if isinstance(_stream, io.TextIOWrapper):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from pricepilot.normalize.species import _from_title  # noqa: E402

QUEUE_JSON = ROOT / "docs" / "learned" / "phase3-annotation-queue.json"
SPLIT_JSON = ROOT / "docs" / "learned" / "phase3-annotation-split.json"
LABELS_JSON = ROOT / "docs" / "learned" / "phase3-labels.json"
RELABEL_QUEUE_JSON = ROOT / "docs" / "learned" / "phase3-relabel-queue.json"


def sha256_lf(data: bytes) -> str:
    """CRLF->LF before hashing, so a Windows worktree (CRLF) and a Linux checkout (`.gitattributes`
    normalises to LF -- Kaggle, the Phase 7 VPS, CI if it ever runs this checker) agree on the same
    file's hash. Used for every guard/traceability hash in this module and in
    scripts/freeze_labels.py (via `clc.sha256_lf`) -- never hash committed JSON raw for a guard."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


# Same constant as scripts/split_annotation_queue.py, scripts/ingest_labels.py,
# tests/test_annotation_split.py -- the value recorded the moment the queue was frozen.
# This is the LF-NORMALISED hash (differs from those other files' raw-CRLF constant of the same
# name -- see DECISIONS.md ADR-0028 addendum #16 for why this module's guard was moved to LF and
# the others were not touched in this session).
FROZEN_QUEUE_SHA256 = "7da125e1856bc65514234d516e17d0a12363ee6ada9b324b3f00ca8bfa146d2a"

_WET_FOOD_FORMS = frozenset({"wet", "tin", "pouch"})

CLASS_LABELS = {
    "a": "rule2_quantity_differs -- quantity tuple differs but label is M",
    "b": "rule1_species_differs -- species differs (both known) but label is M",
    "c": "rule3b_foodform_dry_vs_wet -- dry vs wet/tin/pouch (both stated) but label is M",
    "d": "trivial_spot_check tier labelled something other than M",
    "e": "data quality -- title states one species, species field says the other (NOT an "
    "annotator error)",
    "f": "self_agreement -- the same pair was labelled differently on its two occurrences "
    "(annotator must pick one label per pair)",
}

# Curated, per-occurrence reasoning recorded by the architect -- shown prominently in the tool's
# review screen. Attaches only when the occurrence is actually flagged.
ARCHITECT_NOTES = {
    "3f574dad8b6e_b52acad20816_0": (
        "Revised M->N in the review pass under rule1_species_differs. That revision was WRONG: "
        "conventions rule 1 reads the TITLE, not the `species` field. Both titles state 'pisici' "
        "(cat); the left listing's stored species='dog' is the known normalize/species.py defect. "
        "Same brand, same line, both 40 g, both wet-family. Re-decide on the titles."
    ),
}

_TIER_FIELDS = (
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
    "species",
    "breed_size_class",
)


def _field_diff(left: dict[str, Any], right: dict[str, Any]) -> str:
    diffs = [
        f"{f}: {left.get(f)!r} vs {right.get(f)!r}"
        for f in _TIER_FIELDS
        if left.get(f) != right.get(f)
    ]
    return "; ".join(diffs) if diffs else "no extracted field differs"


def derive_occurrence_ids(pairs: list[dict[str, Any]]) -> list[str]:
    """Same rule as build_annotation_queue.py/split_annotation_queue.py/annotate.html/
    ingest_labels.py -- duplicated here deliberately, same discipline as those files."""
    counts: dict[str, int] = {}
    ids = []
    for p in pairs:
        pid = p["pair_id"]
        k = counts.get(pid, 0)
        ids.append(f"{pid}_{k}")
        counts[pid] = k + 1
    return ids


def _quantity_tuple(listing: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    pack = listing["pack_count"] if listing["pack_count"] is not None else 1
    bonus = listing["bonus_weight_g"] if listing["bonus_weight_g"] is not None else 0
    return (listing["net_weight_g"], listing["net_volume_ml"], pack, bonus)


@dataclass
class Flag:
    occurrence_id: str
    pair_id: str
    cls: str
    rule_id: str
    label: str
    left_title: str
    right_title: str
    note: str | None = None
    revert_hint: bool = False
    self_agreement: bool = False


def check(
    pairs_by_occ: dict[str, dict[str, Any]], decisions: dict[str, dict[str, Any]]
) -> list[Flag]:
    flags: list[Flag] = []
    seen_species_mismatch_hashes: set[str] = set()

    for occ_id, dec in decisions.items():
        pair = pairs_by_occ.get(occ_id)
        if pair is None:
            continue  # a decision for an occurrence_id the current queue doesn't have; not this
            # script's job to diagnose queue/labels drift, only rule-vs-label consistency
        left, right = pair["left"], pair["right"]
        label = dec["label"]
        pair_id = pair["pair_id"]

        if _quantity_tuple(left) != _quantity_tuple(right) and label == "M":
            flags.append(
                Flag(
                    occ_id,
                    pair_id,
                    "a",
                    "rule2_quantity_differs",
                    label,
                    left["title"],
                    right["title"],
                )
            )

        l_species, r_species = left.get("species"), right.get("species")
        if l_species and r_species and l_species != r_species and label == "M":
            flags.append(
                Flag(
                    occ_id,
                    pair_id,
                    "b",
                    "rule1_species_differs",
                    label,
                    left["title"],
                    right["title"],
                )
            )

        l_form, r_form = left.get("food_form"), right.get("food_form")
        if l_form and r_form and (l_form == "dry") != (r_form == "dry") and label == "M":
            flags.append(
                Flag(
                    occ_id,
                    pair_id,
                    "c",
                    "rule3b_foodform_dry_vs_wet",
                    label,
                    left["title"],
                    right["title"],
                )
            )

        if pair["tier"] == "trivial_spot_check" and label != "M":
            flags.append(
                Flag(
                    occ_id,
                    pair_id,
                    "d",
                    "trivial_spot_check_not_M",
                    label,
                    left["title"],
                    right["title"],
                    note=f"differing extracted fields -- {_field_diff(left, right)}",
                )
            )

        for side_name, listing in (("left", left), ("right", right)):
            content_hash = listing["content_hash"]
            title_species = _from_title(listing["title"])
            field_species = listing.get("species")
            if (
                title_species
                and field_species
                and title_species != field_species
                and content_hash not in seen_species_mismatch_hashes
            ):
                seen_species_mismatch_hashes.add(content_hash)
                flags.append(
                    Flag(
                        occ_id,
                        pair_id,
                        "e",
                        "species_title_field_mismatch",
                        label,
                        left["title"],
                        right["title"],
                        revert_hint=True,
                        note=(
                            f"{side_name} listing: title says {title_species!r}, stored species "
                            f"field says {field_species!r} -- this is a normalize/species.py "
                            f"extraction defect, never a labelling error"
                        ),
                    )
                )

    # (f) self-agreement: same pair_id, differing labels across occurrences.
    by_pair: dict[str, list[str]] = {}
    for occ_id in decisions:
        if occ_id in pairs_by_occ:
            by_pair.setdefault(pairs_by_occ[occ_id]["pair_id"], []).append(occ_id)
    for pair_id, occs in by_pair.items():
        labels = {o: decisions[o]["label"] for o in occs}
        if len(occs) > 1 and len(set(labels.values())) > 1:
            for o in occs:
                pair = pairs_by_occ[o]
                others = ", ".join(f"{k}={v}" for k, v in labels.items() if k != o)
                flags.append(
                    Flag(
                        o,
                        pair_id,
                        "f",
                        "self_agreement_disagreement",
                        labels[o],
                        pair["left"]["title"],
                        pair["right"]["title"],
                        note=f"other occurrence(s) of this pair: {others}",
                        self_agreement=True,
                    )
                )

    return flags


@dataclass
class FoodFormDiagnostic:
    both_stated_and_differ: int = 0
    dry_vs_wet: int = 0
    dry_vs_wet_already_n: int = 0
    dry_vs_wet_was_m: int = 0
    wet_family_only: int = 0


def food_form_diagnostic(
    pairs_by_occ: dict[str, dict[str, Any]], decisions: dict[str, dict[str, Any]]
) -> FoodFormDiagnostic:
    """Review finding (ADR-0028 addendum #13): the conventions revision-4 write-up and DECISIONS.md
    both state "37 of 300 TEST pairs have food_form stated on both sides and differing; 7 are
    dry-vs-wet, of which 6 were already N; the remaining 30 are wet-family-only" -- a real number
    that had no script behind it (CLAUDE.md §0.4/§9). This reproduces it directly from the same
    `decisions`/`pairs_by_occ` data `check()` uses, so every count in the docs traces back to
    `uv run python scripts/check_label_rule_consistency.py`'s own output, not a one-off query."""
    d = FoodFormDiagnostic()
    for occ_id, dec in decisions.items():
        pair = pairs_by_occ.get(occ_id)
        if pair is None:
            continue
        left, right = pair["left"], pair["right"]
        l_form, r_form = left.get("food_form"), right.get("food_form")
        if not (l_form and r_form) or l_form == r_form:
            continue
        d.both_stated_and_differ += 1
        if (l_form == "dry") != (r_form == "dry"):
            d.dry_vs_wet += 1
            if dec["label"] == "M":
                d.dry_vs_wet_was_m += 1
            else:
                d.dry_vs_wet_already_n += 1
        else:
            d.wet_family_only += 1
    return d


def main() -> int:
    if not QUEUE_JSON.exists():
        print(f"frozen queue not found: {QUEUE_JSON}", file=sys.stderr)
        return 2
    if not LABELS_JSON.exists():
        print(
            f"no labels ingested yet: {LABELS_JSON} -- run scripts/ingest_labels.py first",
            file=sys.stderr,
        )
        return 2

    queue_raw = QUEUE_JSON.read_bytes()
    queue_sha256_raw = hashlib.sha256(queue_raw).hexdigest()
    queue_sha256_lf = sha256_lf(queue_raw)
    print(f"frozen queue SHA-256 (raw): {queue_sha256_raw}")
    print(f"frozen queue SHA-256 (LF):  {queue_sha256_lf}")
    if queue_sha256_lf != FROZEN_QUEUE_SHA256:
        print(
            f"REFUSING TO RUN: frozen queue hash (LF-normalised) does not match the recorded "
            f"value ({FROZEN_QUEUE_SHA256}). Investigate before checking labels against data this "
            f"script was not written against.",
            file=sys.stderr,
        )
        return 1
    # kept for backward compatibility with callers that pass this hash on -- see below
    actual_queue_sha256 = queue_sha256_raw

    if SPLIT_JSON.exists():
        split_raw = SPLIT_JSON.read_bytes()
        split_sha256_raw = hashlib.sha256(split_raw).hexdigest()
        split_sha256_lf = sha256_lf(split_raw)
    else:
        split_sha256_raw = None
        split_sha256_lf = None
    print(f"split file SHA-256 (raw): {split_sha256_raw}")
    print(f"split file SHA-256 (LF):  {split_sha256_lf}")
    # kept for backward compatibility with callers that read this key
    split_sha256 = split_sha256_raw

    queue = json.loads(queue_raw.decode("utf-8"))
    pairs = queue["pairs"]
    occurrence_ids = derive_occurrence_ids(pairs)
    pairs_by_occ = dict(zip(occurrence_ids, pairs, strict=True))

    labels_data = json.loads(LABELS_JSON.read_text(encoding="utf-8"))
    decisions = labels_data["decisions"]
    print(f"decided occurrence_ids: {len(decisions)}")

    flags = check(pairs_by_occ, decisions)

    class_counts = {c: 0 for c in CLASS_LABELS}
    for f in flags:
        class_counts[f.cls] += 1

    print("\n" + "=" * 90)
    print("MECHANICAL RULE-CONSISTENCY CHECK")
    print("=" * 90)
    for cls, desc in CLASS_LABELS.items():
        print(f"  ({cls}) {class_counts[cls]:3d}  {desc}")
    print("=" * 90)

    for f in flags:
        print(
            f"\n[{f.cls}] {f.occurrence_id} (pair_id={f.pair_id}) label={f.label} rule={f.rule_id}"
        )
        print(f"    L: {f.left_title}")
        print(f"    R: {f.right_title}")
        if f.note:
            print(f"    note: {f.note}")

    total_flagged = len(flags)
    print(f"\ntotal flagged: {total_flagged}")

    ffd = food_form_diagnostic(pairs_by_occ, decisions)
    print("\n" + "=" * 90)
    print("FOOD FORM DIAGNOSTIC (informational only -- not a flagged class, not a gate)")
    print("=" * 90)
    print(
        f"  pairs with food_form stated on both sides and differing: {ffd.both_stated_and_differ}"
    )
    print(f"    dry vs wet/tin/pouch:      {ffd.dry_vs_wet}")
    print(f"      already N (unrelated rule): {ffd.dry_vs_wet_already_n}")
    print(f"      was M (class (c) above):    {ffd.dry_vs_wet_was_m}")
    print(f"    wet-family-only (correctly unaffected by rule 3b): {ffd.wet_family_only}")
    print("=" * 90)

    # Grouped by occurrence_id -- one occurrence can trigger more than one class (e.g. a species
    # extraction defect, class (e), on a pair that class (b) also flags for the same underlying
    # reason). `tools/annotate.html`'s review mode walks OCCURRENCE_IDs, so each one appears once,
    # carrying every class/rule that fired for it.
    by_occ: dict[str, list[Flag]] = {}
    for f in flags:
        by_occ.setdefault(f.occurrence_id, []).append(f)

    relabel_queue = {
        "built_from": "scripts/check_label_rule_consistency.py",
        "generated_at": datetime.now(UTC).isoformat(),
        # "queue_sha256"/"split_sha256" (raw) kept for existing consumers (tools/annotate.html's
        # review mode compares these against its own in-browser hash of the same checkout, where
        # raw and LF never diverge). "_raw"/"_lf" are the explicit, traceable pair added this
        # session (DECISIONS.md ADR-0028 addendum #16) -- the LF value is what the frozen-queue
        # guard above actually checks.
        "queue_sha256": actual_queue_sha256,
        "queue_sha256_raw": queue_sha256_raw,
        "queue_sha256_lf": queue_sha256_lf,
        "split_sha256": split_sha256,
        "split_sha256_raw": split_sha256_raw,
        "split_sha256_lf": split_sha256_lf,
        "labels_ingested_at": labels_data.get("ingested_at"),
        "class_legend": CLASS_LABELS,
        "class_counts": class_counts,
        "flagged_count": total_flagged,
        "flagged_occurrence_count": len(by_occ),
        "food_form_diagnostic": {
            "both_stated_and_differ": ffd.both_stated_and_differ,
            "dry_vs_wet": ffd.dry_vs_wet,
            "dry_vs_wet_already_n": ffd.dry_vs_wet_already_n,
            "dry_vs_wet_was_m": ffd.dry_vs_wet_was_m,
            "wet_family_only": ffd.wet_family_only,
        },
        "flagged": {
            occ_id: {
                "pair_id": fs[0].pair_id,
                "label": fs[0].label,
                "left_title": fs[0].left_title,
                "right_title": fs[0].right_title,
                "classes": [
                    {
                        "class": f.cls,
                        "rule_id": f.rule_id,
                        "note": f.note,
                        **({"revert_hint": True} if f.revert_hint else {}),
                    }
                    for f in fs
                ],
                "class_note": ARCHITECT_NOTES.get(occ_id),
                "self_agreement": any(f.self_agreement for f in fs),
                # TASK 4 / review finding #9 -- class (e) is a data-quality finding, NEVER an
                # annotator error (module docstring). `data_quality_only: true` tells
                # tools/annotate.html's review mode to soften its banner wording for an
                # occurrence_id flagged SOLELY by class (e), so the annotator isn't invited to
                # "fix" a label that was already correct.
                "data_quality_only": all(f.cls == "e" for f in fs),
            }
            for occ_id, fs in by_occ.items()
        },
    }
    RELABEL_QUEUE_JSON.write_text(
        json.dumps(relabel_queue, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"\nwritten: {RELABEL_QUEUE_JSON.relative_to(ROOT)} "
        f"({total_flagged} flag(s) across {len(by_occ)} distinct occurrence_id(s))"
    )

    return 1 if total_flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
