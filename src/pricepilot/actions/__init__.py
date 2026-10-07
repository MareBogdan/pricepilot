"""Phase 6 action layer (ADR-0047): turn a guard-decided recommendation into a logged, reversible,
human-approved action on the store. The guard stays the only authority over WHAT price may be applied;
this package only decides whether to write it, asks a human, writes it, and records it.
"""
