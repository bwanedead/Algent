"""
Router prompts — the generic router identity, specialized at runtime by a brief.

System prompt layers (broad -> specific), composed with the shared assembler:
  universal agent base  ->  newsroom system map  ->  router base  ->  this brief.
The first three are fixed; the brief block is rendered from the injected
``RoutingBrief`` so the same engine speaks for whatever routing job it's given.
"""

from __future__ import annotations

from algent_backend.agent_system.agents.newsroom_map import NEWSROOM_SYSTEM_MAP
from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

from .contracts import RouteCandidate, RoutingBrief

ROUTER_BASE = (
    "You are a routing agent. You rank a set of candidates against an assignment and "
    "select the best — you do NOT produce the downstream work yourself; you decide "
    "what advances and in what order. Rank honestly on the assignment's criteria: a "
    "clear, defensible ranking beats hedging. Give each choice a score and a one-line "
    "rationale grounded in the candidate's own signals, and never invent candidates or "
    "facts not present in what you were given."
)


def build_router_system_prompt(brief: RoutingBrief) -> str:
    """Compose the router's identity, specialized by the injected brief."""
    assignment = (
        "YOUR ROUTING ASSIGNMENT\n"
        f"Role: {brief.role}\n"
        f"You are ranking: {brief.candidate_kind}\n"
        f"Select for: {brief.selecting_for}\n"
        f"What happens next: {brief.downstream}\n"
        f"Return the best up to {brief.top_k} (fewer if fewer qualify), ranked best-first."
    )
    return compose_system_prompt(UNIVERSAL_AGENT_BASE, NEWSROOM_SYSTEM_MAP, ROUTER_BASE, assignment)


def build_router_message(
    candidates: list[RouteCandidate], top_k: int,
    recent: tuple[tuple[str, str], ...] = (),
) -> str:
    """Render the candidates + any cooldown + the ranking directive into the task message."""
    lines = ["# CANDIDATES TO RANK", f"count: {len(candidates)}", ""]
    lines.extend(_fmt(c) for c in candidates)
    if recent:
        lines += [
            "",
            "# ALREADY COVERED — COOLDOWN (what we published recently)",
            *[f"- {when[:10]}  {title}" for when, title in recent],
            "",
            "Do NOT rank #1 any candidate in the same STORY-FAMILY as one of these — same place, "
            "product, conflict, institution, person, or named event. The pool over-represents "
            "whatever is dominating coverage; re-picking it gives the reader a piece they have "
            "effectively already read. Prefer a genuinely different story.",
            "A REFRAME IS NOT A NEW STORY. A new angle, a broader campaign label, updated figures "
            "on the same development, or restating an unresolved question already in this list is "
            "the SAME development for the reader — demote it. A material exception would need a "
            "fact class the prior pieces could not have stated (new primary actor class, new "
            "theatre, resolved question, genuine delta). If you cannot name that against a "
            "SPECIFIC prior headline, it is not a new story. A mechanical floor also demotes "
            "same-family candidates after you rank — do not fight it by padding rationales.",
        ]
    lines.extend([
        "",
        f"TASK: Rank the best up to {top_k} by the assignment's criteria. For each, return "
        "candidate_id (exactly as shown above), rank (1=best), score (0-100), and a one-line "
        "rationale. Omit clearly unworthy candidates rather than padding the list.",
    ])
    return "\n".join(lines)


def _fmt(c: RouteCandidate) -> str:
    sig = " ".join(f"{k}={v}" for k, v in (c.signals or {}).items() if v not in (None, "", False))
    tags = ",".join(c.tags) or "-"
    return f"[{c.id}] {c.label}\n    {c.summary[:240]}\n    tags={tags}  {sig}"
