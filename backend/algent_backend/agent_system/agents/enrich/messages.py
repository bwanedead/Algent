"""
The enrichment task message — the assignment (the lane's findings) + the current profile.

The enricher reads the review findings as concrete assignments and the existing profile's
briefing as context (so it can link new evidence to existing claim/source/thread ids).
"""

from __future__ import annotations

from algent_backend.agent_system.agents.research.briefing import render_briefing
from algent_backend.agent_system.agents.research.profile import SignalProfile


def build_enrich_message(profile: SignalProfile, findings: list, lane: str) -> str:
    lines = [
        f"# ENRICHMENT ASSIGNMENT — lane: {lane}",
        "You are improving an EXISTING profile. Address ONLY the findings below, by ADDING new",
        "evidence — do not rewrite or remove what's already there.",
        "",
        "## Findings to address",
    ]
    for f in findings:
        lines.append(f"- [{f.severity}] target {f.target}: {f.explanation}")
        if f.recommended_enrichment:
            lines.append(f"    do: {f.recommended_enrichment}")
        if f.suggested_search_direction:
            lines.append(f"    lead: {f.suggested_search_direction}")
        lines.append(f"    (finding id: {f.id})")
    lines += [
        "",
        "## Current profile (reference existing `clm_...` / `src_...` / `thr_...` ids to link your additions)",
        "",
        render_briefing(profile),
        "",
        _DIRECTIVE,
    ]
    return "\n".join(lines)


_DIRECTIVE = (
    "TASK: Research the assignments. Find AUTHORITATIVE / PRIMARY sources, DEEP-READ them "
    "(read_url), and return ProfileAdditions: new sources (the urls you actually read), new or "
    "re-grounded claims (graded, traced to your new sources by local id), and any supporting "
    "threads. You MAY reference existing claim/source ids (shown in the briefing) to link or "
    "corroborate. Additive only — never rewrite existing items. List the finding ids you addressed."
)
