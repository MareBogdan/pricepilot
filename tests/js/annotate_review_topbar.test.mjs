// Defect 2 (ADR-0028 addendum #14): in review mode the header must count EVERY re-decided pair,
// including (a) the last one -- the completion screen replaces the pair view and used to skip
// the topbar refresh -- and (b) a re-decision that keeps the SAME label as the original.
// Drives the real tools/annotate.html script in a vm with a minimal fake DOM.
//   node --test tests/js/annotate_review_topbar.test.mjs
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

async function runReview(pressSequence) {
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
  const ctx = vm.createContext({
    document, console, URLSearchParams, Date, Math, JSON, Map, Set, Promise, Object, Array,
    crypto: globalThis.crypto, TextEncoder,
    location: { search: "?review=docs/learned/FIXTURE-relabel.json" },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    setInterval: () => 0, clearInterval() {}, setTimeout, clearTimeout,
    fetch: async (url) => {
      const u = String(url);
      const body = u.includes("annotation-queue") ? queueText : u.includes("annotation-split") ? splitText : reviewFile;
      return { ok: true, text: async () => body, json: async () => JSON.parse(body) };
    },
    Blob: class {}, URL: { createObjectURL: () => "", revokeObjectURL() {} },
    window: {},
  });
  // Build the review fixture from the page's own occurrence_id derivation: run the script once
  // up to the point queue is loaded is overkill -- instead take the first three occurrence_ids
  // the split file assigns (same set the page derives), and flag them with a prior label "M".
  const split = JSON.parse(splitText);
  const three = Object.keys(split.assignments).slice(0, pressSequence.length);
  reviewFile = JSON.stringify({
    queue_sha256: sha(queueText), split_sha256: sha(splitText),
    flagged: Object.fromEntries(three.map((o) => [o, { label: "M", classes: [{ rule_id: "fixture" }] }])),
  });
  vm.runInContext(script, ctx);
  for (let i = 0; i < 200 && vm.runInContext("order.length", ctx) === 0; i++) await new Promise((r) => setTimeout(r, 10));
  const top = () => ({
    done: elements.get("stat-done").textContent,
    total: elements.get("stat-total").textContent,
    left: elements.get("stat-phase-remaining").textContent,
  });
  const snapshots = [];
  for (const key of pressSequence) {
    listeners.keydown({ key, target: fakeElement(), preventDefault() {}, ctrlKey: false, metaKey: false, altKey: false });
    snapshots.push(top());
  }
  return { snapshots, done: vm.runInContext("cursor >= order.length", ctx) };
}

test("review header counts every re-decision, including a same-label one and the final one", async () => {
  // Original label of every flagged pair is "M": pressing "m" re-decides to the SAME label.
  const { snapshots, done } = await runReview(["n", "m", "n"]);
  assert.deepEqual(snapshots.map((s) => [s.done, s.left]), [[1, 2], [2, 1], [3, 0]]);
  assert.equal(snapshots[2].total, 3);
  assert.ok(done, "completion screen reached");
});

test("review header is correct when the SAME-label re-decision is the last one", async () => {
  const { snapshots } = await runReview(["n", "n", "m"]);
  assert.deepEqual(snapshots.map((s) => [s.done, s.left]), [[1, 2], [2, 1], [3, 0]]);
});
