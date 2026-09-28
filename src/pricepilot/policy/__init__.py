"""Phase 5 decision-engine guardrails (CLAUDE.md section 6): thresholds live in one config,
read by a Python guard that is the final deterministic authority over an LLM's price proposal.
"""

from __future__ import annotations
