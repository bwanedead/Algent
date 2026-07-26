"""
The profile task message — the selected signal vector handed to the research agent.

The system prompt (``prompts.py``) is fixed doctrine; this renders the one **vector**
to investigate into the run's task message: its thesis, the questions to resolve, and
the t0 grounding the synthesis agent already surfaced (supporting hit ids + any source
URLs) so research starts from real footing.
"""

from __future__ import annotations

from typing import Any

from .x_seeds import is_x_url


def build_vector_message(vector: dict[str, Any]) -> str:
    """Render a selected signal vector (a ResearchVector dict) into the task message."""
    x_seeds = [str(u) for u in (vector.get("x_seed_urls") or []) if u]
    if not x_seeds:
        x_seeds = [str(u) for u in (vector.get("sources") or []) if is_x_url(str(u))]
    x_primary = bool(vector.get("x_primary")) or bool(x_seeds) or any(
        str(h).startswith("x:") for h in (vector.get("supporting_hits") or [])
    )

    lines = [
        "# YOUR ASSIGNMENT — research this signal vector into a signal profile (t2)",
        "",
        f"vector_id: {vector.get('id', '?')}",
        f"title: {vector.get('title', '')}",
        f"type: {vector.get('vector_type', '?')}   suggested effort: {vector.get('research_effort', '?')}",
        f"pillars: {', '.join(vector.get('pillars', [])) or '-'}   "
        f"scope: {', '.join(vector.get('scope', [])) or '-'}",
        f"x_primary: {x_primary}",
        "",
        f"THESIS: {vector.get('thesis', '')}",
        f"WHY IT MATTERS: {vector.get('rationale', '')}",
        "",
        "KEY QUESTIONS TO RESOLVE:",
        *(f"  - {q}" for q in vector.get("key_questions", []) or ["(none specified — define your own)"]),
        "",
        f"t0 supporting hit ids: {', '.join(vector.get('supporting_hits', [])) or '-'}",
        "SEED SOURCES (from synthesis / t0 — verify, don't trust blindly):",
        *(f"  - {u}" for u in vector.get("sources", []) or ["(none — find your own)"]),
        "",
    ]
    if x_primary or x_seeds:
        lines += [
            "# X PRIMARY FOOTING (structural duty — not optional garnish)",
            "This vector is X-linked (supporting hit and/or seed post URL). Prestige wires alone "
            "are a failure mode for this assignment.",
            "You MUST, before finishing the profile (unless paid X budget is refused):",
            "  1) deep-read at least one X URL below via web_search(read_url=...) — the post is "
            "    first-party what-was-said;",
            "  2) run at least one web_search(query=..., source=\"x\") for related first-party / "
            "    official / OSINT posts on this story;",
            "  3) put load-bearing X posts into the source_ledger (source_type primary when the "
            "    account owns the statement) and ground claims accordingly.",
            "X SEED POST URLs:",
            *(f"  - {u}" for u in x_seeds or ["(reconstruct from supporting hit / find via source=x)"]),
            "",
        ]
    lines.append(_DIRECTIVE)
    return "\n".join(lines)


_DIRECTIVE = (
    "TASK: Build this vector's signal profile. Search free-first and READ the sources "
    "you cite. Construct the source ledger and the claim ledger (atomic, graded claims "
    "traced to sources by id) — that is the core. Map the landscape: competing "
    "interpretations, omissions, open questions. "
    "REQUIRED: fill countries_of_relevance with where this story HAPPENS and who it AFFECTS "
    "(iso2 + name; primary setting first — not every nation mentioned). "
    "The country of an institution that published, reported, funded or operated something is "
    "NOT a place of relevance: a European agency's image of Mars is not a story about Europe, "
    "and a Reuters dispatch from Beijing is not a story about the United Kingdom. These become "
    "the flags a reader sees beside the headline, so they must answer 'where in the world is "
    "this' — if the honest answer is nowhere on Earth (space, the deep ocean, a mathematical "
    "result, a purely online phenomenon), leave the list EMPTY rather than reaching for the "
    "home country of whoever announced it. "
    "If x_primary is true or X seed URLs are listed, fulfill the X PRIMARY FOOTING duties "
    "above so the profile is not wire-only. "
    "Flag (don't compute) analytics needs. "
    "Add derived_leads for adjacent stories. Set an honest profile_status — "
    "insufficient_evidence is a valid result. Return a SignalProfile."
)
