# Phase 3 serving benchmark: price inputs

Retrieved 2026-09-23. Every figure below comes from the fetched page named beside it. Anything I could not confirm on a fetched page is marked UNVERIFIED.

## 1. Anthropic API (USD per million tokens, MTok)

Source: https://platform.claude.com/docs/en/about-claude/pricing (the docs.anthropic.com URL 301-redirects here), and https://platform.claude.com/docs/en/about-claude/models/overview for IDs. Retrieved 2026-09-23.

| Class | Model | API ID (pinned) | Input | Output | Batch in/out |
|---|---|---|---|---|---|
| Sonnet | Claude Sonnet 5 | `claude-sonnet-5` | $2 | $10 | $1 / $5 |
| Haiku | Claude Haiku 4.5 | `claude-haiku-4-5-20251001` (alias `claude-haiku-4-5`) | $1 | $5 | $0.50 / $2.50 |

- Sonnet 5 note: $2/$10 was introductory pricing through 2026-08-31. The pricing page footnote says it is now the standard price, and the scheduled rise to $3/$15 will not occur. The previous Sonnet 4.6 costs $3/$15.
- Discounts exist. Batch API is 50% off input and output. Prompt-cache reads cost 0.1x base input. 5-minute cache writes cost 1.25x, and 1-hour writes cost 2x. These stack.
- Sonnet 5 and Haiku 4.5 use different tokenizers. The page says Claude 4.7 and later models produce about 30% more tokens for the same text. The Sonnet 5 token count for the same text may be higher than Haiku 4.5's. Count tokens per model; do not reuse one count. The 30% is Anthropic's approximate figure, not measured here.

## 2. Hetzner Cloud

| Item | Value | Source |
|---|---|---|
| CX22 sold for new servers? | No. CX22 does not appear in Hetzner's current cost-optimized plan list or price-adjustment tables. | https://www.hetzner.com/cloud/cost-optimized and https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/ (both 2026-09-23) |
| Successor named on Hetzner's own pages | CX23: 2 vCPU, 4 GB RAM, 40 GB NVMe. Same specs as the 2024 CX22 launch (https://www.hetzner.com/pressroom/new-cx-plans/). | cost-optimized page, 2026-09-23 |
| "CX23 replaced CX22" wording | UNVERIFIED on a Hetzner page. It appears only in a third-party search summary. Hetzner's page shows CX23 with matching specs and no CX22. | WebSearch result, not a fetched Hetzner page |
| CX23 price before 2026-06-15 | EUR 0.0064/h, EUR 3.99/month | price-adjustment page |
| CX23 price now (new orders from 2026-06-15, 8 AM CEST) | **EUR 0.0088/h, EUR 5.49/month** | price-adjustment page |
| VAT | All prices EXCLUDING VAT. Also excluding IPv4. | price-adjustment page |
| Location | The price-adjustment page is headed Germany/Finland. The cost-optimized page lists EU-central: NBG1 (Nuremberg) and HEL1 (Helsinki). | both pages |
| Availability today | The cost-optimized page shows "This product is currently unavailable" for CX23 in all locations, including CX33, CX43 and CX53. | https://www.hetzner.com/cloud/cost-optimized, 2026-09-23 |
| CX22 price at launch (historical) | EUR 3.79/month | https://www.hetzner.com/pressroom/new-cx-plans/ (2024-06-06) |

Note: CLAUDE.md budgets "CX22 ~EUR 4/mo". The current CX23 is EUR 5.49/month excluding VAT. VAT and IPv4 cost are not included, and the VAT rate for this project is UNVERIFIED. Also, the plan is unavailable to order right now.

## 3. EUR to USD

| Item | Value | Source |
|---|---|---|
| ECB reference rate, 1 EUR in USD | **1.1411** | https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml, rate dated 2026-09-23, retrieved 2026-09-23 |
| Previous day (cross-check) | 1.1463 on 2026-09-22 | https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/eurofxref-graph-usd.en.html |

## Figures to use (item 8 cost formula)

| Input | Value | Source section |
|---|---|---|
| Sonnet 5 input, $/MTok | 2.00 | 1 |
| Sonnet 5 output, $/MTok | 10.00 | 1 |
| Haiku 4.5 input, $/MTok | 1.00 | 1 |
| Haiku 4.5 output, $/MTok | 5.00 | 1 |
| VPS (CX23) EUR/hour, excl. VAT | 0.0088 | 2 |
| EUR to USD | 1.1411 (ECB, 2026-09-23) | 3 |
| VPS USD/hour | 0.0088 x 1.1411 = **0.010042** (about $0.0100/h) | derived |

Cross-check: Hetzner's own USD column lists $0.0104/h. That is Hetzner's USD price list, which may use a different rate. Use 0.010042 for consistency with the ECB rate, and say so in the results table.
