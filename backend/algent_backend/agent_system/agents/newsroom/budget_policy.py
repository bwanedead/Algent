"""
Newsroom policy for what is optional once the article soft cap is crossed.

The foundation ledger owns mode (normal / slim_finish / hard_stop) and hard refusal.
This module owns which *newsroom-orchestrated* operations are optional in slim_finish.
Tool-layer slim gates (rich / X / search fallback) live in research.py — tools must not
depend on this module.
"""

from __future__ import annotations

from algent_backend.agent_system.foundation import cost

# Ops the rail/editorial/gauntlet may skip after soft cap. Tool paid channels are gated
# inside research.py via cost.is_slim() / is_hard_stop().
SLIM_OPTIONAL_OPS = frozenset({
    "enrich_lane",
    "draft_repair",
    "analytics",
    "comprehension_repair",
})


def allow_optional(op: str, *, reason: str = "slim_finish") -> bool:
    """False when slim/hard mode should skip this optional op (recorded on ledger)."""
    m = cost.mode()
    if m == "hard_stop":
        cost.record_skip(op, "hard_stop")
        return False
    if m == "slim_finish" and op in SLIM_OPTIONAL_OPS:
        cost.record_skip(op, reason)
        return False
    return True
