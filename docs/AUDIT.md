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

---

## 2026-09-13 — Diagnostic: why is overlap 94, not 400?

**Diagnostic only, per explicit instruction.** No code, no gate, no `STATE.md` box touched. Every
number below comes from a query or a live fetch shown inline or in the script it references; all
scripts ran from `.venv` against the real Neon database (single day of data, 2026-09-12) or against
the live sites at the `SCRAPER_MIN/MAX_DELAY_SECONDS` (2–4s) rate limit with the honest
`SCRAPER_USER_AGENT`, exactly as recon does. Scratch scripts live in this session's scratchpad, not
in the repo.

### Q1 — Is the Royal Canin concentration a fact about the market, or about the key?

**About the key.** Query: group every listing by `normalized_brand()`, count listings per source,
and count keys whose brand matches that appear on ≥2 sources (`compute_overlap`'s own key, not a
new one):

```
brand                   petmax  pentruanimale  matched_keys
royal canin                310            276           83
brit                        71            325            0
trixie                     210             86            0
inaba                       31            160            0
hill's science plan          0            185            0
julius k-9                 177              0            0
monge                       25            147            0
petkult                     77             94            0
calibra                     28            118            0
agility                    119             26            0
record                     140              0            0
hill's                     125              0            0
flexi                      124              0            0
mr bandit                   74             48            0
advance                     45             69            1
```

Five of the top 15 (by combined listing count) are exactly the pattern asked about: hundreds of
listings on **both** shops, zero or near-zero matches. `hill's` (125 petmax) and `hill's science
plan` (185 pentruanimale) are the same manufacturer split into two never-colliding brand buckets —
that alone is worth 310 listings that can mathematically never match, before a single title token
is compared.

**Worst 3 — Hill's, Brit, Calibra.** All three fail for the same three reasons, verified with real
title pairs a human would call the same product (weight-verified, i.e. genuinely the same pack
size, not just the same brand):

**Hill's** — petmax's brand field is `"Hill's"`; pentruanimale's is `"HILL'S Science Plan"`.
`normalized_brand()` uses the field verbatim, so these are two different `key_brand` values before
any title token is even read.

| petmax | pentruanimale |
|---|---|
| Hill's SP Canine Adult Perfect Digestion Medium **14 kg** | HILL'S SP Perfect Digestion Medium Adult, Pui cu Orez Brun, hrană uscată câini, sensibilități digestive, **14kg** |
| Hill's SP Canine Adult Light Large Breed **Chicken 14 kg** | Hill's SP Canine Adult Light Large Breed **Pui, 14 Kg** |
| Hill's SP Canine Adult Healthy Mobility Small and Mini **Chicken 6 kg** | Hill's SP Canine Adult Healthy Mobility Small & Miniature **Pui, 6 Kg** |
| Hill's SP Canine Puppy Small and Mini **Chicken 300 g** | Hill's SP Canine Puppy Small & Mini **Pui, 300 g** |
| Hill's SP Canine Adult Perfect Weight Medium **Chicken 12 kg** | Hill's SP Canine Adult Perfect Weight Medium **Pui, 12 Kg** |

**Brit** — worse: on petmax alone, the brand *field* fragments across four strings for the same
manufacturer — `Brit` (71), `Brit Premium` (51), `Brit Care` (49), `Brit Fresh` (12) — while
pentruanimale keeps one (`BRIT`, 325). This is a within-petmax data-quality issue, not just a
cross-shop one.

| petmax | pentruanimale |
|---|---|
| Hrana Uscata Brit Premium by Nature Cat Sterilized **Salmon 1.5 kg** | BRIT Premium by Nature Sterilized, **Somon**, hrană uscată pisici sterilizate, **1.5kg** |
| Hrana Uscata Brit Premium by Nature Cat Sensitive **Lamb 8 kg** | BRIT Premium by Nature Sensitive, **Miel**, hrană uscată pisici, sensibilități digestive, **8kg** |
| Hrana uscata pentru caini Brit Premium by Nature Adult **L 15 kg** | BRIT Premium By Nature Adult **Large Breed, L**, Pui, hrană uscată câini, **15kg** |
| Hrana uscata pentru caini Brit Premium by Nature **Sport 15 kg** | BRIT Premium By Nature **Sport**, Pui, hrană uscată câini, activitate intensă, **15kg** |
| Brit Care Cat Fillets in Gravy Choise **Chicken 85 g** | BRIT Care Fillets In Gravy, **Pui**, plic hrană umedă fără cereale pisici, (în sos), **85g** |

**Calibra** — same fragmentation pattern as Brit: petmax splits `Calibra` (28), `Calibra Life`
(part of 118 combined), `Calibra Premium`, `Calibra Expert`, `Calibra Veterinary` into distinct
brand-field strings; pentruanimale keeps one (`CALIBRA`).

| petmax | pentruanimale |
|---|---|
| Hrana uscata caini, Calibra Dog Expert+ Adult **Mobility & Joint Support 2 kg** | CALIBRA Expert Nutrition **Mobility**, XS-XL, Pui, hrană uscată câini, **sistem articular**, **2kg** |
| Hrana uscata caini, Calibra Dog Expert+ Adult **Mobility & Joint Support 12 kg** | CALIBRA Expert Nutrition **Mobility**, XS-XL, Pui, hrană uscată câini, **sistem articular**, **12kg** |
| Hrana uscata caini, Calibra Dog Life Senior Small Breed **Lamb 1,5 kg** | CALIBRA Life Senior Small Breed, XS-S, **Miel**, hrană uscată conținut redus cereale câini senior, **1.5kg** |
| Hrana uscata caini, Calibra Dog Premium Line Adult **Beef 12+2 kg** | CALIBRA Premium Line, XS-XL, **Vită**, hrană uscată câini, **12kg** *(base weight matches; petmax's bonus pack has no bonus counterpart on pentruanimale — flagged, not counted as a clean pair)* |
| Hrana uscata caini, Calibra Dog Life Senior Small Breed **Lamb 6 kg** | CALIBRA Life Senior Small Breed, XS-S, **Miel**, hrană uscată conținut redus cereale câini senior, **6kg** |

**What specifically breaks, in order of impact:**

1. **Brand-field fragmentation, both directions.** `normalized_brand()` takes the shop's brand
   field verbatim (lowercased), with no alias/canonicalization table. petmax's own field is
   sometimes a sub-line name (`Brit Premium`, `Calibra Life`) rather than the manufacturer; Hill's
   goes the other way — pentruanimale's field carries a sub-brand suffix (`Science Plan`) petmax's
   doesn't. Either direction produces a different `key_brand` and the key can never collide,
   regardless of the title.
2. **No English↔Romanian synonym table.** petmax writes flavour words in English (`Chicken`,
   `Lamb`, `Beef`, `Salmon`); pentruanimale writes them in Romanian (`Pui`, `Miel`, `Vită`,
   `Somon`). `line_tokens()` has no translation step, so this is a permanent, real difference in
   the token set for an otherwise-identical product.
3. **Exact-set equality with no partial credit.** `OverlapKey.line` is a full sorted tuple compared
   for exact equality — not "do these share enough tokens". pentruanimale's comma-separated grammar
   (documented in `docs/SOURCES.md`, predicted in `CLAUDE.md §7`) adds breed-size codes (`XS-XL`,
   `L-XL`) and condition descriptors (`sistem articular`, `sensibilități digestive`) that petmax's
   shorter titles don't carry. One extra token on either side is enough to break the match even
   when every other token lines up and a human would call it an obvious duplicate.
4. **Bonus-weight guard (ADR-0021, working as designed) still costs recall here.** A plain pack and
   a bonus pack of the identical line correctly get different keys — but that also means a plain
   listing on one shop and a currently-promoted bonus listing of the same line on the other shop
   never collide, even though a shopper would call them the same product.

None of this is a market fact. Brit and Calibra plainly have large, overlapping catalogues on both
shops — the five pairs per brand above are real, hand-verified, same-weight products. The key's
exact-match design (deliberately simple, per `docs/overlap.py`'s own docstring) is what's hiding
them, not thin real-world overlap.

### Q2 — How much of each shop's catalogue are we actually collecting?

**petmax.** Fetched `sitemap_categories.xml` live (134 categories, one request) and, for every
category not already in scope and not obviously pharma/farm/promo/other-species by name, fetched
page 1 and read the pagination widget's own last `?p=N` link — the same method `docs/SOURCES.md`'s
existing recon used, 28 requests at 2–4s spacing:

| category | pages | approx. listings |
|---|---:|---:|
| hamuri-lese-si-zgarzi | 18 | 432 |
| sampoane-si-balsamuri-caini | 8 | 192 |
| igiena-catel | 6 | 144 |
| sampoane-si-balsamuri-pisici | 5 | 120 |
| ansambluri-de-joaca-sisaluri | 5 | 120 |
| *(23 more, 24–96 listings each)* | | |
| **Total (28 categories)** | | **1,920** |

Two categories fetched during this pass — `hrana-accesorii-caini` and `hrana-accesorii-pisici` —
turned out to be **broken sitemap entries**, not real listing pages: both render the site's generic
`Caini`/`Pisici` hub page (`<h1 class="catTitle"> Caini </h1>`, empty `data-Gomag` blocks), which
is why their raw pagination read as 200 and 119 pages. Confirmed by fetching and inspecting the raw
HTML, not assumed. Excluded from every total below — a real finding in its own right: a blind
sitemap-wide pagination sum, with no spot-check, would have overcounted by ~4,800 + 2,856 listings
from two categories that aren't real categories at all.

The other 92 of 134 sitemap categories are pharmacy/vet/farm/promo-campaign/other-species
(fish/birds/reptiles/rodents)/pest-control, spot-checked against the list — out of product scope
by `CLAUDE.md §7` itself, or (promo/campaign categories) would double-count listings already filed
under a real category. Not fetched; fetching them would burn request budget on data that was never
going to count.

**The fraction depends entirely on which denominator you use, and only one of them is the right
one for interpreting 94:**

| Denominator | f_petmax | Why it's the wrong/right one here |
|---|---:|---|
| 13 / all 134 sitemap categories | **9.7%** | Wrong — the other 121 are overwhelmingly out-of-scope-by-design (pharmacy, farm, promo, other species) or broken sitemap noise, not missed catalogue |
| 13-category estimate / (13 + the 28 verified, minus the 2 broken) | 4,992 / 6,912 = **72.2%** | A real upper bound if petmax's category scope ever broadens past food/treats into the rest of accessories/hygiene/toys — but most of the 28 are narrow accessory/hygiene sub-facets (`hamuri-lese-si-zgarzi`, `castroane-...`) that `docs/SOURCES.md` already documented as cross-listing the same products filed under the broad `accesorii-*`/`igiena-si-ingrijire-*` categories already scraped, so the true incremental *unique* volume is likely well below 1,920 (unverified without per-product-ID de-duplication, which would need a real crawl) |
| **food/treat sitemap categories scraped / all food/treat sitemap categories that exist** | **~98%** (2,520 of ~2,568; the only gap found is `lapte-praf-caini`/`-pisici`, 48 listings, milk replacer — a different food form, not currently scraped) | **This is the one that matters.** Overlap=94 lives entirely in food/treats (pentruanimale scrapes *only* food/treat categories), and petmax's food/treat category set is already essentially fully covered by the current 13 |

The naive 9.7% number, if used to project "true" overlap, would be badly wrong in the optimistic
direction (see arithmetic below) — it's not the right correction to apply.

**pentruanimale.** Already measured same-day in `docs/SOURCES.md` (no new fetch needed — the
recon there already used the "one request per category" method): **3 of the 6 scraped categories
hit the ~600-product/50-page pagination wall** (`hrana-uscata-caini`, `recompense---snacks-caini`,
`hrana-umeda-pisici`). Products permanently unreachable through `?page=N`: 366 + 154 + 236 = **756
products**, corresponding to **1,266 listings** (uncapped estimate 6,593 vs. corrected/reachable
estimate 5,327 — the difference).

**Coverage factor and what 94 implies at full coverage — arithmetic, labeled ESTIMATE:**

```
f_petmax  (food/treat-relevant, the correct denominator) ≈ 2,520 / 2,568           ≈ 0.98
f_pentruanimale = corrected/reachable listings / uncapped true listings
                = 5,327 / 6,593                                                    ≈ 0.81

coverage factor = f_petmax × f_pentruanimale ≈ 0.98 × 0.81                         ≈ 0.79

projected true overlap at full coverage ≈ 94 / 0.79                               ≈ 119
```

If instead the broader (accessories/hygiene-inclusive) `f_petmax` of 72% is used —
appropriate only if category scope broadens beyond food — the factor is 0.72 × 0.81 ≈ 0.58 and the
projection is 94 / 0.58 ≈ **161**. Both are **ESTIMATES**, not measurements, and both are far below
400. The naive 9.7%-based projection (94 / (0.097 × 0.81) ≈ 1,196) is included only to show why it
must not be used: it divides by a denominator built mostly from pharmacy and farm-animal
categories that were never going to contain a matchable pet-food product.

**Conclusion for Q2: pagination/category coverage is a real, ~20–40% effect, not the ~4×
effect needed to reach 400.** It closes part of the gap (94 → roughly 120–160) but the dominant gap
to 400 is not a coverage problem — it's the key's recall problem (Q1) plus the market's real
brand concentration.

### Q3 — What is the key's recall, roughly?

Sampled 50 random petmax listings that are keyable and in a food category (dry/wet/treats × dog/cat
— the same 6 categories pentruanimale scrapes), fixed random seed for reproducibility (2,329
eligible listings; seed `20260913`). For each, searched pentruanimale's real listings **by hand**
— brand root word + weight + an English↔Romanian flavour translation table (chicken/pui,
lamb/miel, beef/vită, salmon/somon, turkey/curcan, duck/rață, rabbit/iepure, tuna/ton), explicitly
*not* using `overlap_key()` — and judged whether the same purchasable unit (same brand, same line,
same pack size) genuinely exists on both shops.

**Result: 27 of the 50 (54%) genuinely exist on both shops. Of those 27, the current key found
0.** Examples of genuine, hand-confirmed matches the key missed: `Royal Canin Feline Digestive
Care, 10 kg` (petmax) ↔ `ROYAL CANIN Digestive Care Adult, hrană uscată pisici, confort digestiv,
10kg` (pentruanimale) — missed on the extra `feline`/`confort digestiv` tokens; `Inaba Ciao Dashi
Delights Ton și Fulgi de Bonito 70g` — identical on both shops, missed only because pentruanimale's
brand field is `INABA` while the sample's `overlap_key` never got a chance to compare it (the title
tokens matched perfectly; brand normalization elsewhere in the run is where it would have kept
failing at scale).

**Recall on this sample: 0/27 ≈ 0%.** With n=27 this has a wide confidence interval (a
rule-of-thumb upper bound for 0 successes in 27 trials is roughly 3/27 ≈ 11%), so "recall is
exactly zero" is not the claim — the honest claim is **recall is low, plausibly in the low single
digits to low tens of percent, not the 50%+ a working key would need.** This is corroborated by a
second, independent number: across *all* 2,329 keyable petmax food listings, only 4.3% (101) end
up in a matched key — far below the 54% hand-verified true-match rate found in the sample. If the
true match rate (54%) and the key's one-sided match rate (4.3%) both hold shopwide, that implies a
recall on the order of 4.3/54 ≈ **8%**, roughly consistent with drawing 0 matches in a 27-true-match
sample of 50 (expected ≈2.2, not implausible to land on 0).

**This is the single number that reframes 94.** If the true cross-shop food-category overlap rate
is closer to 54% of keyable petmax listings than to 4.3%, the *true* overlap between these two
shops today, at current coverage, is plausibly in the many hundreds — the 400 gate looks like it
was never actually about market thinness. It's a key-recall problem, consistent with Q1.

### Q4 — Does Phase 3 actually need 400?

Query: build every listing's `OverlapKey`, group by `(brand, line)` ignoring weight, and count
pairs of distinct-weight entries — same source (within-shop hard negative) or different source
(cross-shop hard negative) — plus the existing 94 true positives (`compute_overlap`'s own number,
reproduced exactly by this query as a sanity check):

```
TP (shared full key, matches compute_overlap):                          94
Cross-shop hard negatives (same brand+line, diff weight, diff shop):    175
Within-shop hard negatives (same brand+line, diff weight, same shop): 1,919
Total annotatable pairs (TP + cross-shop HN + within-shop HN):        2,188
```

2,188 candidate pairs already exceeds an 800–1,000-pair annotation set on raw volume, even before
counting easy negatives (any two listings that share nothing), which are effectively unlimited.

**But the more important point is that the positive class is not actually capped at 94 for
annotation purposes.** Q3 showed that a looser, brand+weight+translation-aware search (not the
strict key) surfaces true-positive *candidates* at roughly 54% of keyable petmax food listings —
call it on the order of 1,000+ candidate pairs across the full keyable set, each still needing a
human "yes/no", exactly the annotation tool's job. The 94-gate number measures the proxy key's
precision-first design, not the ceiling on how many genuine positive pairs a human annotator could
be shown.

**Answer: yes, a smaller positive class (94, or even the ~27-confirmed-per-50-sampled rate) still
supports an 800–1,000-pair set** — the hard-negative supply (1,919 within-shop + 175 cross-shop) is
large, and a broader candidate generator (not `overlap_key()` itself, just a looser blocking pass
for surfacing annotation candidates) can supply well more than 94 real positive candidates for the
annotator to confirm or reject.

### Bottom line across all four

- **94 is a key artifact, not a market measurement** (Q1, Q3). Brand-field fragmentation
  (both directions) and missing English↔Romanian synonym handling are the two biggest,
  concretely-demonstrated causes.
- **Coverage/pagination limits are real but secondary** — roughly a 0.6–0.8× factor (Q2), projecting
  true overlap at full coverage to roughly 120–160, not 400.
- **The recall estimate (Q3) implies the true number, at current coverage, could plausibly already
  be in the hundreds** if the key's recall problem were fixed — which is a different, and better,
  finding than "the market is thin."
- **Phase 3's annotation set is not blocked by the 94 number** (Q4): both the hard-negative supply
  and a broader (non-key) positive-candidate search comfortably support 800–1,000 pairs today.

This is a diagnostic report only. No key change, no gate change, no code change, no ADR was made in
this session — per instruction.

---

## 2026-09-13 — independent verification of the Q3 sample

Recorded as fact, not re-derived in this session:

- All 27 claimed matches in `docs/learned/q3-verification.md` were opened and checked by hand
  against the live shops. 26 confirmed genuine, 1 rejected (#13, a title/URL mismatch on the
  petmax side — the URL slug names a different Calibra product than the title and price actually
  served). Precision approximately 96%.
- Line-level traps were checked specifically and did not occur: Hill's Adult vs Puppy, Royal Canin
  Digestive Care 10kg, Brit Premium Cat Sensitive 8kg, Brit Care Sustainable Sensitive 1kg, Petkult
  Sensitive Care Small Breed 1kg, Royal Canin Kitten in gravy 85g.
- A spot-check of 3 rows from Table 2 ("no match") found one false negative: #22 Calibra Dog Life
  Adult Small Fresh Beef 6 kg does exist on pentruanimale.ro with a 6kg variant. Therefore the 54%
  true-match rate is a floor, not a ceiling.
- Implication, stated as an estimate: at 52% confirmed over 2,329 keyable petmax food listings,
  true cross-shop overlap is on the order of **1,200 products, roughly 3x the 400 gate.**
