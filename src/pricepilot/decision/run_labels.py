"""Run labels shared by the dashboard, the decision runner and the action layer.

A module of its own so the read-only API can use the label without importing the decision engine
(and, through it, the embedding / RAG path): the serving image ships none of that stack.
"""

from __future__ import annotations

# Rows replaced by a later run are relabelled (never deleted); they must never be acted on.
SUPERSEDED_RUN_LABEL = "s5-superseded"
