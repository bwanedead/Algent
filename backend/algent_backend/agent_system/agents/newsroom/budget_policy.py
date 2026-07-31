"""
Newsroom policy for what is optional once the article soft cap is crossed.

The foundation ledger owns mode (normal / slim_finish / hard_stop) and hard refusal.
This module owns *which* newsroom operations are optional in slim_finish — so the
budget layer stays mechanical and newsroom policy stays domain-owned.
"""

from __future__ import annotations

from algent_backend.agent_system.foundation import cost

# Billable ops that slim_finish must not initiate. Essential finish ops
# (initial draft, headline, required hero) pass essential=True at reserve time.
SLIM_OPTIONAL_OPS = frozenset({
    "enrich_lane",
    "draft_repair",
    "analytics",
    "comprehension_repair",
    "advisory_review",
    "search_fallback",
    "rich",
    "x",
    "semantic_extra",
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


def essential_billable_ok() -> bool:
    """True while a finish-path essential op may still reserve under the hard cap."""
    return not cost.is_hard_stop() or cost.remaining_usd() > 0
