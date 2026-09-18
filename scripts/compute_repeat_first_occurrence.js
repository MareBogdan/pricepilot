#!/usr/bin/env node
/**
 * Phase 3 STEP 7, ADR-0028 addendum #12, TASK 2 rule 2 -- for a repeated pair_id (one of the 38
 * that appear twice in the frozen queue, always once as proxy_key_collision and once as
 * trivial_spot_check), the evaluation label used for the headline TEST metric is the FIRST
 * decision in DISPLAY order, not file order or occurrence-id order. This script names which
 * occurrence_id that is, for every one of the 38 pairs.
 *
 * Display order is a stateful, seeded-RNG algorithm (Mulberry32 shuffle, fractional-rank
 * per-tier interleave, then a >=100-position repeat-spacing pass -- TASK 1, ADR-0028 addendum
 * #12) that lives in exactly one place: the <script> body of tools/annotate.html. This script
 * does NOT re-implement that algorithm in Python or a second copy of JS -- a hand-ported
 * duplicate of a stateful RNG-based algorithm is exactly the kind of thing that silently drifts
 * from the original, which is what produced the occurrence_id collision bug in the first place
 * (ADR-0028 addendum #11). Instead it extracts and EXECUTES the real <script> body (Node's `vm`
 * module, DOM-free -- same technique this session used for its own order-verification harness)
 * against the real, committed queue + split files, and reads off which of each repeated pair's
 * two occurrence_ids the resulting order places first.
 *
 *     node scripts/compute_repeat_first_occurrence.js
 *
 * Reads docs/learned/phase3-annotation-queue.json (FROZEN, read-only) and
 * docs/learned/phase3-annotation-split.json (read-only). Writes
 * docs/learned/phase3-repeat-first-occurrence.json. Touches nothing else; starts no annotation.
 *
 * RESIDUAL RISK, found on review, worth stating rather than hiding: this file's own driver
 * (below) re-implements init()'s ORCHESTRATION -- the queue/split merge, the split into a TEST
 * block and a TRAIN_VAL block, and the literal minGap=100 passed to enforceRepeatSpacing() --
 * even though it calls the real buildOrder()/enforceRepeatSpacing()/deriveOccurrenceIds()
 * functions for the ALGORITHM itself. If tools/annotate.html's init() ever changes that
 * orchestration (a different minGap, a different block boundary), this script and the real tool
 * could silently disagree while every existing test still passes, since nothing currently checks
 * this driver's shape against init()'s. Low probability, not fixed here (no test infrastructure
 * change was in scope this session) -- flagged so a future change to init() remembers to check
 * this file too.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.resolve(__dirname, "..");
const HTML_PATH = path.join(ROOT, "tools", "annotate.html");
const QUEUE_PATH = path.join(ROOT, "docs", "learned", "phase3-annotation-queue.json");
const SPLIT_PATH = path.join(ROOT, "docs", "learned", "phase3-annotation-split.json");
const OUT_PATH = path.join(ROOT, "docs", "learned", "phase3-repeat-first-occurrence.json");

const html = fs.readFileSync(HTML_PATH, "utf8");
const scriptMatch = html.match(/<script>([\s\S]*)<\/script>/);
if (!scriptMatch) {
  console.error("could not extract <script> body from tools/annotate.html");
  process.exit(2);
}
const scriptText = scriptMatch[1];

// DOM-free stub -- identical shape to this session's own verification harness. init()'s fetch()
// call rejects immediately and is caught internally by init() itself; none of that matters here,
// since the driver below calls buildOrder()/enforceRepeatSpacing() directly rather than via
// init().
const sandbox = {
  console,
  require,
  process,
  TextEncoder,
  crypto: global.crypto, // Node 19+ built-in Web Crypto (unused by this driver, kept for parity)
  document: {
    getElementById: () => ({
      set innerHTML(_v) {},
      get innerHTML() {
        return "";
      },
      textContent: "",
      style: {},
      classList: { add() {}, remove() {}, toggle() {} },
      addEventListener() {},
      appendChild() {},
    }),
    querySelectorAll: () => [],
    addEventListener() {},
  },
  location: { search: "" },
  fetch: () => Promise.reject(new Error("no network in this script")),
  URLSearchParams,
};
vm.createContext(sandbox);

const driver = `
const fsNode = require("fs");
const cryptoNode = require("crypto");

const queueRaw = fsNode.readFileSync(${JSON.stringify(QUEUE_PATH)}, "utf8");
const splitRaw = fsNode.readFileSync(${JSON.stringify(SPLIT_PATH)}, "utf8");
// Named distinctly from the extracted script's own module-level \`queueSha256\`/\`splitSha256\`
// (FIX 3, label export/import) to avoid a duplicate top-level \`let\`/\`const\` declaration in the
// shared execution scope.
const outQueueSha256 = cryptoNode.createHash("sha256").update(queueRaw).digest("hex");
const outSplitSha256 = cryptoNode.createHash("sha256").update(splitRaw).digest("hex");

const data = JSON.parse(queueRaw);
const splitData = JSON.parse(splitRaw);

queue = data.pairs;
deriveOccurrenceIds(queue);
for (const item of queue) {
  const a = splitData.assignments[item.occurrence_id];
  if (!a) throw new Error("missing split assignment for " + item.occurrence_id);
  item.split = a.split;
  item.engine_prediction = a.split === "train_val" ? (a.engine_prediction || null) : null;
}

const seed = data.shuffle_seed || 20260915;
order = buildOrder(seed); // sets testBlockSize as a side effect
const tb = testBlockSize;
const testBlock = order.slice(0, tb);
const trainValBlock = order.slice(tb);
const spacedTest = enforceRepeatSpacing(testBlock, queue, 100, new Set(testBlock));
const spacedTrainVal = enforceRepeatSpacing(trainValBlock, queue, 100, new Set(trainValBlock));
const finalOrder = spacedTest.concat(spacedTrainVal);

const positionOf = {};
finalOrder.forEach((idx, pos) => { positionOf[queue[idx].occurrence_id] = pos; });

const byPid = {};
queue.forEach((item) => { (byPid[item.pair_id] = byPid[item.pair_id] || []).push(item); });

const lookup = {};
let repeatedCount = 0;
for (const pid of Object.keys(byPid)) {
  const items = byPid[pid];
  if (items.length !== 2) continue;
  repeatedCount += 1;
  const [a, b] = items;
  const posA = positionOf[a.occurrence_id];
  const posB = positionOf[b.occurrence_id];
  const first = posA < posB ? a : b;
  const second = posA < posB ? b : a;
  lookup[pid] = {
    first_occurrence_id: first.occurrence_id,
    first_tier: first.tier,
    first_position: positionOf[first.occurrence_id],
    second_occurrence_id: second.occurrence_id,
    second_tier: second.tier,
    second_position: positionOf[second.occurrence_id],
    split: first.split,
  };
}

if (repeatedCount !== 38) {
  console.error("expected 38 repeated pair_ids, found " + repeatedCount);
  process.exit(1);
}

const out = {
  built_from: "scripts/compute_repeat_first_occurrence.js, executing the REAL " +
    "tools/annotate.html display-order logic (buildOrder + enforceRepeatSpacing) against the " +
    "committed queue+split files -- not a re-implementation, to avoid the two ever silently " +
    "disagreeing (see this file's own module docstring)",
  purpose: "ADR-0028 addendum #12 rule 2: for a repeated pair, the evaluation label is the " +
    "FIRST decision in DISPLAY order, not file order. This file names which occurrence_id that " +
    "is, for each of the 38 repeated pair_ids.",
  queue_sha256: outQueueSha256,
  split_sha256: outSplitSha256,
  shuffle_seed: seed,
  repeat_pair_count: repeatedCount,
  lookup,
};
fsNode.writeFileSync(${JSON.stringify(OUT_PATH)}, JSON.stringify(out, null, 1), "utf8");
console.log("wrote " + ${JSON.stringify(OUT_PATH)} + " (" + repeatedCount + " repeated pairs)");
console.log("queue_sha256=" + outQueueSha256);
console.log("split_sha256=" + outSplitSha256);
`;

vm.runInContext(scriptText + "\n" + driver, sandbox, { filename: "compute-repeat-first-occurrence-driver.js" });
