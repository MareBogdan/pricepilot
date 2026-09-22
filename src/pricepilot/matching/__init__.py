"""Phase 3 matching harness — model-agnostic building blocks shared by both the classical
cross-encoder baseline and the LoRA fine-tune (CLAUDE.md §7 items 5-6; ADR-0028 addendum #19).

Nothing in this package imports a model library (`sentence-transformers`, `torch`,
`transformers`) or makes a network call — it exists to build a fair, identical input for
whichever model scores it, not to run one.
"""

from __future__ import annotations
