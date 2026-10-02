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
`bottom_line`, `escalation.assessment`, `second_order`, `peripheral`, `indicators` and `judgments`
are assessments: use estimative language (almost certain, likely, roughly even, unlikely, remote) and
say what each rests on. Calm is evidence too: if something has NOT happened that would have been
expected, that is worth a line. News over-reports escalation; do not read volume as intensity.

WHAT A GOOD BRIEF HOLDS:
- `changes`: when there is a PREVIOUS BRIEF, lead the work with what changed since it, most
  important first. Each is `escalated`, `eased`, `new`, `resolved` or `unchanged` (say so when a
  watched thing stayed put: stasis is a finding), with the evidence that moved it. A repeat brief
  that reads like a first brief wastes the reader's time; the reader already knows the old one.
  Empty when there is no previous brief.
- `bottom_line`: 2-3 sentences: what matters, which way it is moving, how sure we are. On a repeat
  brief, say what is different now.
- `timeline`: dated events, most recent last, each with actors, verification and a source URL.
- `relations`: who is doing what to whom, one edge per relationship (kind: strikes, sabotage,
  coerces, sanctions, supports, negotiates, deters, other).
- `escalation`: direction (rising/steady/easing/unclear), pace (fast/gradual/flat) and the
  assessment with its basis, compared with the months before.
- `judgments`: 2-4 key judgments, each a FORECAST the desk will be scored on. A judgment is a claim
  about the future that events can prove wrong, concrete enough that a stranger could check it later
  from public reporting ("X will happen by DATE", not "tensions will remain elevated"). Give a real
  probability (1-99): the number is a commitment, so let it vary with your evidence. A slate of
  all 50s says you will not commit; a slate of all 90s says you are not honest about uncertainty.
  Set `horizon` (YYYY-MM-DD) from about two weeks to six months out, whenever the question will
  actually be decidable. Fill `resolves_yes_if` and `resolves_no_if` with what a later reader would
  have to see to settle it, and `basis` with what the number rests on. Keep the words consistent
  with the number (almost certain 95+, likely 70-85, roughly even 40-60, unlikely 15-30, remote
  under 5). If YOUR TRACK RECORD shows misses, look for the pattern (too confident? too slow to call
  a turn?) and correct for it; do not restate a missed call unchanged.
- `alternatives`: the red team. Take the theater's core question (what is really going on, or what
  happens next) and set out 2-3 competing explanations, the leading one included. For each: the
  evidence consistent with it, the evidence that cuts against it, and its plausibility (leading,
  plausible, unlikely). Steelman the alternative honestly, as its best advocate would argue it, not
  as a strawman. Weigh each by what the evidence rules OUT rather than by how much fits, because
  most evidence fits several stories. The point is to catch the brief's own favourite being wrong.
- `would_change_our_mind`: the specific observations that would make you abandon the leading
  hypothesis or move a key judgment sharply.
- `second_order`: what follows for outside parties, with likelihood and what to watch for.
- `peripheral`: things outside the core that bear on it and should be watched: adjacent target
  classes, neighbouring theaters, supply lines, elections, markets.
- `indicators`: the observable signals that would mark the next rung (status: not seen, emerging,
  observed) and what each would mean. Indicators are tracked over time: re-assess EVERY indicator
  from the previous brief using the SAME `signal` wording, so a reader can follow it from one brief
  to the next, and put its old status in `previous_status` (leave it empty for new signals). Add
  new indicators as the situation calls for them; drop one only when it is overtaken, and say so in
  `changes`.
- `unknowns`: what we cannot establish and would most want to.
- `pulses`: which of the listed Pulses this theater bears on, by their EXACT names from the table
  provided. Only names from that table; if none fits, leave it empty.
Plain words a newcomer can follow; no internal jargon.
"""


def focus_tag(focus: str) -> str:
    """A short stable tag, so a focused research run and its brief never overwrite the general one."""
    import hashlib

    return hashlib.sha1(" ".join(focus.lower().split()).encode("utf-8")).hexdigest()[:6] if focus.strip() else ""


def commission_research(context: Any, config: Any, theater: Theater, *, focus: str = "",
                        questions: tuple[str, ...] | None = None, id_tag: str = "") -> dict | None:
    """Research the theater with the generic questions (or ``questions``, e.g. the daily report's
    recency-first set), led by the desk's FOCUS question when one is given (the recipe stays
    generic; the focus is how an operator steers it). ``id_tag`` keeps a recurring run's profile from
    colliding with the deep brief's. Returns the profile (also saved to the corpus)."""
    from ..research.spec import build_graph as build_profile

    sources = list(dict.fromkeys(u for m in theater.members for u in m.sources))[:12]
    vector = {
        "id": f"intel_{theater.id.removeprefix('thr_')}"[:60] + (f"_{focus_tag(focus)}" if focus.strip() else "")
              + (f"_{id_tag}" if id_tag else ""),
        "title": theater.name + (f" — {focus.strip()}" if focus.strip() else ""),
        "thesis": (f"Desk focus: {focus.strip()}\n" if focus.strip() else "") + (theater.why or theater.description),
        "vector_type": "synthesis",
        "research_effort": "deep",
        "pillars": [theater.domain],
        "scope": [],
        "key_questions": ([focus.strip()] if focus.strip() else []) + list(questions or GENERIC_QUESTIONS),
        "sources": sources,
        "supporting_hits": [f"{m.edition}#{m.n}" for m in theater.members][:20],
        "rationale": "commissioned by the intel desk: this theater is running hot",
    }
    out = build_profile(context).invoke({"vector": vector}, config)
    profile = out.get("profile")
    return profile if isinstance(profile, dict) and profile.get("id") else None


def recall(theater: Theater, *, as_of: str, window_days: int, exclude_ids: list[str] | None = None,
           store: Any = None) -> Any:
    """Our own earlier research on this theater, from before the research window (the window's evidence
    is already in hand). The CorpusContext is empty when the corpus has nothing; never raises."""
    from datetime import date, timedelta

    from ..research import corpus
    from ..research.store import JsonProfileStore

    try:
        cutoff = (date.fromisoformat(as_of) - timedelta(days=window_days)).isoformat()
        query = "\n".join([theater.name, theater.why, theater.description,
                           *(f"{m.title} {m.thesis}" for m in theater.members)])
        sources = [u for m in theater.members for u in m.sources]
        return corpus.related(store or JsonProfileStore(), query_text=query, sources=sources,
                              exclude_ids=exclude_ids or (), as_of=as_of, older_than=cutoff)
    except Exception:  # noqa: BLE001 - memory is an aid, not a dependency
        return corpus.CorpusContext()


def corpus_block(found: Any) -> str:
    """The prompt section for a CorpusContext ('' when it has nothing)."""
    if found is None or found.empty:
        return ""
    return ("OUR EARLIER RESEARCH (graded, dated; from before this run's window). Our own corpus, for "
            "background and the older half of the timeline. Cite only the URLs listed; an item built on one of "
            "these is `researched` ONLY with that URL attached, otherwise `reported`. Dates are when the thing "
            "was said or learned, so never present it as today's news; it may have changed since:\n"
            f"{found.render()}\n\n")


def reported(theater: Theater) -> str:
    return "\n".join(f"- ({m.edition[:10]}) {m.title} — {m.thesis[:220]} [sources: {', '.join(m.sources[:2]) or '—'}]"
                     for m in sorted(theater.members, key=lambda m: m.edition))


def pulse_catalog(store: Any) -> dict[str, str]:
    """Current Pulses as ``name -> table row`` (situation, position or 'unassessed', band): the closed
    list the analyst may tag a theater with. Dormant pulses and inactive situations are left out."""
    titles = {s.id: s.title for s in store.situations() if s.status == "active"}
    out = {}
    for p in store.pulses():
        if p.status == "dormant" or p.situation_id not in titles:
            continue
        st = store.state(p.id)
        pos = "unassessed" if st.position is None else f"{st.position:.0f}"
        out[p.name] = f"- {p.name} | {titles[p.situation_id]} | {pos} | {st.band or 'unassessed'}"
    return out


def previous_digest(record: dict) -> str:
    """A compact digest of the last brief on this theater: what we said, so this one can say what moved."""
    esc = record.get("escalation") or {}
    lines = [f"PREVIOUS BRIEF ({record.get('as_of', '?')}): {record.get('title', '')}",
             f"Bottom line: {record.get('bottom_line', '')}",
             f"Escalation: {esc.get('direction', '?')}, {esc.get('pace', '?')} - {esc.get('assessment', '')[:300]}",
             "Indicators (keep these signals, same wording):"]
    lines += [f"- [{i.get('status', '?')}] {i.get('signal', '')}" for i in record.get("indicators") or []]
    lines += ["Key judgments:"] + [f"- {j.get('probability')}% by {j.get('horizon')}: {j.get('statement', '')}"
                                    for j in record.get("judgments") or []]
    return "\n".join(lines)


def write_brief(context: Any, config: Any, theater: Theater, heat: dict, *, profiles: list[dict],
                pulse_table: dict[str, str], model_spec: Any, focus: str = "", previous: dict | None = None,
                track_record: str = "", corpus_ctx: Any = None) -> Brief | None:
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    from ..pulse.seed import evidence_block

    researched, _ids = evidence_block(profiles)
    source_urls = {s.get("id"): s.get("url") for p in profiles for s in p.get("source_ledger") or []}
    task = (f"THEATER: {theater.name}\n{theater.why}\n\n"
            f"HEAT: {heat.get('recent', 0)} headlines in the last 3 days vs {heat.get('prior', 0)} before "
            f"({heat.get('trend', '?')}); first seen {heat.get('first_seen', '?')}.\n\n"
            + (previous_digest(previous) + "\n\n" if previous else "PREVIOUS BRIEF: none, this is the first.\n\n")
            + (f"YOUR TRACK RECORD ON THIS THEATER (the desk's earlier judgments and how they came out):\n"
               f"{track_record}\n\n" if track_record else "")
            + corpus_block(corpus_ctx)
            + f"RESEARCHED CLAIMS (graded by our research):{researched or ' none'}\n\n"
            f"SOURCE URLS FOR RESEARCHED CLAIMS: {_compact(source_urls)}\n\n"
            f"REPORTED HEADLINES (other outlets, unverified):\n{reported(theater)}\n\n"
            + ("OHMEGA PULSES (name | situation | position | band); tag `pulses` with names from here only:\n"
               + "\n".join(pulse_table.values()) + "\n\n" if pulse_table else "")
            + (f"DESK FOCUS: {focus.strip()}\nThe desk asked this directly: lead with it and answer it from the "
               "evidence, then cover the rest of the theater.\n\n" if focus.strip() else "")
            + "TASK: write the brief.")
    model = context.model_resolver.resolve(model_spec).client.with_structured_output(Brief)
    brief = model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, ANALYST_ROLE)),
                          HumanMessage(content=task)], config=config)
    if not isinstance(brief, Brief):
        return None
    allowed = {u for u in source_urls.values() if u} | (corpus_ctx.source_urls if corpus_ctx is not None else set())
    return normalise(brief, pulse_table=pulse_table, has_previous=bool(previous), research_urls=allowed)


def normalise(brief: Brief, *, pulse_table: dict[str, str], has_previous: bool,
              research_urls: set[str] | None = None) -> Brief:
    """Enforce what the schema cannot: Pulse names come from the table (canonical spelling, no
    inventions), changes need a previous brief, judgments are at most four and carry a real date, and
    (when ``research_urls`` is given: the researched profiles' sources plus our earlier corpus claims')
    a timeline item is `researched` only if its source is one of those URLs."""
    if research_urls is not None:
        known = {u.strip().rstrip("/") for u in research_urls}
        for item in brief.timeline:
            if item.verification == "researched" and item.source.strip().rstrip("/") not in known:
                item.verification = "reported"
    canon = {n.lower(): n for n in pulse_table}
    brief.pulses = list(dict.fromkeys(canon[p.strip().lower()] for p in brief.pulses if p.strip().lower() in canon))
    if not has_previous:
        brief.changes = []
    brief.judgments = [j for j in brief.judgments if _is_date(j.horizon) and j.statement.strip()][:4]
    return brief


def _is_date(text: str) -> bool:
    from datetime import date

    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _compact(urls: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in list(urls.items())[:60] if v)


def safe_name(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "brief"
