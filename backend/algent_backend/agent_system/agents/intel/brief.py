"""
The intelligence brief — what a watch desk produces on a hot theater.

1. COMMISSION: the newsroom's research agent investigates the theater with questions that apply to
   ANY theater (nothing here names a country): what happened in the last 30 days, who is acting on
   whom, what is escalating versus the months before, what classes of target are being hit and what
   else of that class is exposed, what the next rung would look like, what larger contests it sits in.
   The profile lands in the research corpus like any other, and — through the same update path
   articles use — moves the Pulses it bears on. Intel work compounds into the model of the world.
2. ANALYSE: an analyst pass writes the brief from two kinds of evidence kept visibly apart —
   RESEARCHED claims (graded by our research) and REPORTED headlines (other outlets, unverified).
   Facts carry their verification; assessments carry estimative likelihood words and their basis.
"""

from __future__ import annotations

import re
from typing import Any

from .contracts import Brief, Theater

GENERIC_QUESTIONS = (
    "What has happened in this dynamic over the last 30 days? Date every event.",
    "Who are the actors, and what is each doing to whom (strikes, sabotage, coercion, sanctions, "
    "support, negotiation)?",
    "Is it escalating, steady or easing compared with the previous three months — and how fast? "
    "What evidence shows the pace?",
    "What classes of target or asset are being hit or threatened, and what else of that class is "
    "exposed? What would hitting those mean?",
    "What would the next rung of escalation look like, and what observable indicators would come "
    "before it?",
    "What larger contests does this sit inside, and what second-order effects follow for outside "
    "parties (markets, alliances, neighbouring states)?",
)

ANALYST_ROLE = """\
You are the analyst on an intelligence desk writing a brief on one theater for a decision-maker who
needs to understand it fast and act on it. This is not an article: no narrative arc, no scene-setting,
no quotes for colour. Every line earns its place by changing what the reader knows or watches.

TWO KINDS OF EVIDENCE, KEPT APART:
- RESEARCHED claims — graded by our research (confirmed, likely, contested…). These can carry facts.
- REPORTED headlines — what other outlets said, unverified by us. These can carry leads, and must be
  marked `verification: "reported"` wherever they appear in the timeline.
Never upgrade a reported item into a fact. When the only evidence is reported, say so.

FACTS VS ASSESSMENTS. The `situation` and `timeline` are facts with dates and verification. The
`bottom_line`, `escalation.assessment`, `second_order`, `peripheral` and `indicators` are
assessments: use estimative language (almost certain, likely, roughly even, unlikely, remote) and
say what each rests on. Calm is evidence too: if something has NOT happened that would have been
expected, that is worth a line. News over-reports escalation; do not read volume as intensity.

WHAT A GOOD BRIEF HOLDS:
- `bottom_line`: 2–3 sentences — what matters, which way it is moving, how sure we are.
- `timeline`: dated events, most recent last, each with actors, verification and a source URL.
- `relations`: who is doing what to whom — one edge per relationship (kind: strikes, sabotage,
  coerces, sanctions, supports, negotiates, deters, other).
- `escalation`: direction (rising/steady/easing/unclear), pace (fast/gradual/flat) and the
  assessment with its basis, compared with the months before.
- `second_order`: what follows for outside parties, with likelihood and what to watch for.
- `peripheral`: things outside the core that bear on it and should be watched — adjacent target
  classes, neighbouring theaters, supply lines, elections, markets.
- `indicators`: the observable signals that would mark the next rung (status: not seen, emerging,
  observed) and what each would mean.
- `unknowns`: what we cannot establish and would most want to.
- `pulses`: the persistent dimensions this theater bears on, in a few words each.
Plain words a newcomer can follow; no internal jargon.
"""


def commission_research(context: Any, config: Any, theater: Theater) -> dict | None:
    """Research the theater with the generic questions. Returns the profile (also saved to the corpus)."""
    from ..research.spec import build_graph as build_profile

    sources = list(dict.fromkeys(u for m in theater.members for u in m.sources))[:12]
    vector = {
        "id": f"intel_{theater.id.removeprefix('thr_')}"[:60],
        "title": theater.name,
        "thesis": theater.why or theater.description,
        "vector_type": "synthesis",
        "research_effort": "deep",
        "pillars": [theater.domain],
        "scope": [],
        "key_questions": list(GENERIC_QUESTIONS),
        "sources": sources,
        "supporting_hits": [f"{m.edition}#{m.n}" for m in theater.members][:20],
        "rationale": "commissioned by the intel desk: this theater is running hot",
    }
    out = build_profile(context).invoke({"vector": vector}, config)
    profile = out.get("profile")
    return profile if isinstance(profile, dict) and profile.get("id") else None


def _reported(theater: Theater) -> str:
    return "\n".join(f"- ({m.edition[:10]}) {m.title} — {m.thesis[:220]} [sources: {', '.join(m.sources[:2]) or '—'}]"
                     for m in sorted(theater.members, key=lambda m: m.edition))


def write_brief(context: Any, config: Any, theater: Theater, heat: dict, *, profiles: list[dict],
                pulse_lines: list[str], model_spec: Any) -> Brief | None:
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    from ..pulse.seed import evidence_block

    researched, _ids = evidence_block(profiles)
    source_urls = {s.get("id"): s.get("url") for p in profiles for s in p.get("source_ledger") or []}
    task = (f"THEATER: {theater.name}\n{theater.why}\n\n"
            f"HEAT: {heat.get('recent', 0)} headlines in the last 3 days vs {heat.get('prior', 0)} before "
            f"({heat.get('trend', '?')}); first seen {heat.get('first_seen', '?')}.\n\n"
            f"RESEARCHED CLAIMS (graded by our research):{researched or ' none'}\n\n"
            f"SOURCE URLS FOR RESEARCHED CLAIMS: {_compact(source_urls)}\n\n"
            f"REPORTED HEADLINES (other outlets, unverified):\n{_reported(theater)}\n\n"
            + (f"OHMEGA PULSES IN THIS AREA:\n" + "\n".join(pulse_lines) + "\n\n" if pulse_lines else "")
            + "TASK: write the brief.")
    model = context.model_resolver.resolve(model_spec).client.with_structured_output(Brief)
    brief = model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, ANALYST_ROLE)),
                          HumanMessage(content=task)], config=config)
    return brief if isinstance(brief, Brief) else None


def _compact(urls: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in list(urls.items())[:60] if v)


def safe_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "brief"
