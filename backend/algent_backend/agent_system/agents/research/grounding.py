"""
The deep-read grounding floor — ONE canonical definition, used at every layer.

"Load-bearing" = high salience. The floor: a load-bearing claim (or thread) must rest on a
source we actually DEEP-READ (``grounding == "snapshotted"``), not a search snippet. Snippets
are fragile; deep reads carry the exact figure/quote and the context that keeps us honest.

This rule was duplicated ad-hoc across the briefing, the reviewer message, and (implicitly) the
drafter. Centralizing it here means the research layer, the profile status, and the draft
citation harness all judge grounding IDENTICALLY — so "avoid snippets on anything that matters"
is enforced the same way everywhere. Pure + deterministic: no model, no cost.
"""

from __future__ import annotations

from .profile import Claim, ProfileStatus, SignalProfile, Thread

# Statuses that assert the profile is trustworthy/finished — a load-bearing gap must not coexist
# with these, so the deterministic floor caps them down.
_MATURE_STATUSES: frozenset[str] = frozenset({"mature", "complete"})


def is_deep_read(grounding: str) -> bool:
    """The floor's atom: a source/claim is deep-read iff it is snapshotted."""
    return grounding == "snapshotted"


def weak_load_bearing_claims(claims: list[Claim]) -> list[Claim]:
    """High-salience claims NOT backed by a deep-read source (the floor violations)."""
    return [c for c in claims if c.salience == "high" and not is_deep_read(c.grounding)]


def weak_load_bearing_threads(threads: list[Thread]) -> list[Thread]:
    """High-salience threads whose grounding is thin (their weakest claim is not deep-read)."""
    return [t for t in threads if t.salience == "high" and not is_deep_read(t.grounding)]


def meets_grounding_floor(claims: list[Claim], threads: list[Thread]) -> bool:
    """True iff every load-bearing claim and thread is deep-read."""
    return not weak_load_bearing_claims(claims) and not weak_load_bearing_threads(threads)


def cap_status_by_grounding(
    status: ProfileStatus, claims: list[Claim], threads: list[Thread]
) -> ProfileStatus:
    """Deterministic floor at the profile layer: a profile may not CLAIM maturity/completeness
    while a load-bearing claim or thread is only snippet-grounded. Cap such a status down to
    ``needs_verification`` regardless of what the model asserted — the model reasons, the harness
    guarantees the floor."""
    if status in _MATURE_STATUSES and not meets_grounding_floor(claims, threads):
        return "needs_verification"
    return status


def grounding_gap(profile: SignalProfile) -> dict[str, list[str]]:
    """A compact, machine-readable report of the floor violations on a profile (claim + thread
    ids that are load-bearing but not deep-read). Empty lists mean the floor is met."""
    return {
        "weak_claims": [c.id for c in weak_load_bearing_claims(profile.claim_ledger)],
        "weak_threads": [t.id for t in weak_load_bearing_threads(profile.threads)],
    }
