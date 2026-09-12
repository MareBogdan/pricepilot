# AUDIT — critical review of the PricePilot plan

Date: 2026-09-12
Author: Claude (main session), before writing any project code.
Audience: Bogdan. This document is deliberately adversarial. Nothing here is a blocker;
everything here is a risk that gets cheaper the earlier it is decided.

---

## Summary judgement

The plan is well above the median portfolio project. The three things that make it good:
a genuinely hard matching problem with no shared product identifier, a deliberate small-model-on-CPU
serving decision, and the discipline of "numbers from SQL, RAG only for policy text".

The plan's weakness is not technical, it is **scheduling**. It has one long-lead dependency
(price history) and one irreplaceable manual bottleneck (1,000 hand-labelled pairs), and the phase
ordering hides both. That is concern #1 and it is the one I would actually change today.

---

## Concern 1 — The phase ordering guarantees dead time. This is the biggest flaw.

`CLAUDE.md §7` orders the work 0 → 1 → 2 → ... → 7, with a note that collection "should start early".
A note is not a mechanism. Two things in this project take *wall-clock* time that no amount of
working faster can compress:

- **Price history.** Phase 4 needs ≥7 days at the gate, and realistically wants 4–6 weeks to show
  any promotion cycle. You cannot backfill this. Ever.
- **Annotation.** 800–1,000 pairs at a genuine 150–200/hour (the 200/hour figure assumes every pair
  is a fast `M`/`N`; the 40% hard cases are not fast) is 5–7 hours of *your* focused time, in
  sittings, not one evening.

If Phase 1 finishes in week 2 and Phase 3 annotation starts in week 5, you have burned three weeks
of history you could have had for free.

**What I would change:** treat collection and annotation as *background tracks* that start at the
earliest possible moment and run concurrently with everything else, and make the phase gates
reflect that. Concretely:

- Get **one** scraper (petmax.ro, the anchor source) to production quality and on a daily schedule
  **before** building the other two. Day-1 history matters more than source coverage.
- Move the annotation tool (currently Phase 3, item 2) to the **end of Phase 2**. The moment you
  have normalized listings, you can generate candidate pairs and start labelling — you do not need
  the embedding retriever finished to label pairs, you only need it to *rank* them.
- Add a "days of history" and "pairs annotated" counter to `make status` from day one, so the
  clock is visible every time you open the terminal. (I have built both.)

## Concern 2 — The Phase 1 gate (≥3,000 listings, ≥3 sources, ≥7 days) is the wrong shape

It measures volume, and volume is the one thing that is easy. It does not measure the property the
entire rest of the project depends on: **cross-shop overlap**.

If you collect 3,000 listings from three shops and only 60 products appear in more than one shop,
Phase 3 has no positive class. You would not discover this until you were building the annotation
tool, which is weeks later. The plan asserts overlap is "confirmed, not assumed" — it is confirmed
for *one product* (Orijen Original Dog Adult Mini). One anecdote is not a base rate.

**What I would change:** add to the Phase 1 gate an *overlap estimate*: after ingest, run a crude
brand+weight blocking join across sources and report how many distinct (brand, line, weight) tuples
appear in ≥2 sources. Target something like **≥400**. If the real number is 50, you find out in
week 2 while you can still add sources, not in week 6 when you cannot.

This is cheap — it is one SQL query over data you already have — and it is the single highest-value
change to the plan.

## Concern 3 — "Fine-tuning beats the baseline" is not a safe bet, and the plan half-knows it

`CLAUDE.md §7` says, honourably, that a negative result should be reported. Good. But the plan
still structures Phase 3 as though fine-tuning is the deliverable and the baseline is a formality.
Be clear-eyed about the actual odds:

- A well-tuned cross-encoder (e.g. a multilingual MiniLM) on 800 in-domain pairs is a *strong*
  baseline. Cross-encoders are extremely sample-efficient on pairwise-similarity tasks.
- A 0.5B instruct model LoRA'd on 800 examples is working against its grain: it has to learn a
  binary decision through a text-generation head, from a small dataset, in a language (Romanian)
  that is thin in its pretraining mix.
- The dominant error class you identified — same brand/line, different weight — is a task where an
  exact numeric comparison beats any learned representation. A 5-line rule ("if both sides have a
  parsed net weight and they differ by >2%, it is not a match") will likely outperform both models
  on that slice.

**What I would change:** three things.
1. Add that deterministic weight rule as an explicit **third system** in the comparison table. If a
   rule beats your fine-tune on the hard slice, that is a genuinely interesting finding and a much
   better interview story than "my fine-tune got 0.91".
2. Budget for **two** fine-tuning runs, not one. The first run will have a bug — a prompt format
   mismatch, a label leak, an eval that scores the wrong token. Everyone's does.
3. Consider fine-tuning the **cross-encoder** rather than only an LLM. It is free (runs on your CPU
   or a free Colab T4), takes minutes, and is the technically correct tool. The LLM fine-tune can
   still happen as the "can I do LoRA" demonstration, but do not stake the project's headline
   number on it.

## Concern 4 — The demand model is the weakest link and the plan overstates its defensibility

`§7 Phase 4` says the real/synthetic split ("real prices, simulated sales") is a defensible
methodology. It is honest, which is not the same as defensible. The problem:

**You generate the sales from an elasticity you choose, then fit a model, then report the recovered
elasticity as a finding.** That is a circular loop. The model is being graded on its ability to
invert your own data generator. MAE against a naive baseline on synthetic data measures nothing
about the real world — it measures that your generator has learnable structure, which you
guaranteed by writing it.

A sharp interviewer will ask "what would this model have predicted if your elasticity assumption
was wrong?" and there is no good answer.

**What I would change:** reframe Phase 4 from "we estimate demand" to **"we built the elasticity
estimation harness, and validated it by recovering known ground-truth elasticity from simulation"**.
That is a real and honest engineering claim — it is exactly how you would validate such a pipeline
before real sales data existed. Then:
- Report **recovery error** (estimated elasticity vs the planted one), not just MAE. That is the
  metric that actually means something on synthetic data.
- State in the README that the demand component is a *harness validated in simulation*, not a
  trained-on-reality model. Say it before the interviewer says it.
- Keep the naive baseline comparison, but stop treating it as the headline.

Also: MLP vs GRU is over-specified for a 7-day-history problem. Start with **ridge regression on
log(price) with category fixed effects**. If a linear model recovers the planted elasticity and a
GRU does not beat it, that is your result, and it is a much more mature one.

## Concern 5 — Budget and risk are concentrated in exactly the wrong place

`§5` allocates **$15–25 of a $20 current balance** to GPU fine-tuning — the single item with the
highest chance of being wasted (see concern 3) and the lowest marginal contribution to a working
demo. Meanwhile Phase 5 recommendation generation ($5–8) and hosting (€12–16) are what make the
project *visible to a recruiter*, and they are queued behind it.

There is also a hard arithmetic problem: **$20 available, $15–25 for one GPU run.** A single failed
run leaves nothing for the deployed demo. The plan's stated ceiling of $100 is not money you have.

**What I would change:**
- Spend on **hosting first**. A publicly reachable URL is worth more than a fine-tune in every
  scenario where a recruiter spends 90 seconds on your repo.
- Do the LoRA run on a **free Colab/Kaggle T4** first (0.5B with QLoRA fits comfortably). Rent a GPU
  only if the free tier genuinely blocks you. This likely takes GPU spend to ~$0.
- Reprice the realistic total: ~€15 hosting + ~$5 extraction + ~$8 generation ≈ **$30**, with the
  GPU line as an optional extra rather than the largest item.

## Concern 6 — Five smaller things that will bite

1. **`docker compose up` is in the Phase 0 gate and Docker is not installed on this machine.**
   I verified: `docker` and `make` are both absent. The gate as literally written cannot pass today.
   I have built the compose stack and a Postgres-free local path so work is not blocked — see
   `STATE.md` → Blocked on Bogdan.
2. **`make` is also absent on Windows.** I have written a real `Makefile` (for CI and the VPS) plus a
   `make.ps1` shim so `.\make.ps1 status` works here today. The logic lives in `scripts/`, so
   neither is the source of truth. This is a deliberate deviation from `§11`, recorded in
   `DECISIONS.md`.
3. **The scraping-legality posture is thin.** `§5` covers rate limiting and `robots.txt`, which is
   the right start. But this is EU/Romania, the project is public on GitHub, and you are named on
   it. Do not commit raw scraped HTML fixtures containing shop content into a public repo without
   thinking about it — keep fixtures minimal, trimmed, and documented as "retained for offline
   testing". I would add a short `docs/LEGAL.md` before Phase 1 goes public.
4. **pgvector + a 0.5B model + Postgres on a CX22 (2 vCPU / 4 GB) is tight.** Quantized 0.5B is
   ~500 MB resident, Postgres wants its shared buffers, and Next.js build is memory-hungry. Build
   the frontend in CI, ship a static export, and do not run `next build` on the VPS. Expect to need
   swap. Measure before committing to the CPU-serving claim.
5. **`§9` forbids "an LLM call outside `src/llm/client.py`" — enforce it mechanically.** A rule in a
   markdown file is a suggestion. I have added a ruff lint rule banning direct SDK imports outside
   that module, so CI fails instead of you remembering.

---

## What I would keep exactly as-is

- **Numbers from SQL, RAG only for policy** (`§6.1`). This is the single most common failure in
  portfolio RAG projects and the plan gets it right.
- **Margin floor as a Python `if` after the LLM** (`§6.2`). Correct.
- **Product-level test splits** (`§6.3`). Correct, and the plan is right that this is where these
  projects quietly become worthless.
- **Caching attribute extraction by content hash** (`§5`). Correct, and the cost analysis behind it
  is sound.
- **The pet-food category choice.** The matching problem here is genuinely hard for defensible
  reasons, and you can articulate why. This is a better category than electronics precisely because
  there is no EAN to fall back on.

---

## The five changes, ranked by value

| # | Change | Cost to do | Value |
|---|---|---|---|
| 1 | Add cross-shop **overlap count** to the Phase 1 gate (target ≥400 shared tuples) | one SQL query | Prevents discovering in week 6 that Phase 3 has no positive class |
| 2 | Start **one** scraper on a daily schedule immediately; move the annotation tool to end of Phase 2 | reordering only | Recovers 3+ weeks of price history and parallelises the manual bottleneck |
| 3 | Add a **deterministic weight rule** as a third system in the Phase 3 comparison | ~20 lines | Likely the strongest result on the hardest slice, and a better interview story |
| 4 | Reframe Phase 4 as an **elasticity-recovery harness**; report recovery error; start with ridge | reframing + simpler model | Removes a circular claim an interviewer will find |
| 5 | **Hosting before GPU**; attempt the LoRA run on free Colab/Kaggle first | scheduling only | Fixes the $20-available / $15–25-per-run arithmetic and front-loads the visible demo |

These are recommendations, not unilateral changes. I have implemented none of the reordering —
Phase 0 is built exactly as `§7` specifies. Decisions needed from Bogdan are listed in `STATE.md`.
