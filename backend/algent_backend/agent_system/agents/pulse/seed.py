"""
Seeding — build the first situations and Pulses from the research corpus Ohmega already has.

Two steps, both reading only research the newsroom has already graded (Pulse never fetches the web):
1. ATTACH — one cheap call sorts the research profiles into the seed situations (``catalog.py``).
2. SEED   — per situation, define 2–4 Pulses with anchored rulers, place each against the graded
            claims of its attached profiles, and open a few watches.

The machine's answer is then CHECKED, not trusted: cited claim ids must exist in the evidence it
was shown, anchors must sit at exactly 0/25/50/75/100, and a position with no valid evidence
behind it is demoted to "unassessed" rather than kept as a confident guess.

Dry run by default: ``draft()`` returns the proposal and ``render_review()`` writes it for a human
to read. ``commit()`` persists an approved proposal into a Pulse repository.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .catalog import SEED_SITUATIONS, SeedSituation
from .contracts import Anchor, Confidence, Influence, Pulse, PulseDefinition, Situation, Source, Watch
from .prompts import ATTACH_ROLE, PROMPT_VERSION, SEED_ROLE

ANCHOR_POSITIONS = (0.0, 25.0, 50.0, 75.0, 100.0)
_CLAIMS_PER_PROFILE = 40          # most salient first; enough to ground, bounded for the call
_STATUS_ORDER = {"confirmed": 0, "likely": 1, "contested": 2, "unconfirmed": 3, "speculative": 4}
_SALIENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


# ── what the model returns ────────────────────────────────────────────────────────────────────
class AttachLink(BaseModel):
    situation_id: str
    profile_ids: list[str] = Field(default_factory=list)


class AttachPlan(BaseModel):
    links: list[AttachLink] = Field(default_factory=list)


class PulseDraft(BaseModel):
    slug: str
    name: str
    question: str
    anchors: list[Anchor] = Field(default_factory=list)
    position: float | None = None
    claim_ids: list[str] = Field(default_factory=list)
    rationale: str = ""
    confidence: Confidence = Field(default_factory=Confidence)
    evidence_through: str = ""


class WatchDraft(BaseModel):
    condition: str
    why: str = ""
    evidence_needed: str = ""
    pulse_slugs: list[str] = Field(default_factory=list)
    expected_direction: Literal["up", "down", "either"] = "either"
    horizon: str = ""


class SituationDraft(BaseModel):
    summary: str = ""
    entities: list[str] = Field(default_factory=list)
    pulses: list[PulseDraft] = Field(default_factory=list)
    watches: list[WatchDraft] = Field(default_factory=list)
    gaps: str = ""


class SeededSituation(BaseModel):
    """One situation's checked proposal, ready to review or commit."""

    situation: SeedSituation | Any
    profile_ids: list[str] = Field(default_factory=list)
    draft: SituationDraft = Field(default_factory=SituationDraft)
    problems: list[str] = Field(default_factory=list)   # what the checks corrected

    model_config = {"arbitrary_types_allowed": True}


# ── evidence packing ──────────────────────────────────────────────────────────────────────────
def profile_index(profiles: list[dict]) -> str:
    """One line per profile — what ATTACH sorts."""
    lines = []
    for p in profiles:
        summary = " ".join(str(p.get("summary") or "").split())[:220]
        lines.append(f"- {p.get('id')}: {p.get('title') or ''} — {summary}")
    return "\n".join(lines)


def evidence_block(profiles: list[dict]) -> tuple[str, set[str]]:
    """The graded claims SEED may cite, and the set of ids that are citable."""
    ids: set[str] = set()
    out: list[str] = []
    for p in profiles:
        claims = [c for c in (p.get("claim_ledger") or []) if isinstance(c, dict) and c.get("id")]
        claims.sort(key=lambda c: (_SALIENCE_ORDER.get(str(c.get("salience")), 3),
                                   _STATUS_ORDER.get(str(c.get("status")), 5)))
        out.append(f"\n## {p.get('title') or p.get('id')} (as of {p.get('as_of') or '?'})")
        for c in claims[:_CLAIMS_PER_PROFILE]:
            ids.add(str(c["id"]))
            out.append(f"- [{c['id']}] ({c.get('status')}) {' '.join(str(c.get('text') or '').split())}")
    return "\n".join(out), ids


# ── the calls ─────────────────────────────────────────────────────────────────────────────────
def attach(context: Any, config: Any, profiles: list[dict], *, model_spec: Any,
           situations: tuple[SeedSituation, ...] = SEED_SITUATIONS) -> dict[str, list[str]]:
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    sits = "\n".join(f"- {s.id}: {s.title} — SCOPE: {s.scope}" for s in situations)
    task = (f"SITUATIONS:\n{sits}\n\nRESEARCH PROFILES:\n{profile_index(profiles)}\n\n"
            "TASK: for each situation, the profile ids that genuinely belong to it.")
    model = context.model_resolver.resolve(model_spec).client.with_structured_output(AttachPlan)
    plan = model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, ATTACH_ROLE)),
                         HumanMessage(content=task)], config=config)
    known = {str(p.get("id")) for p in profiles}
    links = {s.id: [] for s in situations}
    for link in getattr(plan, "links", []) or []:
        if link.situation_id in links:
            links[link.situation_id] = [pid for pid in dict.fromkeys(link.profile_ids) if pid in known]
    return links


def seed_situation(context: Any, config: Any, sit: SeedSituation, profiles: list[dict], *,
                   model_spec: Any, tracked_elsewhere: list[str] | None = None) -> SeededSituation:
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    evidence, citable = evidence_block(profiles)
    elsewhere = ("\n\nALREADY TRACKED BY OTHER SITUATIONS — do not measure these again:\n"
                 + "\n".join(f"- {line}" for line in tracked_elsewhere)) if tracked_elsewhere else ""
    task = (f"SITUATION: {sit.title}\nSCOPE: {sit.scope}{elsewhere}\n\n"
            f"EVIDENCE — graded claims from Ohmega's research ({len(profiles)} profile(s)):"
            f"{evidence or ' none yet.'}\n\n"
            "TASK: define this situation's Pulses with anchored rulers, place each against the "
            "evidence (or leave it unassessed), and open the watches.")
    model = context.model_resolver.resolve(model_spec).client.with_structured_output(SituationDraft)
    draft = model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, SEED_ROLE)),
                          HumanMessage(content=task)], config=config)
    if not isinstance(draft, SituationDraft):
        return SeededSituation(situation=sit, profile_ids=[p["id"] for p in profiles],
                               problems=["model returned no draft"])
    return check(sit, draft, citable, [p["id"] for p in profiles])


def check(sit: SeedSituation, draft: SituationDraft, citable: set[str],
          profile_ids: list[str]) -> SeededSituation:
    """Correct what the model got wrong, and record every correction."""
    problems: list[str] = []
    pulses: list[PulseDraft] = []
    for p in draft.pulses:
        slug = re.sub(r"[^a-z0-9_]+", "_", p.slug.lower()).strip("_") or "pulse"
        positions = sorted(a.position for a in p.anchors)
        if tuple(positions) != ANCHOR_POSITIONS:
            problems.append(f"{slug}: anchors at {positions}, not 0/25/50/75/100 — pulse dropped")
            continue
        window = str(p.evidence_through or "")[:4]
        if window.isdigit():
            recent = {window, str(int(window) - 1)}
            circular = [a.position for a in p.anchors if any(y in (a.example or "") for y in recent)]
            if circular:
                problems.append(f"{slug}: anchor example(s) at {circular} may come from the evidence "
                                f"window ({'/'.join(sorted(recent))}) — a ruler must predate what it measures")
        bad = [c for c in p.claim_ids if c not in citable]
        good = [c for c in p.claim_ids if c in citable]
        if bad:
            problems.append(f"{slug}: cited ids not in the evidence dropped: {bad}")
        position = p.position
        if position is not None and not good:
            problems.append(f"{slug}: position {position} had no valid evidence — left unassessed")
            position = None
        if position is not None and not 0 <= position <= 100:
            problems.append(f"{slug}: position {position} off the ruler — left unassessed")
            position = None
        pulses.append(p.model_copy(update={"slug": slug, "claim_ids": good, "position": position,
                                           "anchors": sorted(p.anchors, key=lambda a: a.position)}))
    slugs = {p.slug for p in pulses}
    watches = []
    for w in draft.watches:
        linked = [s for s in w.pulse_slugs if s in slugs]
        if not linked:
            problems.append(f"watch '{w.condition[:50]}' linked to no known pulse — dropped")
            continue
        watches.append(w.model_copy(update={"pulse_slugs": linked}))
    return SeededSituation(situation=sit, profile_ids=profile_ids, problems=problems,
                           draft=draft.model_copy(update={"pulses": pulses, "watches": watches}))


# ── persist an approved proposal ─────────────────────────────────────────────────────────────
def pulse_id(sit: SeedSituation, slug: str) -> str:
    return f"pls_{sit.id.removeprefix('sit_')}_{slug}"


def commit(store: Any, seeded: list[SeededSituation], *, run_id: str, model: str = "") -> int:
    """Write situations, Pulses (definition v1), seed influences and watches. Returns pulses made."""
    made = 0
    now = datetime.now(UTC).isoformat()
    for s in seeded:
        sit = s.situation
        store.save_situation(Situation(id=sit.id, domain=sit.domain, title=sit.title,
                                       summary=s.draft.summary, entities=s.draft.entities))
        positions: dict[str, float] = {}
        for p in s.draft.pulses:
            pid = pulse_id(sit, p.slug)
            store.create_pulse(Pulse(id=pid, situation_id=sit.id, name=p.name, definitions=[
                PulseDefinition(question=p.question, anchors=p.anchors, note="seed")]))
            store.append(Influence(
                pulse_id=pid, at=now, evidence_through=p.evidence_through, mode="seed",
                definition_version=1, proposed_position=p.position,
                decision="applied" if p.position is not None else "no_change",
                rationale=p.rationale or "seeded without evidence — unassessed",
                confidence=p.confidence, prompt_version=PROMPT_VERSION, model=model,
                source=Source(run_id=run_id, stage="pulse_seed", claim_ids=p.claim_ids)))
            if p.position is not None:
                positions[pid] = p.position
            made += 1
        for i, w in enumerate(s.draft.watches, 1):
            store.save_watch(Watch(
                id=f"wch_{sit.id.removeprefix('sit_')}_{i:02d}", situation_id=sit.id,
                condition=w.condition, why=w.why, evidence_needed=w.evidence_needed,
                pulse_ids=[pulse_id(sit, x) for x in w.pulse_slugs],
                expected_direction=w.expected_direction, horizon=w.horizon,
                origin_positions={pulse_id(sit, x): positions[pulse_id(sit, x)]
                                  for x in w.pulse_slugs if pulse_id(sit, x) in positions}))
    return made


# ── review ────────────────────────────────────────────────────────────────────────────────────
def render_review(seeded: list[SeededSituation], titles: dict[str, str]) -> str:
    from .contracts import band_of

    out = ["# Pulse seed — review before commit", ""]
    for s in seeded:
        sit, d = s.situation, s.draft
        out += [f"## {sit.title}", "",
                f"*{len(s.profile_ids)} research profile(s):* "
                + (", ".join(titles.get(p, p) for p in s.profile_ids) or "none — Pulses left unassessed"), "",
                d.summary, ""]
        for p in d.pulses:
            where = (f"**{p.position:g} — {band_of(p.position)}**" if p.position is not None
                     else "**unassessed**")
            out += [f"### {p.name}  ·  {where}  ·  confidence {p.confidence.overall()}",
                    f"*{p.question}*", ""]
            out += [f"- **{a.position:g}** — {a.meaning}" + (f" *(e.g. {a.example})*" if a.example else "")
                    for a in p.anchors]
            through = p.evidence_through if p.evidence_through not in ("", "null", "None", "?") else "—"
            out += ["", f"Why: {p.rationale}", f"Evidence: {', '.join(p.claim_ids) or '—'} "
                    f"(through {through})", ""]
        if d.watches:
            out.append("**Watches**")
            out += [f"- {w.condition} → {w.expected_direction} on {', '.join(w.pulse_slugs)}"
                    + (f" (by {w.horizon})" if w.horizon else "") for w in d.watches]
            out.append("")
        if d.gaps:
            out += [f"**Gaps:** {d.gaps}", ""]
        if s.problems:
            out += ["**Checks corrected:**", *[f"- {x}" for x in s.problems], ""]
    return "\n".join(out)
