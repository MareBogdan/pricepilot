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
**The main session is the orchestrator and does most of the implementation itself.** Sub-agents fragment context and cost more tokens; they earn their keep only on genuinely isolated, repetitive or high-volume work. Phase 0 creates exactly these three in `.claude/agents/`:

| Agent | Use it for | Why it's isolated |
|---|---|---|
| `scraper-engineer` | One source adapter at a time, against saved fixtures | Repetitive, self-contained, produces a lot of throwaway parsing detail |
| `reviewer` | Reviewing a diff against §0 and §6 before merge | Needs a fresh perspective, not the context that produced the code |
| `researcher` | Investigating an option and writing a doc | High token volume, single-document output |

Do not create more agents. Do not delegate core ML, RAG or decision-engine work — that stays in the main session, because those decisions need full project context and are what the user most needs explained.

---

## 5. Cost discipline — read this before writing any scraper or LLM call

This is the part where money gets wasted. Treat it as a hard engineering constraint.

### Scrapers
1. **Never test a scraper against a live site in a loop.** First run fetches *one* page and saves the raw HTML to `tests/fixtures/<source>/`. All subsequent development and all tests run against those saved fixtures, offline.
2. Every scraper has a `--limit` flag. Default is 5 items. Full runs are explicit.
3. Every scraper has a `--dry-run` flag that parses and prints but writes nothing.
4. Rate limit: minimum 2 seconds between requests, randomized. Respect `robots.txt`. Honest User-Agent with a contact.
   **The contact address is never committed.** Scrapers read `SCRAPER_USER_AGENT` from `.env`; the repo
   carries only `.env.example` with a placeholder. A scraper that finds no `SCRAPER_USER_AGENT` fails
   loudly at startup rather than falling back to a default or an invented address.
5. Self-hosted HTTP first (`httpx` + `selectolax`). Playwright only when a site genuinely requires JS. Paid scraping services (proxies, Apify-style) only if the user explicitly approves — assume €0 for these by default.
6. Every run logs to a `scrape_runs` table: source, items found, errors, duration. If a source's item count drops more than 40% vs the previous run, raise an alert instead of silently ingesting.

### LLM API calls
1. **Cache by content hash.** Attribute extraction runs once per unique normalized title, never per scrape run. The price changes daily; the title almost never does. Re-extracting on every run multiplies cost by the number of days. This is the single largest cost risk in the project.
2. Use the cheapest capable model for bulk work. Escalate only where quality demonstrably fails.
3. Use prompt caching for the system prompt, and batch processing where latency doesn't matter.
4. Every LLM call goes through **one wrapper module** (`src/llm/client.py`) which logs model, input tokens, output tokens and computed cost to a `llm_calls` table. No direct SDK calls anywhere else in the codebase.
5. Implement a hard spend cap in that wrapper, read from `LLM_BUDGET_USD` in `.env`. On exceeding it, raise — never degrade silently.
6. Before any batch job over 500 calls, print an estimate and require confirmation.
7. `make cost` prints spend to date, broken down by phase and model.

### GPU / training
Fine-tuning runs on rented GPU by the hour. Before any training run: state the expected duration and cost, and confirm the dataset and eval harness are ready. Never start a run "to see what happens".

### Spend schedule

The user currently has **$20 available**. Ceiling for the whole project is **$100**, but the realistic landing point is around $50. Most of this project costs nothing.

**Money is reserved in priority order, not spent in phase order.** The deliverable is a publicly
reachable demo. Hosting is what makes the project visible to a recruiter; a fine-tuned model on a
dead URL is worth nothing. So:

| Priority | What | Reserve | Approval needed |
|---|---|---|---|
| **1 — reserved first** | VPS hosting, three months (Hetzner CX22 ~€4/mo) | **~$15** | yes, once, at Phase 7 |
| **2** | LLM attribute extraction, Phase 2, cached by title hash | $2–3 | yes, before first batch |
| **3** | Recommendation generation, Phase 5 | $5–8 | yes |
| **4** | Optional pre-labelling assist, Phase 3 | $2–4 | yes |
| **not committed** | GPU rental for LoRA fine-tuning | — | **separate decision at week 5** |

Phases 0, 1 and 4 cost nothing and are not in this table.

**GPU fine-tuning is not a committed budget line.** It is a decision taken at week 5, on the
evidence available then: whether the annotated dataset exists, whether the cross-encoder baseline
is recorded, and whether a free tier (Colab / Kaggle T4) can carry the run. Treating it as
committed now is what makes the $20-available arithmetic fail.

**When that decision is taken, the first fine-tune is a deliberate smoke run.** Smallest model,
~200 examples, a few minutes of wall clock, **~$1–2** — its purpose is to prove the pipeline runs
end to end: dataset loads, LoRA attaches, training steps, checkpoint saves, eval harness scores it.
The number it produces is discarded. Only after that succeeds does the real run get approved, as a
second `SPEND:` line. Never start the real run first.

**Rules that follow from this:**
- Phases 0, 1 and 4 must be completed with zero spend. If a design needs money in those phases, the design is wrong.
- Do not start any paid work until the free work around it is finished and tested.
- Announce the cost *before* the action, in the format: `SPEND: <action> — est. $X.XX — proceed?`
- After any paid action, report actual vs estimated.
- Track everything in `docs/COSTS.md`, updated in the same commit as the work.

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

**Deployment target (decided):** a single Hetzner CX22 VPS (~€4/month), Docker Compose, **Caddy** as reverse proxy for automatic HTTPS. Not Kubernetes, not a PaaS. The user has not deployed to a VPS before — explain each step: SSH keys, firewall, domain DNS, systemd unit, backups.

**Model serving (decided):** the fine-tuned 0.5B matching model runs **quantized on CPU on the same VPS**, in real time. This is a deliberate architectural choice and one of the strongest selling points of the project. Phase 3 must produce a benchmark table comparing the local model against a large hosted API model on: accuracy, p50/p95 latency, and cost per 1,000 comparisons. If CPU latency proves unworkable, fall back to nightly batch inference — but measure first, and record the measurement either way.

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
Scaffold the repo, Docker Compose with Postgres + pgvector, initial schema and migration, `.env.example`, ruff + mypy + pre-commit, pytest, `make` targets, `STATE.md`, `docs/` structure, `.claude/agents/`, `.claude/commands/`.

Also build `services/mock-store` — a small FastAPI service standing in for the user's own shop: a seeded product catalogue (SKU, title, brand, category, purchase cost, current price, stock), synthetic price and sales history, `GET /products`, `GET /products/{id}/history`, and `PATCH /products/{id}/price`. Keep it under ~300 lines. It is a fixture, not a feature — no cart, no checkout, no storefront. Its purpose is to give the pipeline a catalogue to price against and a real endpoint for Phase 6 tool calling to target, mirroring how a Shopify or WooCommerce integration would work.

Also produce `docs/AUDIT.md`: your own critical review of this plan. What is underspecified, what is likely to fail, what you would change. Be blunt. The user wants disagreement, not agreement.

**Gate:** `docker compose up` works, `/health` responds, mock-store serves a seeded catalogue and accepts a price update, `make test` passes, `make lint` passes. Zero dollars spent.

### Phase 1 — Collection

**Product scope — pet food and supplies.**

Include: dry and wet food, treats, litter, grooming and hygiene products, accessories, toys. **Exclude anything regulated** — veterinary medicines, antiparasitics, prescription diets, vaccines. Those are pharmaceutical products and carry compliance questions this project does not need. Filter them out at ingest, not later.

Include a listing only if it has a real manufacturer and a stable product identity another shop could also sell. Build a manufacturer allowlist from the data (Royal Canin, Purina, Pro Plan, Acana, Orijen, Hill's, Brit, Taste of the Wild, Advance, Josera, Calibra, Trixie, Bosch, Petkult, Smølke and so on) and record it in `docs/SOURCES.md`.

**Why this category — the matching problem is genuinely hard.**

No global product code appears in the titles, and the same product is written in fundamentally different title grammars across shops. Verified examples of the identical kind of product:

- `animax.ro`: "Hrana uscata pentru caini Orijen Original Dog Adult Mini **4.5 kg**"
- `zoomalia.ro`: "**12 kg** SMØLKE Hrană uscată Medium cu pui pentru câini seniori" — weight first, plus a price-per-kg figure
- `petmax.ro`: "Recompense caini, Calibra Joy Dog Classic Duck Strips **80 g**"
- `pentruanimale.ro`: "BRIT Premium By Nature Adult Large Breed, **L**, Pui, hrană uscată câini" — comma-separated attribute style

The dominant hard negative is the size variant: same brand, same product line, different weight is **not** a match. Models get this wrong constantly, and it will likely be the largest error class in Phase 3. Related traps: pack counts ("3 pipete", "24x85 g"), dosage bands tied to animal weight ("10-25 kg"), and breed-size codes (Mini, Medium, Maxi, L, XS-XL).

**Known structural difference between sources — handle it in the adapter.**
`petmax.ro` lists each size as its own product row. `pentruanimale.ro` groups variants under one product and shows a price range ("38,01 lei - 62,00 lei", "Vezi 5 variante"). The adapter for grouped sources must expand variants into individual listings, which may require fetching the product page. Normalise to one row per purchasable variant before anything downstream sees the data.

**Sources — verified, do not search the web for alternatives.**

1. **`petmax.ro`** — Gomag platform, fully server-rendered. ✅ Verified. Raw HTML contains title, brand, previous price, current price, discount percentage, stock state and review count. Richest data of the set; use as the anchor source.
2. **`pentruanimale.ro`** — server-rendered. ✅ Verified. Note the variant-grouping issue above.
3. **`animax.ro`** — Magento, server-rendered product pages. ✅ Verified via indexed product pages carrying full titles and weights.
4. **`magazindeanimale.ro`**, **`zoopoint.ro`** — carry the same catalogue, different title conventions. ✅ Overlap confirmed.
5. **`zoomalia.ro`**, **`zoomania.ro`**, **`maxi-pet.ro`** — available, audit before implementing.
6. **Affiliate product feeds** (Profitshare, 2Performant) where a shop offers one — structured CSV/XML built for third-party consumption, refreshed daily. Prefer these when available.

**Cross-shop overlap is confirmed, not assumed.** The same product — Orijen Original Dog Adult Mini, 1.8 kg — appears as:
- `animax.ro`: "Hrana uscata pentru caini Orijen Original Dog Adult Mini 1.8 kg"
- `magazindeanimale.ro`: "Hrană uscată câini ORIJEN Original Dog Adult Mini 1,8 kg"
- `zoopoint.ro`: "Orijen Original Dog Adult Mini" — **no weight in the title at all**; size is a separate variant
- `petmax.ro`: names the line "Orijen Adult Original" — **word order reversed** inside the brand line

Decimal comma versus point, diacritics present or absent, brand casing, weight in title versus weight as variant, and reordered line names. Shops also expose internal SKUs (`ORJ_D_OD_AMI_2`) that are useless across shops. Seed the annotation tool with pairs drawn from exactly these four shops.

*Do not use:* **`shop4pet.ro`** — disallows automated access in `robots.txt`. ❌ Confirmed. Also avoid eMAG and other large marketplaces.

**Before implementing any source,** fetch one page with `curl`, confirm titles and prices are in the raw response rather than injected by JS, read `robots.txt`, note the crawl-delay, and record all of it in `docs/SOURCES.md`. If prices are absent from the raw response, drop the source rather than reaching for a headless browser.

Implement adapters behind a common `Scraper` protocol. Save fixtures. Schedule runs. Log every run and detect volume drops. Validate with Pydantic at the boundary.

**Build order — one scraper first, on a schedule, before the others exist.**

Do not build three adapters and then schedule them. Build **`petmax.ro` only**, put it on a daily
schedule, and let it accumulate history while the other two adapters are written. History is
wall-clock: a day not collected is a day that cannot be recovered later, and Phase 4 is the phase
that pays for it. The other sources join the schedule as each one is finished. The cost of this
ordering is nothing; the cost of the alternative is weeks.

**Cross-shop overlap is a gate condition, not an assumption.**

Phase 3 is a matching problem. If the same product does not appear on two shops, there is no
positive class, and every downstream phase is unfounded. This must be measured while there is still
time to react — in Phase 1, not in week 6.

Measure it with a **cheap proxy key**, no matching model involved, just SQL: normalise
`(brand, product-line tokens, net weight in grams)` and count keys that collide across two or more
sources. The proxy will be wrong in both directions — it will miss real matches the model would
find, and it will join a few products that are not the same. That is acceptable: it is a floor
estimate used to make one decision, and a floor is exactly what is needed here. Do not build a
matching model to compute it.

If the count cannot reach **400**, **add a source before leaving Phase 1** — not later. That is the
whole point of measuring it now. (2026-09-13, ADR-0023: the proxy key's own recall measured at
~8% — too low to decide this on its own. The gate decision is now made from a hand-verified random
sample instead; the proxy key stays a daily floor indicator, not the gate measurement. Threshold
unchanged.)

`make status` reports the overlap count from day one, alongside listings per source, so the number
is visible as it grows rather than discovered at the gate.

**Gate:**
- ≥3,000 in-scope listings from ≥3 sources, at least one of them non-Shopify
- ≥7 consecutive days of history
- **≥400 products appearing on two or more shops** — the threshold, unchanged. Measured by the
  proxy key above only as a first pass; the proxy key's own recall runs low enough (~8%, ADR-0023)
  that it cannot decide this alone. The gate itself is met by a hand-verified random sample of
  listings (method and evidence in DECISIONS.md ADR-0023), reported alongside the proxy key's own
  count — which `make status` prints every day as a floor indicator, explicitly labelled as such,
  never as the gate itself.
- all adapters tested offline against fixtures
- `docs/SOURCES.md` complete

> Start collection as early as possible and let it run in the background. Phase 4 needs price history, and history cannot be backfilled.

### Phase 2 — Normalization

Extract only what is in the title or description: brand and product line, net weight or volume with unit, pack count, breed-size code (Mini, Medium, Maxi, XS-XL, L), life stage (Puppy, Junior, Adult, Senior), flavour or protein source, food form (dry, wet, tin, pouch), and dosage band where present.

Regex and lookup tables first — weights, pack counts and dosage bands are trivially matched and running an LLM over them is wasted money. LLM fallback only for the rest, cached by content hash.

**Unit normalisation is not optional here.** "4.5 kg", "4,5 kg", "4500 g" and "12 kg" as a leading token must all resolve to a comparable numeric field. Get this right and a large share of the matching problem becomes tractable; get it wrong and the fine-tuned model spends its capacity compensating.

Also handle: Romanian descriptive prefixes the shop adds ("Hrana uscata pentru caini...", "Recompense caini, ..."), diacritic inconsistency, brand names with special characters (Smølke, Hill's), and price-per-unit figures that some shops append to the title area.

**Gate:** ≥85% attribute accuracy on 100 manually verified listings, with weight parsing measured separately; the cache demonstrably prevents repeat calls on unchanged titles.

### Phase 3 — Matching ⭐ core of the project
1. Candidate retrieval via embeddings, measured by recall@20 (target ≥90%)
2. A local annotation tool — single HTML page, keyboard-driven (`M`/`N`/`S`), so 200 pairs/hour is realistic
3. **The user annotates 800–1,000 pairs manually.** At least 40% hard cases: same model different capacity, single unit vs multipack, consecutive generations, same title different brand. This dataset is the most valuable artefact in the repo — it is not generated, it is labelled.
4. Product-level train/val/test split
5. Baseline: classical cross-encoder. Record precision/recall/F1.
6. Fine-tune a 0.5B–1.5B instruct model with LoRA/QLoRA. Same test set.
7. Comparison table + error analysis of 10 representative failures

8. Quantize the fine-tuned model and benchmark it running on CPU: accuracy, p50/p95 latency, cost per 1,000 comparisons — against both the classical baseline and a large hosted API model

**Gate:** documented baseline vs fine-tuned comparison on a held-out product-level test set, broken down by category as well as overall, plus the three-way serving benchmark above.

> If fine-tuning does not beat the baseline, write that down honestly and analyse why. A correctly reported negative result is stronger evidence of competence than an unexplained good number.

**Fine-tune versus cross-encoder is an uncertain bet, and that is accepted going in.** The fine-tune
may not beat the classical cross-encoder on F1. That does not make the phase a failure, and it does
not license quietly reframing the goal afterwards:

- If the fine-tune **wins on F1** — report the margin, broken down by category, with error analysis.
- If the two **tie on F1** — the serving benchmark is the result. A local quantized model matching a
  cross-encoder at some cost per 1,000 comparisons and some p95 latency is a real, reportable finding,
  and it is the engineering question a hiring manager actually cares about. Report cost and latency
  as the headline, F1 as the parity claim it is.
- If the fine-tune **loses** — say so, in the README results table, and analyse why.

Whichever happens, report what actually happened. The decision rule is written down here, before the
numbers exist, precisely so the numbers cannot choose the framing.

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
Write a 300–500 word pricing policy document. Index it. Build the recommendation prompt combining: product, matched competitor prices (SQL), estimated elasticity (model), relevant policy passages (RAG). Deterministic margin guardrail after the LLM. Full trace persisted.

**Gate:** 50 generated recommendations, zero margin violations.

### Phase 6 — Tool calling
Strict-schema tools: `update_price`, `flag_for_review`, `do_nothing`. Human approval by default; automatic mode only under narrow conditions. Full action log with rollback.

**Gate:** one complete cycle end to end, visible in logs.

### Phase 7 — Production
Full dockerization. Deployment to a Hetzner CX22 behind Caddy, on a real domain, walked through step by step with the user — this is new territory for him, so explain SSH hardening, firewall rules, DNS, volumes and database backups as you go, and write `docs/DEPLOYMENT.md` as you do it.

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
- An LLM call outside `src/llm/client.py`
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
Phase: 3 — Matching
Updated: 2026-09-20

## Gate progress
[x] candidate retrieval, recall@20 = 0.93
[x] annotation tool built
[ ] 1000 pairs annotated — 340 done
[ ] baseline trained
[ ] fine-tune trained
[ ] serving benchmark

## Last done
- <five most recent completed items, newest first>

## Open issues
- <anything known-broken or deferred, with why>

## Blocked on Bogdan
- <decisions or manual steps waiting on him>
```

**`make status`** — prints the live numbers, queried from the database and the repo, never hand-written: current phase, gate checklist, listings collected per source, **the cross-shop overlap gate (≥400, met by the hand-verified sample per ADR-0023 — the proxy key it also prints alongside is a daily floor indicator, not the gate itself)**, days of price history, annotated pairs, tests passing, spend to date. This is the command he runs when he opens the terminal. Build it in Phase 0 and extend it each phase.

**`DECISIONS.md`** — short ADRs, append-only. One entry per architectural choice: context, decision, alternatives rejected, date. Three to six lines each. Future-Bogdan reads this when he cannot remember why something is the way it is, and at interview prep.

**`docs/COSTS.md`** — every paid action: date, what, estimated, actual, running total. Updated in the same commit as the work that spent the money.

Update `STATE.md` at the end of every work session, and `DECISIONS.md` whenever a choice gets made. If you finish a task and do not update tracking, the task is not finished.

## 12. First session

1. Read this file fully
2. Write `docs/AUDIT.md` — your critical review of this plan. At least five specific concerns and what you would do differently. Be blunt; the user wants disagreement, not agreement.
3. Build Phase 0 end to end, autonomously. Do not ask for approval on scaffolding.
4. Report: what exists now, what the audit flagged, and the decisions you need from the user before Phase 1.

Matching hard cases worth seeding the Phase 3 annotation tool with, so the dataset is not all easy pairs: the same food in different net weights, the same line in different breed sizes, the same product as tin versus pouch versus dry, pack-count differences, life-stage variants, flavour variants within one line, and the same product written by two shops in different title grammars (weight-first versus weight-last, comma-separated attributes versus prose).

For Phase 5, the pricing policy document should cover realistic pet-retail rules: minimum margin per category (dry food carries thinner margins than accessories), brands with distributor pricing restrictions, products excluded from automatic discounting, daily maximum price movement, and rounding conventions. This is genuine natural-language policy — the correct use of RAG. The numbers it references (costs, current margins, stock) still come from SQL.