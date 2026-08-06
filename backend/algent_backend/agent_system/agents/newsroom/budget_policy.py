"""
Newsroom policy for what is optional once the article soft cap is crossed.

The foundation ledger owns mode (normal / slim_finish / hard_stop) and hard refusal.
This module owns which *newsroom-orchestrated* operations are optional in slim_finish.
Tool-layer slim gates (rich / X / search fallback) live in research.py — tools must not
depend on this module.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.foundation import cost

# Ops the rail/editorial/gauntlet may skip after soft cap. Tool paid channels are gated
# inside research.py via cost.is_slim() / is_hard_stop().
# Note: analytics PLANNING is cheap and is not listed here — the pipeline runs the router
# early. Analytics WORKER fulfillment is gated via select_analytics_requests().
SLIM_OPTIONAL_OPS = frozenset({
    "enrich_lane",
    "gauntlet_rereview",
    "treatment_review",
    "treatment_revise",
    "caveat_check",
    "draft_repair",
    "analytics",              # non-essential worker fulfillment
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


def select_analytics_requests(
    requests: list[dict[str, Any]], *, cap: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pick which visual requests to fulfill under the current budget mode.

    Returns ``(keep, skipped)``. Normal mode keeps up to ``cap``. Slim finish keeps at most
    one ``essential_context`` request; everything else is marked soft_cap_skipped.
    """
    if cost.is_hard_stop():
        cost.record_skip("analytics", "hard_stop")
        return [], [{**r, "status": "skipped", "note": "hard_stop"} for r in requests]
    if cost.mode() == "slim_finish":
        essential = [r for r in requests
                     if str(r.get("priority") or "") == "essential_context"]
        if not essential:
            cost.record_skip("analytics", "slim_finish")
            return [], [{**r, "status": "soft_cap_skipped"} for r in requests]
        keep = essential[:1]
        keep_id = str(keep[0].get("id") or "")
        skipped = [
            {**r, "status": "soft_cap_skipped"}
            for r in requests if str(r.get("id") or "") != keep_id
        ]
        return keep, skipped
    n = max(0, cap)
    keep = list(requests[:n])
    skipped = [{**r, "status": "skipped"} for r in requests[n:]]
    return keep, skipped
