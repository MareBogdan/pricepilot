# PricePilot — Competitive Pricing Intelligence

> **This file is the single source of truth for this project.**
> Claude Code loads it automatically at the start of every session. Read it fully before doing anything.

---

## 0. Non-negotiable rules

Read these first. They override anything else in this file.

1. **Always respond in English.** The user may write in Romanian or English. Regardless of the input language, every reply, commit message, comment, document and identifier you produce is in English. Do not switch languages, do not ask about it.
2. **Work autonomously by default.** Do not ask for approval on ordinary implementation. Ask only for the four things listed in §4 under "When to stop and ask".
3. **Never spend money without asking.** Any code path that hits a paid API (LLM calls, GPU rental, proxy services) must be opt-in, capped, and approved in advance. See §5.
4. **Never invent a number.** Any metric that appears in README, docs, or conversation must be produced by a script inside this repo and reproducible with one command. If a number is an estimate, label it `ESTIMATE`.
5. **Never put secrets in the repo.** `.env` only, `.env.example` committed, `.gitignore` from day one.
6. **Never auto-deploy.** Deployment is always a manual step the user runs.
7. **Explain before you build.** See §3 — this project is also a learning exercise.

---

## 1. What this project is

A production system that tracks competitor prices for an e-commerce catalogue, automatically determines which competitor listing corresponds to which of our products, estimates how demand responds to price changes, and recommends a new price with a written justification and a hard margin floor.

**Purpose:** a portfolio project demonstrating AI/ML engineering competence for junior-to-mid AI Engineer roles. It must end up publicly deployed and demonstrable in a browser.

**The three capabilities it must prove:**
- **RAG** over business data (pricing policy, product specs) — with correct architectural judgement about when *not* to use RAG
- **Fine-tuning** an open-source LLM on a dataset built from real collected data, beating a documented baseline
- **Full production deployment** — Docker, FastAPI, cloud, monitoring, CI

**Explicitly out of scope for v1:** multi-tenant SaaS, authentication beyond a single admin user, mobile app, real integration with a live store's API (simulate it).

---

## 2. Who you are working with

The user is a master's student in E-Business with a bachelor's in Economic Informatics, working as a developer. Strong in TypeScript/JavaScript, React, React Native, Node.js, SQL, Python. Has built and shipped production scraping pipelines before.

**Weaker / new territory — go slower and explain more here:**
- PyTorch and model training
- Fine-tuning workflows (LoRA/QLoRA, datasets, evaluation)
- Embeddings, vector search, RAG architecture
- MLOps: experiment tracking, drift monitoring

**How to communicate with him:**
- Direct and concrete. No abstract preamble.
- Step-by-step instructions, not essays.
- When you need a decision, give 2–3 named options with a recommendation, not an open question.
- He often writes long messages in Romanian because it's faster for him. Read them, answer in English.
- He will push back if a response is too long or too vague. Prefer short and specific.

---

## 3. Teaching requirement

For every piece of work that touches **RAG, embeddings, fine-tuning, model evaluation, or PyTorch**, you must, before writing code:

1. Explain what the component does and why it's needed here, in plain language, in under 200 words
2. Explain the key design choice and what the realistic alternatives are
3. Name the failure mode — what goes wrong if this is done naively
4. Then write the code, with comments on the non-obvious lines

After implementing, write a short `docs/learned/<topic>.md` capturing what was decided and why. These files are for the user's own understanding and for interview preparation. Keep them under 300 words each.

For ordinary application code (CRUD, API endpoints, Docker config), skip this — just build it.

---

## 4. Working protocol

### Session start
1. Read `STATE.md` (created in Phase 0) to see where the project stands
2. State in one or two lines what phase we're in and what the next concrete task is
3. Wait for direction

### For any non-trivial task
```
AUDIT → BUILD → VERIFY → REPORT → UPDATE STATE
```

Decision rules and thresholds are written and committed before the numbers they judge exist.

- **AUDIT** — read the relevant existing code and docs. Know what exists before adding to it. Do not assume.
- **BUILD** — implement it. Small commits, one logical change each. Do not ask permission.
- **VERIFY** — run the tests, run the code, show real output. Never report something as working without having executed it. If it fails, fix it and run again before reporting.
- **REPORT** — a short summary of what changed and anything the user should know. Not a transcript.
- **UPDATE STATE** — append to `STATE.md`; log architectural choices in `DECISIONS.md` as short ADRs (context, decision, alternatives rejected).

### When to stop and ask

Only these four. Everything else, proceed.

1. **Architecture and product behaviour** — data model changes, what the system actually does, anything that would be hard to reverse later
2. **Money** — see §5. Always `SPEND: <action> — est. $X.XX — proceed?`
3. **Destructive or external actions** — dropping tables, force-push, deleting data, deploying, hitting a live third-party site outside fixtures
4. **A real fork in the road** — when two approaches have genuinely different consequences and you cannot pick on technical grounds alone

When you do ask: 2–3 named options, one-line trade-off each, your recommendation, and a default you will take if the user just says "go".

### Teach-back checkpoints

These replace approval gates on the AI work. When a RAG, embedding, fine-tuning, evaluation or PyTorch component is **finished and verified**, stop and explain it before moving on:

- what you built and how it works, in plain language
- the one design decision that mattered and why you chose it
- what would break it, and how you would notice
- the actual numbers you measured

Keep it under 300 words in chat, and write the longer version to `docs/learned/<topic>.md`. Then continue. Do not wait for a reply unless you asked a §4 question.

The user wants to understand this material well enough to defend it in a job interview. Assume every explanation will be repeated to an interviewer.

### End every response with this block

No exceptions, including short answers and error messages. Keep it tight — one line each, no padding.

```
── NEXT ──
Now:     <the single next action, concrete enough to start>
Then:    <what follows it>
Watch:   <anything broken, risky, skipped, or owed — or "nothing">
Needs you: <a decision or manual step only Bogdan can do — or "nothing">
```

`Watch` is where you are honest. Tests you skipped, a hack you left in, a number you have not verified, a gate you passed loosely. If there is nothing, say nothing — do not invent concerns to fill the line.

### Model and effort policy
The user is on a Pro plan and is budget-conscious with tokens.

- **Sonnet is the default.** From Phase 1 onward, implementation runs on Sonnet unless the session
  is explicitly one of the Opus cases below. If you are on Opus and the work in front of you is
  ordinary implementation, say so and ask the user to switch (`/model sonnet`) before continuing.
- Use **Opus** for: phase audits, architecture decisions, debugging hard problems, reviewing the fine-tuning setup
- Use **Sonnet** for: everything else — implementation, tests, docs, refactoring
- **Do not use maximum effort/thinking settings.** Standard reasoning is sufficient for this work.
- Prefer reading a specific file over searching broadly. Prefer `rg` over reading whole directories.
- Do not re-read files already in context.
- Keep replies short. Long explanations go into `docs/`, not into chat.

### Sub-agents
**The main session is the orchestrator and does most of the implementation itself.** Sub-agents fragment context and cost more tokens; they earn their keep only on genuinely isolated, repetitive or high-volume work.

| Agent | Use it for | Why it's isolated |
|---|---|---|
| `reviewer` | Reviewing a diff against §0 and §6 before merge | Needs a fresh perspective, not the context that produced the code |
| `researcher` | Investigating an option and writing a doc | High token volume, single-document output |

`scraper-engineer` retired after Phase 1 (archived in `docs/archive/agents/`).

Do not create more agents. Do not delegate core ML, RAG or decision-engine work — that stays in the main session, because those decisions need full project context and are what the user most needs explained.

---

## 5. Cost discipline — read this before writing any scraper or LLM call

This is the part where money gets wasted. Treat it as a hard engineering constraint.

### Scrapers
1. Fixtures only: first run saves raw HTML to `tests/fixtures/<source>/`; all later dev and tests run offline against those fixtures — never a live site in a loop.
2. Every scraper has `--limit` (default 5) and `--dry-run` (parses/prints, writes nothing).
3. Rate limit ≥2s randomized, respect `robots.txt`, honest User-Agent read from `SCRAPER_USER_AGENT` in `.env` (never a hardcoded or committed contact address — fails loudly at startup if unset).
4. Self-hosted HTTP first (`httpx` + `selectolax`); Playwright only when a site genuinely requires JS; paid scraping services only with explicit approval.
5. Every run logs to `scrape_runs` (source, items, errors, duration); a >40% item-count drop vs. the previous run raises an alert instead of silently ingesting.
Full text (rationale, examples): `docs/archive/claude-md-condensed-sections.md`.

### LLM API calls
1. **Cache by content hash.** Attribute extraction runs once per unique normalized title, never per scrape run. The price changes daily; the title almost never does. Re-extracting on every run multiplies cost by the number of days. This is the single largest cost risk in the project.
2. Use the cheapest capable model for bulk work. Escalate only where quality demonstrably fails.
3. Use prompt caching for the system prompt, and batch processing where latency doesn't matter.
4. Every LLM call goes through **one wrapper module** (`src/pricepilot/llm/client.py`) which logs model, input tokens, output tokens and computed cost to a `llm_calls` table. No direct SDK calls anywhere else in the codebase.
5. Implement a hard spend cap in that wrapper, read from `LLM_BUDGET_USD` in `.env`. On exceeding it, raise — never degrade silently.
6. Before any batch job over 500 calls, print an estimate and require confirmation.
7. `make cost` prints spend to date, broken down by phase and model.

### GPU / training
Fine-tuning runs on rented GPU by the hour. Before any training run: state the expected duration and cost, and confirm the dataset and eval harness are ready. Never start a run "to see what happens".

### Spend schedule

Ceiling **$100**; **$20 available**; spent **$1.22 to date** (`docs/COSTS.md`). Reserved in priority order — the deliverable is a public demo, hosting makes it visible:

| Priority | What | Reserve | Approval |
|---|---|---|---|
| **1** | VPS hosting, three months | **~$23 (ESTIMATE, ADR-0030)** | yes, once, at Phase 7 — CX23 pricing per `docs/phase3-serving-prices.md`; shortfall vs. available is a Phase 7 decision |
| **2** | Recommendation generation, Phase 5 | ~$2 (ESTIMATE) | yes |

Phases 0, 1, 4 cost $0. Announce cost first: `SPEND: <action> — est. $X.XX — proceed?`; report actual vs. estimated in `docs/COSTS.md`, same commit. Full text (week-5 GPU decision, smoke-run rationale): `docs/archive/claude-md-condensed-sections.md`.

---

## 6. Architecture

```
[0] MOCK STORE      our catalogue + price/sales history + price-update API
[1] COLLECTION      scrapers → raw_listings (price, title, url, timestamp)
[2] NORMALIZATION   clean titles, extract attributes, dedup → norm_listings
[3] MATCHING        embeddings → candidates → fine-tuned model → product_links
[4] DEMAND          PyTorch model: price history → demand estimate
[5] DECISION        RAG over pricing policy + LLM → recommendation + rationale
[6] ACTION          tool calling → apply price (human approval by default)
[7] SURFACE         FastAPI + dashboard + monitoring
```

### Stack
- Python 3.11+, FastAPI, Pydantic v2
- PostgreSQL + pgvector, Alembic migrations
- `httpx` + `selectolax`; Playwright only where required
- `sentence-transformers` for embeddings (local, free)
- PyTorch for the demand model
- PEFT / Unsloth for LoRA fine-tuning
- Docker + docker-compose; GitHub Actions for CI
- Frontend: Next.js + Tailwind (the user is strong here — keep it minimal, it is not the point of the project)

**Deployment target (decided):** a single Hetzner CX23-class VPS (4 GB RAM; plan and reserve re-checked at Phase 7, ADR-0030), Docker Compose, **Caddy** as reverse proxy for automatic HTTPS. Not Kubernetes, not a PaaS. The user has not deployed to a VPS before — explain each step: SSH keys, firewall, domain DNS, systemd unit, backups.

**Model serving (decided, ADR-0030):** the fine-tuned cross-encoder (mMiniLMv2, ONNX fp32, threshold 0.89) runs on CPU on the VPS as an **incremental batch** after each daily collection run, scoring only new/changed `content_hash` pairs; K=100 candidates, at most one match per (our product, competitor shop), highest score wins. The full re-match (first deployment, model change) runs off the VPS on Kaggle CPU with the same ONNX file. The fine-tuned LoRA LLM tied on F1 but is 26x slower: a result, not a served component. Precision at K=100 is unmeasured until the Phase 7 hand-verified sample.

### Hard architectural rules
1. **Numbers come from SQL, not from RAG.** Costs, margins, prices, inventory counts are queried. RAG is only for policy text and unstructured documents. Retrieving a number by semantic similarity is a bug, and an interviewer will spot it.
2. **Guardrails live in code, not in prompts.** The margin floor is a Python `if` statement executed after the LLM responds. A prompt is a suggestion; code is a rule.
3. **Test splits are at product level, not pair level.** Otherwise the same product appears in train and test and every metric is inflated. This is the most common way these projects become worthless.
4. **A baseline exists before any fine-tuning.** Without it there is nothing to compare against and the fine-tuning has no demonstrated value.
5. **Small fine-tuned model for the narrow repetitive task** (matching), large API model only for generating the final explanation. This cost argument is a central selling point of the project.
6. **Every LLM decision is traced** — input context, output, latency, cost, stored and inspectable.

---

## 7. Phases

Each phase has an exit gate. Do not start the next phase until the gate is met and `STATE.md` records it.

### Phase 0 — Foundation
CLOSED 2026-09-12, all 8 gate boxes met (Docker compose up, migration applied, pgvector live, `/health` ok, mock-store seeded, `make test`/`make lint` clean, $0 spent). Full text: `docs/archive/phases-0-2.md`.

### Phase 1 — Collection
CLOSED 2026-09-22, gate MET: ≥3,000 in-scope listings, ≥3 sources (18,585/18,703, petmax non-Shopify); ≥7 consecutive days (9 days, 09-13→09-21); ≥400 cross-shop overlap (hand-verified sample, point 1,214–1,342, ADR-0023/ADR-0028 addendum #7). Full text: `docs/archive/phases-0-2.md`.

### Phase 2 — Normalization
CLOSED 2026-09-14, gate MET: 93.2% attribute accuracy (261/280 symmetric, brand excluded) vs. the 85% target; weight parsing 100% (82/82); cache proof shown. Full text: `docs/archive/phases-0-2.md`.

### Phase 3 — Matching
CLOSED 2026-09-25, gate MET as a **TIE on F1** (fine-tuned 0.5B LoRA 0.8796 vs fine-tuned cross-encoder 0.8737, McNemar p=1.0000). Served model: the cross-encoder, ONNX fp32 on CPU, threshold 0.89, incremental batch after each daily collection run (ADR-0030). LoRA int8 had no eligible config (protocol 5.11); its fp32 fallback scores 0.8750. Full text: `docs/archive/phases-3.md`; audit: `docs/audits/phase3-audit.md`.

### Phase 4 — Demand model (PyTorch)

**Price history is real, sales are synthetic.** By the time you reach this phase, Phase 1 will have collected weeks of genuine daily prices, plus promotion events visible through `compare_at_price`. Use that as the real backbone: actual price levels, actual competitor moves, actual discount timing. Generate only the sales series on top of it, with category-varying elasticity, weekly seasonality, noise and psychological price thresholds.

This matters for how you report it. "Real price and promotion history from N shops over M weeks; sales simulated on top because no retailer shares that data" is a defensible methodology. "Everything is synthetic" is not. State the split explicitly in the README and in `docs/learned/demand-model.md`.

**The circularity trap, and the rule that avoids it.**

The mock store's 180 days of price and sales history were generated from a planted elasticity
constant. A model trained on that data and then measured against that constant is measuring nothing:
it recovers a number that was put there by hand, and calling that a result is a fabricated claim.
`make status` will not catch it, an interviewer will.

Three rules, binding:

1. **Real collected history is the backbone.** Once Phase 1 has genuine daily price observations,
   those are the price series the demand model consumes. The mock store's 180 days are **bootstrap
   only** — they exist to let the code be written and tested before enough real history accumulates,
   and they are labelled as such wherever they appear.
2. **Never report "recovered the planted elasticity" as a result.** Not in the README, not in
   `docs/learned/`, not in conversation. It is a self-test of the generator, and at most it belongs
   in a unit test asserting the training loop is not broken — never in a results table.
3. **Grade only against a naive baseline, on real observed price movements.** The comparison is
   MAE/MAPE versus a naive 7-day-average forecast, evaluated on periods where the price actually
   moved in the collected data. A model that only beats the baseline on flat stretches has learned
   nothing about price response.

The README must state plainly which parts of this phase are real and which are simulated — real
prices, real promotions, real competitor moves; simulated sales volumes — in the same table as the
numbers, not in a footnote.

MLP or GRU — no transformer needed. Compare against a naive 7-day-average baseline. Report MAE/MAPE. Derive elasticity per category, and label every derived elasticity as an estimate from simulated volumes.

**Gate:** beats the naive baseline on validation, measured on real observed price movements; prediction-vs-actual plot committed; the real/synthetic split stated in the README and in `docs/learned/demand-model.md`; no elasticity-recovery number reported as a result anywhere.

### Phase 5 — Decision engine
CLOSED 2026-10-07, gate MET with caveats: 50 real recommendations, 0 margin violations (38 APPROVE / 12 FLAG; 10 APPROVEs move the price, 6 of them labelled guard stress-tests on synthetic competitor prices); the floor is shown entirely by the guard's tests and sweeps, not by the live rows. Spend $0.40 on the gate runs. Full text: `docs/archive/phases-5.md`; report: `docs/learned/results/phase5/fifty-recommendations.md`.

### Phase 6 — Tool calling
CLOSED 2026-10-07, gate MET: one complete apply -> verify -> idempotent re-apply -> rollback -> verify cycle on a real guard-APPROVEd recommendation against the mock store, human approval required, logged in `action_log`. Deterministic guard-selected actions, not LLM-chosen. Cost $0. Full text: `docs/archive/phases-6.md`; trail: `docs/learned/results/phase6/gate-cycle.txt`.

### Phase 7 — Production
Full dockerization. Deployment to the Hetzner VPS chosen at Phase 7 (ADR-0030) behind Caddy, on a real domain, walked through step by step with the user — this is new territory for him, so explain SSH hardening, firewall rules, DNS, volumes and database backups as you go, and write `docs/DEPLOYMENT.md` as you do it.

Minimal dashboard: product list, matches found, pending recommendations with rationale, price history chart. Monitoring: per-source volumes, matching score distribution, latency, cost per recommendation. 60–80 tests. CI green.

**Gate:** publicly reachable URL, README with the results table, short demo GIF.

---

## 10. README requirements

Written incrementally, not at the end. Must contain:
1. The problem in five lines, understandable by a non-technical reader
2. Architecture diagram (Mermaid, inline)
3. **The results table** — baseline vs implemented solution, per component, with the metric named
4. What the system does *not* do, and why
5. Local setup in three commands
6. A short demo GIF — a recruiter on a phone will not clone the repo

---

## 9. Things that must never happen

- A scraper hitting a live site during tests
- An LLM call outside `src/pricepilot/llm/client.py`
- Attribute extraction re-running on unchanged titles
- A metric in the README with no script behind it
- A margin check implemented inside a prompt
- A test split at pair level
- Secrets committed
- A claim that something works without showing the command output
- Silent degradation when a budget cap is hit
- A contact email, or any personal detail, in a committed file
- A non-ASCII byte in a `.ps1` file (PowerShell 5.1 reads a BOM-less script as ANSI and mis-parses it; `tests/test_powershell_ascii.py` enforces this, ADR-0013)
- Reporting "recovered the planted elasticity" — or any metric computed against the mock store's
  generator constants — as a result
- Leaving Phase 1 with the hand-verified overlap estimate (ADR-0023) below 400 instead of adding a
  source — this refers to the gate measurement, not the proxy key's own daily-floor count, which
  reads far lower by design and is never itself the gate
- Starting a paid fine-tuning run before the ~$1–2 smoke run has passed
- Agreeing with a bad idea because the user proposed it

---

## 11. Tracking

Bogdan works only in the terminal. He has no dashboard, no project board, and no way to see project state except what you show him. Tracking is therefore part of the build, not paperwork.

Four artefacts, created in Phase 0 and maintained from then on:

**`STATE.md`** — the single source of truth, in the repo root. Rewritten (not appended) so it never grows stale. Structure:
```
# STATE
Phase: <current>   Updated: <date>
**Where we are:** <= 8 lines, current only.

## Gate progress
Phases 0-3: one line each (CLOSED date + gate figure + pointer to docs/archive/).
Current phase: its checklist, condensed to <= 2 lines per item + a pointer to its ADR addendum.

## Last done
- <five most recent completed items, newest first>

## Open issues
- <only still-open items, condensed, with why — resolved items move to docs/archive/STATE-history.md>

## Blocked on Bogdan
- <decisions or manual steps waiting on him>
```

**`make status`** — prints the live numbers, queried from the database and the repo, never hand-written: current phase, gate checklist, listings collected per source, **the cross-shop overlap gate (≥400, met by the hand-verified sample per ADR-0023 — the proxy key it also prints alongside is a daily floor indicator, not the gate itself)**, days of price history, annotated pairs, tests passing, spend to date. This is the command he runs when he opens the terminal. Build it in Phase 0 and extend it each phase.

**`DECISIONS.md`** — short ADRs, append-only. One entry per architectural choice: context, decision, alternatives rejected, date. Three to six lines each. Future-Bogdan reads this when he cannot remember why something is the way it is, and at interview prep.

**`docs/COSTS.md`** — every paid action: date, what, estimated, actual, running total. Updated in the same commit as the work that spent the money.

Update `STATE.md` at the end of every work session, and `DECISIONS.md` whenever a choice gets made. If you finish a task and do not update tracking, the task is not finished.

**Context budget.** CLAUDE.md <= 400 lines, STATE.md <= 400 lines, DECISIONS.md <= 600 lines,
enforced by `tests/test_context_budget.py`. When a phase closes: its §7 text moves to
`docs/archive/phases-*.md`, its STATE history to `docs/archive/STATE-history.md`, and its ADR is
condensed in DECISIONS.md with the full text moved to `docs/archive/`. Move, never delete.
