"""
The caveat-review task message — the prose + the three pre-computed lists of promises to check.

The lists are computed deterministically here (no model), so the reviewer never has to hunt: it
gets exactly the claims/figures the harness flagged, and only reads the prose to confirm each is
honestly handled. Keeping the input this small is what makes the lane cheap.
"""

from __future__ import annotations

from algent_backend.agent_system.agents.research.profile import SignalProfile

from .citations import unverified_prose_figures
from .draft import ArticleDraft


def caveat_worklists(draft: ArticleDraft, profile: SignalProfile) -> dict:
    """The three flagged lists (deterministic). Empty everywhere -> nothing to check."""
    claims = {c.id: c for c in profile.claim_ledger}
    sources = {s.id: s for s in profile.source_ledger}
    cited = [claims[c] for c in draft.cited_claim_ids if c in claims]
    prose = " ".join(x for x in (draft.title, draft.standfirst, draft.body) if x)
    return {
        "overstatement": [c for c in cited if c.status != "confirmed"],
        "unhedged": [c for c in cited if c.grounding != "snapshotted"],
        "figures": unverified_prose_figures(prose, cited, sources),
    }


def has_promises_to_check(work: dict) -> bool:
    return bool(work["overstatement"] or work["unhedged"] or work["figures"])


def _bullets(items: list[str]) -> list[str]:
    return items if items else ["- none"]


def build_caveat_message(draft: ArticleDraft, profile: SignalProfile) -> str:
    work = caveat_worklists(draft, profile)
    prose = (draft.standfirst + "\n\n" if draft.standfirst else "") + draft.body.strip()
    lines = [
        f"# CAVEAT CHECK — draft {draft.id}",
        "",
        "## The prose",
        prose,
        "",
        "## Promises to verify (check each against the prose; pass silently if already honest)",
        "",
        "### 1. Claims the prose must state AT their grade (not stronger)",
        *_bullets([f"- [{c.status}] \"{c.text}\"  ({c.id})" for c in work["overstatement"]]),
        "",
        "### 2. Claims resting on a source we did not read in full — must be attributed + hedged",
        *_bullets([f"- [{c.grounding}] \"{c.text}\"  ({c.id})" for c in work["unhedged"]]),
        "",
        "### 3. Figures the prose must carry an as-of / uncertainty for",
        f"- {', '.join(work['figures'])}" if work["figures"] else "- none",
        "",
        "TASK: For each listed item, find where the prose handles it and confirm it is honest "
        "(stated at grade / attributed + hedged / dated). Emit a CaveatCheck: a finding ONLY where "
        "the prose fails, and verdict = verified if all pass, else needs_hedging. Do not invent "
        "problems — a piece that already keeps every promise is 'verified' with no findings.",
    ]
    return "\n".join(lines)
