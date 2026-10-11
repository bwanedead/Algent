"""
Relink — one repair pass when the claims lost their links to sources.

A research run can end with a full source ledger and a full claim ledger and no claim tied to any
source: the model wrote the claims without source refs, or with refs assembly could not resolve.
The money for the reading is already spent, so before the research is written off this makes ONE
cheap structured call over what we hold (claim texts, the source ledger) and asks which sources
support which claim. The harness validates the answer (ids must come from the ledger; an empty list
is allowed) and applies it with ``assembly.attach_claim_sources``. One attempt, no loop.
"""

from __future__ import annotations

from typing import Any

from algent_backend.agent_system.foundation import cost
from algent_backend.agent_system.foundation.models import house_spec

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .assembly import attach_claim_sources
from .profile import LinkAudit, SignalProfile

GENERATOR = "claim_relinker@v1"
_SNIPPET_CHARS = 300
RELINK_MODEL = house_spec(reasoning_effort="low", temperature=0.0)
RELINK_CAP_USD = 0.10   # a ceiling on the one repair call, not a target

SYSTEM_PROMPT = """\
You are tying claims back to the sources that support them. A researcher read these sources and
wrote these claims, but the links between them were lost. For each claim, list the ids of the
sources whose content supports it. Use ONLY ids from the source list. A claim that no listed source
supports gets an empty list: do not guess and do not stretch a source to cover it. A source supports
a claim only if what it says (title, snippet) bears on that specific assertion.
"""


class ClaimLinks(BaseModel):
    claim_id: str
    source_ids: list[str] = Field(default_factory=list)


class Relink(BaseModel):
    links: list[ClaimLinks] = Field(default_factory=list)


def claims_lost_their_links(profile: SignalProfile) -> bool:
    """There is a ledger of sources and a ledger of claims, yet no claim is tied to a source: the
    research happened, the links did not survive."""
    return bool(profile.source_ledger and profile.claim_ledger) and not profile.is_complete


def build_task(profile: SignalProfile) -> str:
    sources = "\n".join(
        f"[{s.id}] {s.title or '(untitled)'} | {s.url}"
        + (f" | {s.snapshot.excerpt[:_SNIPPET_CHARS]!r}" if s.snapshot and s.snapshot.excerpt else "")
        for s in profile.source_ledger)
    claims = "\n".join(f"[{c.id}] {c.text}" for c in profile.claim_ledger)
    return f"SOURCES:\n{sources}\n\nCLAIMS:\n{claims}"


def relink(profile: SignalProfile, model: Any, config: Any = None) -> SignalProfile:
    """Run the one repair pass. ``model`` is a chat client. Never raises: a failed call is a recorded
    failed attempt. The returned profile carries the outcome in ``link_audit``."""
    audit = (profile.link_audit or LinkAudit()).model_copy(update={"relink_attempted": True})

    def done(note: str, attached: int = 0, p: SignalProfile = profile) -> SignalProfile:
        return p.model_copy(update={"link_audit": audit.model_copy(
            update={"claims_relinked": attached, "relink_note": note})})

    try:
        out = model.with_structured_output(Relink).invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=build_task(profile))], config=config)
    except Exception as exc:  # noqa: BLE001 - repair is best effort; the caller handles the still-empty profile
        return done(f"relink call failed: {type(exc).__name__}")
    if not isinstance(out, Relink):
        return done("relink returned no structured answer")
    fixed, n = attach_claim_sources(profile, {c.claim_id: c.source_ids for c in out.links})
    if not n:
        return done("relink found no supporting source for any claim")
    return done(f"{n} of {len(profile.claim_ledger)} claims relinked", n, fixed)


def repair_profile(profile: SignalProfile, context: Any, config: Any = None) -> tuple[SignalProfile, float]:
    """The one repair pass over a profile whose claims lost their sources, metered. Returns
    ``(profile, usd_spent)``. The entry point for both the research loop and a saved incomplete profile."""
    with cost.scoped(RELINK_CAP_USD, RELINK_MODEL.model):
        fixed = relink(profile, context.model_resolver.resolve(RELINK_MODEL).client, config)
        return fixed, cost.spent_usd()


def repair_saved(store: Any, profile_id: str, context: Any, config: Any = None) -> SignalProfile | None:
    """Repair the saved profile with this id when its claims lost their links, and save the result.
    Returns the profile (repaired, or as found if it needed nothing or the repair found nothing), or
    None when nothing is saved. No research is done; everything already bought is reused."""
    found = store.get(profile_id)
    if found is None or not claims_lost_their_links(found):
        return found
    fixed, _usd = repair_profile(found, context, config)
    if fixed.is_complete:
        store.save(fixed)
    return fixed
