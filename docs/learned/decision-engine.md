# Decision engine (Phase 5, sessions 4-5)

**What it does.** For one product it gathers numbers from SQL, retrieves policy passages (RAG), builds a
prompt, asks a *proposer* for a price + rationale, parses the reply, runs the deterministic guard, and
stores a full trace row (`recommendations`).

**The decision that mattered: the proposer is a seam.** Session 4 used a deterministic mock; session 5
swapped in `client.complete`. Prompt-building and parsing are the same in both, so the mock proved the
wiring for $0 and the real run changed one object.

**RAG vs numbers.** Policy *text* is what RAG is for. Every number the model sees (floor, daily cap, stock
minimum) is read from `config/pricing-policy.toml`; retrieved text is labelled reference-only, and a test
plants "99%" in a passage to prove it never reaches the facts.

**The guard is the authority.** The model's price only leaves `decide()` through `enforce()`. Since
ADR-0043 charm rounding also keeps the move's direction (it used to turn +3% into -4% on a 5 RON item).

**What broke in the real run (ADR-0044).** `claude-sonnet-5` thinks before answering. At `max_tokens=400`,
4 of 50 replies were cut off: three empty (FLAG), one cut mid-sentence and accepted. A truncated "12.50"
can parse as "12.5", so the trace now records `stop_reason` and any `max_tokens` reply is FLAGged.
Charm rounding can also push an in-cap -5% proposal just over the cap (2 FLAGs).

**Honest limits.** Gate result: 50 rows, 0 margin violations, $0.24. But 42 of 45 APPROVEs keep the
price and 0 of 20 hypothetical scenarios moved it, so the live run is weak evidence for the floor; the
guard's tests and sweeps carry that claim. Elasticity is a value-less placeholder; `price_7d_ago` is
synthetic; scenario competitor prices are hypothetical.
