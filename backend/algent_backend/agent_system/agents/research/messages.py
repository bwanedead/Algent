"""
The profile task message — the selected signal vector handed to the research agent.

The system prompt (``prompts.py``) is fixed doctrine; this renders the one **vector**
to investigate into the run's task message: its thesis, the questions to resolve, and
the t0 grounding the synthesis agent already surfaced (supporting hit ids + any source
URLs) so research starts from real footing.
"""

from __future__ import annotations

from typing import Any


def build_vector_message(vector: dict[str, Any]) -> str:
    """Render a selected signal vector (a ResearchVector dict) into the task message."""
    lines = [
        "# YOUR ASSIGNMENT — research this signal vector into a signal profile (t2)",
        "",
        f"vector_id: {vector.get('id', '?')}",
        f"title: {vector.get('title', '')}",
        f"type: {vector.get('vector_type', '?')}   suggested effort: {vector.get('research_effort', '?')}",
        f"pillars: {', '.join(vector.get('pillars', [])) or '-'}   "
        f"scope: {', '.join(vector.get('scope', [])) or '-'}",
        "",
        f"THESIS: {vector.get('thesis', '')}",
        f"WHY IT MATTERS: {vector.get('rationale', '')}",
        "",
        "KEY QUESTIONS TO RESOLVE:",
        *(f"  - {q}" for q in vector.get("key_questions", []) or ["(none specified — define your own)"]),
        "",
        f"t0 supporting hit ids: {', '.join(vector.get('supporting_hits', [])) or '-'}",
        "SEED SOURCES (from synthesis — verify, don't trust blindly):",
        *(f"  - {u}" for u in vector.get("sources", []) or ["(none — find your own)"]),
        "",
        _DIRECTIVE,
    ]
    return "\n".join(lines)


_DIRECTIVE = (
    "TASK: Build this vector's signal profile. Search free-first and READ the sources "
    "you cite. Construct the source ledger and the claim ledger (atomic, graded claims "
    "traced to sources by id) — that is the core. Map the landscape: competing "
    "interpretations, omissions, open questions. Flag (don't compute) analytics needs. "
    "Add derived_leads for adjacent stories. Set an honest profile_status — "
    "insufficient_evidence is a valid result. Return a SignalProfile."
)
