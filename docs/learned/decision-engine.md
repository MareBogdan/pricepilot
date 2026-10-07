# Decision engine (Phase 5, session 4)

**What it does.** For one product it gathers numbers from SQL (our cost/price/stock, matched
competitor prices, our price 7 days ago), retrieves the relevant policy passages (RAG), builds a
prompt, asks a *proposer* for a price + rationale, parses the reply, runs the deterministic guard,
and stores a full trace row (`recommendations`).

**The decision that mattered: the proposer is a seam.** Session 4 used a deterministic mock;
session 5 swaps in `client.complete`. Prompt-building and parsing are real in both, so the mock
proves the wiring end to end for $0 and the real run only changes one object.

**Why RAG is where it is.** Policy *text* (why margins differ, when not to discount) is what RAG is
for. Every *number* the model sees (floor, daily cap, stock minimum) is read from
`config/pricing-policy.toml`, and the retrieved text is labelled "reference only". A test plants
"99%" in a retrieved passage and checks it never reaches the facts. Retrieving a number by
similarity is the bug an interviewer looks for.

**The guard is the authority.** The model's price never leaves `decide()` except through
`enforce()`. Below-floor proposal -> the guard lifts it to a floor-safe value, then the 5% daily
cap FLAGs it. No stock -> REJECT. Garbled reply -> FLAG with no price at all.

**What would break it.** (1) Prose and TOML drifting apart -- a drift test now fails on it.
(2) The model citing a stale number from the passages -- mitigated, not eliminated, by the label.
(3) `charm_round` picks the *nearest* charm value, so on cheap items it can flip a proposal's
direction (5.20, proposed 5.36, approved 4.99). Not a margin violation, but it contradicts the
rationale. Logged in ADR-0042.

**Honest limits.** Elasticity is a value-less placeholder (Phase 4 postponed). `price_7d_ago` is the
mock store's synthetic history. Mock rows (`is_mock = true`) are wiring evidence, never results.
No measured quality number exists yet; that is session 5.
