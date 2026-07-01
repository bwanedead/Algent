"""
The deep-read grounding floor — ONE canonical definition, used at every layer.

The principle: **snippets are for discovery, deep reads are for persistence.** A search snippet
is a reconnaissance tool — scan the landscape, find what matters. But by the time we PERSIST
meaning — write a claim into the ledger, enrich stable knowledge — the source should have been
read in full. A *consequential* claim (high or medium salience) that rests only on a snippet is
a floor violation: half-digested evidence that shouldn't have been persisted. Only genuinely
peripheral, low-salience context may remain at snippet level (the residue of scouting).

This rule was duplicated ad-hoc across the briefing, the reviewer message, and (implicitly) the
drafter. Centralizing it here means the research layer, the profile status, and the draft
citation harness all judge grounding IDENTICALLY. Pure + deterministic: no model, no cost.
"""

from __future__ import annotations

from .profile import Claim, ProfileStatus, SignalProfile, Thread

# Statuses that assert the profile is trustworthy/finished — a grounding gap must not coexist
# with these, so the deterministic floor caps them down.
_MATURE_STATUSES: frozenset[str] = frozenset({"mature", "complete"})
# "Consequential" = worth persisting on real evidence. Low-salience is inconsequential scouting
# residue where a snippet is tolerable; high/medium must be deep-read before it persists.
_CONSEQUENTIAL: frozenset[str] = frozenset({"high", "medium"})


def is_deep_read(grounding: str) -> bool:
    """The floor's atom: a source/claim is deep-read iff it is snapshotted."""
    return grounding == "snapshotted"


def is_consequential(salience: str) -> bool:
    """Consequential = high or medium salience (only low-salience context may stay snippet)."""
    return salience in _CONSEQUENTIAL


def weak_load_bearing_claims(claims: list[Claim]) -> list[Claim]:
    """Consequential (high/medium) claims NOT backed by a deep-read source — the floor violations
    (a snippet-derived claim that got persisted anyway)."""
    return [c for c in claims if is_consequential(c.salience) and not is_deep_read(c.grounding)]


def weak_load_bearing_threads(threads: list[Thread]) -> list[Thread]:
    """Consequential threads whose grounding is thin (their weakest claim is not deep-read)."""
    return [t for t in threads if is_consequential(t.salience) and not is_deep_read(t.grounding)]


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
