# CLAUDE.md lines superseded 2026-09-25 (ADR-0030), verbatim before editing

L184:
| **1** | VPS hosting, three months | **~$15** | yes, once, at Phase 7 — CX22 no longer sold; CX23 pricing per `docs/phase3-serving-prices.md`, re-check the reserve then |

L185:
| **2** | Recommendation generation, Phase 5 | $5–8 | yes |

L214:
**Deployment target (decided):** a single Hetzner CX22 VPS (~€4/month), Docker Compose, **Caddy** as reverse proxy for automatic HTTPS. Not Kubernetes, not a PaaS. The user has not deployed to a VPS before — explain each step: SSH keys, firewall, domain DNS, systemd unit, backups.

L216:
Note (2026-09-24): CX22 is no longer sold; see `docs/phase3-serving-prices.md`. The serving model decision is re-taken at the Phase 3 audit (`docs/learned/phase3-serving-benchmark.md`).

L218:
**Model serving (decided):** the fine-tuned 0.5B matching model runs **quantized on CPU on the same VPS**, in real time. This is a deliberate architectural choice and one of the strongest selling points of the project. Phase 3 must produce a benchmark table comparing the local model against a large hosted API model on: accuracy, p50/p95 latency, and cost per 1,000 comparisons. If CPU latency proves unworkable, fall back to nightly batch inference — but measure first, and record the measurement either way.

L320:
Full dockerization. Deployment to a Hetzner CX22 behind Caddy, on a real domain, walked through step by step with the user — this is new territory for him, so explain SSH hardening, firewall rules, DNS, volumes and database backups as you go, and write `docs/DEPLOYMENT.md` as you do it.

