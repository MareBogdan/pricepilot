// Regression test (ADR-0028 addendum #18): review mode must not treat an occurrence as
// "already re-decided" just because it carries ANY `revised_at`. It must be re-decided under
// THIS review session's own file specifically -- an occurrence revised under an OLDER
// relabel-queue file (a different `generated_at`) carries a stale `revised_at` from a PREVIOUS
// review pass and must be shown again, not silently skipped while still counting toward the
// completion screen. This is exactly what happened to 3f574dad8b6e_b52acad20816_0: it carried
// a `revised_at` from the previous session's review pass, so it was skipped while the
// completion screen still reported "12/12 done".
//   node --test tests/js/annotate_review_stale_revision.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const html = fs.readFileSync(path.join(ROOT, "tools", "annotate.html"), "utf8");
assert.equal(html.split("<script>").length, 2, "expected exactly one inline <script>");
const script = html.slice(html.indexOf("<script>") + 8, html.lastIndexOf("</script>"));
const queueText = fs.readFileSync(path.join(ROOT, "docs/learned/phase3-annotation-queue.json"), "utf8");
const splitText = fs.readFileSync(path.join(ROOT, "docs/learned/phase3-annotation-split.json"), "utf8");
const sha = (t) => crypto.createHash("sha256").update(t).digest("hex");

function fakeElement() {
  const store = { style: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false }, dataset: {} };
  const el = new Proxy(store, {
    get(t, k) {
      if (k in t) return t[k];
      if (k === "querySelector") return () => el;
      if (k === "querySelectorAll") return () => [];
      if (k === "parentElement") return el;
      if (k === "children" || k === "childNodes") return [];
      return () => el; // addEventListener, appendChild, click, ... all no-ops
    },
    set(t, k, v) { t[k] = v; return true; },
  });
  return el;
}

// `staleGeneratedAt` and `currentGeneratedAt` differ -- the occurrence's own prior revision was
// produced under `staleGeneratedAt` (an older review file), while the review file this session
// loads declares `currentGeneratedAt`.
async function runReview({ staleGeneratedAt, currentGeneratedAt, priorState }) {
  const elements = new Map();
  const listeners = {};
  const document = {
    getElementById(id) { if (!elements.has(id)) elements.set(id, fakeElement()); return elements.get(id); },
    querySelector: () => fakeElement(),
    querySelectorAll: () => [],
    createElement: () => fakeElement(),
    createTextNode: () => fakeElement(),
    createDocumentFragment: () => fakeElement(),
    addEventListener(type, fn) { listeners[type] = fn; },
    body: fakeElement(),
  };
  let reviewFile = null;
  let storedState = JSON.stringify(priorState);
  const ctx = vm.createContext({
    document, console, URLSearchParams, Date, Math, JSON, Map, Set, Promise, Object, Array,
    crypto: globalThis.crypto, TextEncoder,
    location: { search: "?review=docs/learned/FIXTURE-relabel.json" },
    localStorage: {
      getItem: (k) => (k === "pricepilot_phase3_annotations_v1" ? storedState : null),
      setItem: (k, v) => { if (k === "pricepilot_phase3_annotations_v1") storedState = v; },
      removeItem() {},
    },
    setInterval: () => 0, clearInterval() {}, setTimeout, clearTimeout,
    fetch: async (url) => {
      const u = String(url);
      const body = u.includes("annotation-queue") ? queueText : u.includes("annotation-split") ? splitText : reviewFile;
      return { ok: true, text: async () => body, json: async () => JSON.parse(body) };
    },
    Blob: class {}, URL: { createObjectURL: () => "", revokeObjectURL() {} },
    window: {},
  });
  const split = JSON.parse(splitText);
  const three = Object.keys(split.assignments).slice(0, 3);
  reviewFile = JSON.stringify({
    generated_at: currentGeneratedAt,
    queue_sha256: sha(queueText), split_sha256: sha(splitText),
    flagged: Object.fromEntries(three.map((o) => [o, { label: "M", classes: [{ rule_id: "fixture" }] }])),
  });
  vm.runInContext(script, ctx);
  for (let i = 0; i < 200 && vm.runInContext("order.length", ctx) === 0; i++) await new Promise((r) => setTimeout(r, 10));
  return {
    occurrenceIds: three,
    doneText: elements.get("stat-done").textContent,
    remainingText: elements.get("stat-phase-remaining").textContent,
    cursorOccId: vm.runInContext("queue[order[cursor]].occurrence_id", ctx),
    firstUnrevisedIdx: vm.runInContext("reviewFirstUnrevisedIndex()", ctx),
  };
}

test("an occurrence revised under an OLDER review file is shown again, not skipped", async () => {
  const currentGeneratedAt = "2026-09-22T08:44:42.706673+00:00";
  const staleGeneratedAt = "2026-09-15T00:00:00.000000+00:00";
  const split = JSON.parse(splitText);
  const [staleOcc] = Object.keys(split.assignments);

  const priorState = {
    [staleOcc]: {
      answer: "M",
      split: "train_val",
      tier: "fixture",
      source: "override",
      revised_at: "2026-09-15T09:00:00.000000+00:00",
      revised_under_review_generated_at: staleGeneratedAt,
      revision_rule: "fixture-old",
    },
  };

  const result = await runReview({ staleGeneratedAt, currentGeneratedAt, priorState });

  // The stale occurrence must NOT count as already re-decided this session: it must still be
  // reachable (cursor lands on it, first-unrevised index points at it) and must not inflate the
  // "done" counter before anything has actually been re-decided in this session.
  assert.equal(result.doneText, 0, "stale revision from an older review file must not count as done");
  assert.equal(result.cursorOccId, result.occurrenceIds[0], "cursor must land on the stale occurrence, not skip past it");
  assert.equal(result.firstUnrevisedIdx, 0, "the stale occurrence's index must be reported as the first unrevised one");
});

test("an occurrence revised under the CURRENT review file still counts as done and is not re-walked", async () => {
  // Guards against an over-correction that made isRevisedUnderCurrentReview() always false
  // (which would also pass the "stale" test above but make review mode un-resumable).
  const currentGeneratedAt = "2026-09-22T08:44:42.706673+00:00";
  const split = JSON.parse(splitText);
  const [firstOcc, secondOcc] = Object.keys(split.assignments);

  const priorState = {
    [firstOcc]: {
      answer: "M",
      split: "train_val",
      tier: "fixture",
      source: "override",
      revised_at: "2026-09-22T09:00:00.000000+00:00",
      revised_under_review_generated_at: currentGeneratedAt,
      revision_rule: "fixture-current",
    },
  };

  const result = await runReview({ staleGeneratedAt: currentGeneratedAt, currentGeneratedAt, priorState });

  assert.equal(result.doneText, 1, "a revision made under the CURRENT review file must count as done");
  assert.notEqual(result.cursorOccId, result.occurrenceIds[0], "cursor must skip the already-done occurrence");
  assert.equal(result.cursorOccId, secondOcc, "cursor must land on the next undone occurrence");
});

test("legacy shape (revised_at with no revised_under_review_generated_at key at all) is re-opened", async () => {
  // This is the actual shape real pre-fix localStorage holds -- a decision made before this fix
  // existed never wrote the new key at all, not merely an old value for it. This is the path the
  // original "12/12" bug actually took; the earlier test sets the key explicitly, which the
  // pre-fix code never wrote.
  const currentGeneratedAt = "2026-09-22T08:44:42.706673+00:00";
  const split = JSON.parse(splitText);
  const [legacyOcc] = Object.keys(split.assignments);

  const priorState = {
    [legacyOcc]: {
      answer: "M",
      split: "train_val",
      tier: "fixture",
      source: "override",
      revised_at: "2026-09-15T09:00:00.000000+00:00",
      revision_rule: "fixture-legacy",
      // no revised_under_review_generated_at key at all
    },
  };

  const result = await runReview({ staleGeneratedAt: currentGeneratedAt, currentGeneratedAt, priorState });

  assert.equal(result.doneText, 0, "a legacy revision with no session-identity key must not count as done");
  assert.equal(result.cursorOccId, legacyOcc, "cursor must land on the legacy occurrence, not skip past it");
});
