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
    "clear, defensible ranking beats hedging. Give each choice a score and a short "
    "rationale grounded in the candidate's own signals, and never invent candidates or "
    "facts not present in what you were given.\n"
    "COOLDOWN is semantic judgment only: you receive recent published headlines; for "
    "each candidate you decide whether it is the same story-family (too similar for the "
    "reader). There is no lexical matcher after you — flag cooldown honestly."
)


def build_router_system_prompt(brief: RoutingBrief) -> str:
    """Compose the router's identity, specialized by the injected brief."""
    scope = (
        f"Return ALL {brief.candidate_kind} ranked best-first (full list)."
        if brief.rank_all
        else f"Return the best up to {brief.top_k} (fewer if fewer qualify), ranked best-first."
    )
    assignment = (
        "YOUR ROUTING ASSIGNMENT\n"
        f"Role: {brief.role}\n"
        f"You are ranking: {brief.candidate_kind}\n"
        f"Select for: {brief.selecting_for}\n"
        f"What happens next: {brief.downstream}\n"
        f"{scope}\n"
        "For EVERY candidate you return: score (0-100), one-line rationale, and "
        "cooldown=true/false (true = same story-family as something in ALREADY COVERED)."
    )
    return compose_system_prompt(UNIVERSAL_AGENT_BASE, NEWSROOM_SYSTEM_MAP, ROUTER_BASE, assignment)


def build_router_message(
    candidates: list[RouteCandidate],
    brief: RoutingBrief,
) -> str:
    """Render the candidates + recent headlines + ranking directive into the task message."""
    n = len(candidates)
    scope = (
        f"Rank ALL {n} candidates best-first (do not omit any id)."
        if brief.rank_all
        else f"Rank the best up to {brief.top_k} by the assignment's criteria."
    )
    lines = ["# CANDIDATES TO RANK", f"count: {n}", ""]
    lines.extend(_fmt(c) for c in candidates)
    if brief.recent:
        lines += [
            "",
            "# ALREADY COVERED — recent published headlines (cooldown reference)",
            "Judge SEMANTICALLY — not keyword matching. Same story-family = same place, "
            "institution, conflict thread, person-event, or named development a reader "
            "would recognise as 'we already wrote that'.",
            *[f"- {when[:10]}  {title}" for when, title in brief.recent],
            "",
            "For each candidate set cooldown=true if it is too similar to any of these "
            "(reframe, new angle, updated figures, or restating an open question on the "
            "same development still counts as same family). Set cooldown=false if it is "
            "a genuinely different story. Put cooldown_reason as the matching prior title "
            "(or short why) when cooldown=true.",
            "A REFRAME IS NOT A NEW STORY. Prefer different stories for high ranks among "
            "cooldown=false items. Score still reflects quality even when cooldown=true "
            "(cooled items stay in the list for audit; they will not promote).",
        ]
    else:
        lines += [
            "",
            "# ALREADY COVERED — none loaded (no recent site headlines available)",
            "Set cooldown=false for all unless you know of no other reason.",
        ]
    lines.extend([
        "",
        f"TASK: {scope}",
        "For each: candidate_id (exactly as shown), rank (1=best), score (0-100), "
        "rationale (one line), cooldown (bool), cooldown_reason (string, empty if false).",
        "Order choices best-first by score/fitness among all items (cooldown does not "
        "remove them — only flags them).",
    ])
    return "\n".join(lines)


def _fmt(c: RouteCandidate) -> str:
    sig = " ".join(f"{k}={v}" for k, v in (c.signals or {}).items() if v not in (None, "", False))
    tags = ",".join(c.tags) or "-"
    return f"[{c.id}] {c.label}\n    {c.summary[:280]}\n    tags={tags}  {sig}"
