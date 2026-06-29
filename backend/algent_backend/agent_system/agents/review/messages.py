"""
The review task message — the profile under review, as the reviewer should see it.

Two inputs stitched together: the deterministic **briefing** (the holistic, drillable
view — the reviewer is its first real consumer) and a compact block of **machine grounding
signals** the harness already computes (deep-read coverage of high-salience claims, source
concentration, weakly-grounded threads). The model brings the semantic judgment on top.
"""

from __future__ import annotations

from collections import Counter

from algent_backend.agent_system.agents.research.briefing import render_briefing
from algent_backend.agent_system.agents.research.profile import SignalProfile


def build_review_message(profile: SignalProfile) -> str:
    return "\n".join([
        f"# PROFILE UNDER REVIEW — {profile.id}  (status: {profile.profile_status})",
        "",
        "## Machine grounding signals (computed, trust these)",
        *_grounding_signals(profile),
        "",
        "## Briefing (the profile as a consumer reads it)",
        "",
        render_briefing(profile),
        "",
        "TASK: Review this profile for soundness, completeness, and reliability. Emit a "
        "ReviewReport — targeted findings (cite claim/thread/source ids), a verdict, and the "
        "enrichment lanes to run, in priority order. Be specific to THIS profile.",
    ])


def _grounding_signals(profile: SignalProfile) -> list[str]:
    claims = profile.claim_ledger
    high = [c for c in claims if c.salience == "high"]
    high_weak = [c for c in high if c.grounding != "snapshotted"]
    deep_sources = sum(1 for s in profile.source_ledger if s.snapshot is not None)
    pubs = Counter((s.publisher or s.url or "?") for s in profile.source_ledger)
    top_pub, top_n = (pubs.most_common(1)[0] if pubs else ("-", 0))
    weak_threads = [t for t in profile.threads if t.salience == "high" and t.grounding != "snapshotted"]
    return [
        f"- claims: {len(claims)} ({len(high)} high-salience); "
        f"deep-read sources: {deep_sources}/{len(profile.source_ledger)}",
        f"- HIGH-salience claims NOT deep-read (snippet/unsourced): {len(high_weak)}"
        + (f" -> {', '.join(c.id for c in high_weak)}" if high_weak else ""),
        f"- source concentration: top source '{str(top_pub)[:30]}' = {top_n}/{len(profile.source_ledger)}",
        f"- high-salience threads that are weakly grounded: "
        f"{', '.join(t.id for t in weak_threads) or 'none'}",
        f"- omissions noted: {len(profile.omissions)} | open questions: {len(profile.open_questions)} | "
        f"analytics flags: {len(profile.data_notes) + len(profile.visual_opportunities)}",
    ]
