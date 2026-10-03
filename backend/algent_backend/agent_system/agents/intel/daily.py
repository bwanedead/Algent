"""
The daily report — the regular, stable rundown of what is happening in each live theater.

Run manually (``newsroom intel daily``), like an article run. For each of the domain's hottest
theaters it curates what significantly happened recently (who said what, events, decisions, with
dates and sources), the older items that matter for context, the theater's temperature and Pulses,
an outlook and what to watch. It is curation to stay in the loop: not an article, and not a copy of
the deep brief (briefs stay the occasional dive; the daily links to the latest one).

1. HEAT BOARD: the theaters and their temperature come from the board (``heat.run``); ``domain`` is
   data, so the same recipe serves any domain's feed.
2. PER THEATER: optional research with recency-first questions (fed to the Pulses like any research),
   that theater's due forecasts settled, then one section writer (structured output) given the reported
   headlines, the research claims, yesterday's section for continuity and the Pulse table.
3. ONE SUMMARY writer over all sections: the day's headline, bullets and cross-theater links.
4. PERSIST to ``intel_store/daily/<domain>/<date>.json`` (schema ``ohmega.daily/1``) — the durable copy
   the site mirrors and the next day's report reads for continuity.

Numbers are never the model's: temperature comes from the board and Pulse positions/deltas from the
Pulse store. The model only names which listed Pulses a theater bears on (exact names, filtered), and
the ``key_figures`` it lists are numbers the researched evidence states, kept only when their source is
one the research cited. Places are the model's coordinates, validated against the basemap (``geo``)
and dropped when they do not hold; the theater ``map`` is built from the survivors.

``temperature.trend`` is COVERAGE momentum (share of headlines), not severity; ``temperature.coverage`` is
its reader-facing label, ``escalation`` is the situation itself, and a Pulse ``band`` is severity.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import brief as br
from . import desk, forecasts, geo, render
from .contracts import DaySummary, Place, PulseProposal, SectionDraft, Theater, coverage_label
from .heat import store_dir

SCHEMA = "ohmega.daily/1"
MAX_QUOTE_WORDS = 25
RESEARCH_WINDOW_DAYS = 3        # the daily's research covers ~72 hours; earlier corpus claims are the background

DAILY_QUESTIONS = (
    "What happened in this dynamic in the last 72 hours? Date every event and say where it happened.",
    "What did named officials and other actors say about it? For each statement give who, their role, "
    "the date and the source URL; prefer exact wording only where the wording itself matters.",
    "What was decided, voted, deployed, struck, signed or announced? Give the date, the actor and the source.",
    "Which older events, agreements or precedents explain why today's developments matter? Give dates.",
)

DAILY_ROLE = """\
You are an editor on an intelligence desk compiling today's rundown for ONE theater, for a reader who
wants to stay in the loop without reading everything. This is curation, not an article and not the deep
brief: no narrative arc, no colour. Substance over volume: a few developments that actually changed the
picture beat a long list of headlines. Every line earns its place.

TWO KINDS OF EVIDENCE, KEPT APART:
- RESEARCHED claims, graded by our research, each with its source URLs. A development built on them is
  `verification: "researched"`.
- REPORTED headlines, what other outlets said, unverified by us. A development resting only on them is
  `verification: "reported"`. Never upgrade a reported item into a fact. When a claim has a single source,
  say so in the detail; one source is a lead, not a settled thing.

WHAT GOOD LOOKS LIKE:
- `developments`: the significant things from roughly the last three days, most important first. Each is
  concrete: who did or said what, when (YYYY-MM-DD) and where, and `significance` in a line (why a reader
  should care). Put the actors in `actors`. Use only source URLs that appear in the evidence you were
  given; if there is none, leave `sources` empty rather than inventing one.
- `statements`: attribute every statement to a named person or body, with their role, the date and the
  source. Paraphrase by default. Set `quote: true` only when the exact wording matters (a threat, a
  commitment, a denial), and then use the exact words, at most 25 of them — trim a longer one to its
  decisive words with an ellipsis, or paraphrase.
  Never put words in someone's mouth that the evidence does not give.
- `context`: OLDER items (weeks, months, years back) that the reader needs to make sense of today: the
  agreement being breached, the earlier strike this answers. Say why each is relevant now. Not a history
  lesson: only what changes how today reads.
- `since_yesterday`: when there is a PREVIOUS DAILY SECTION, say what moved against it: escalated, eased,
  new, resolved, or unchanged (stasis is a finding; say when a watched thing stayed put). Empty when there
  is no previous section. The reader already knows yesterday's; do not restate it.
- `bottom_line`: 2-3 sentences: what matters today and how sure we are. Calm is news too: if something
  expected has NOT happened, or the day was quiet, say so plainly. News over-reports escalation; do not
  read volume as intensity.
- `escalation`: direction (rising, steady, easing, unclear) and pace (fast, gradual, flat) from the
  evidence, set against the weeks before, not just the day.
- `outlook`: 2-3 sentences in estimative language (almost certain, likely, roughly even, unlikely,
  remote), with what it rests on. `watch_next`: short, concrete things that would show which way it goes.
- `pulses`: the listed Pulses this theater bears on, by their EXACT names from the table; none if none
  fits. You never state Pulse numbers; the desk adds them.
- `pulse_proposals`: propose a NEW Pulse only when the theater bears on a dimension that no listed Pulse
  measures. One dimension, one Pulse; a question whose low end is calm and high end is extreme, with a
  one-line reason. One question only (never two joined by "and"). Proposals that recur on later days become
  real Pulses, so make one rarely and only when it is genuinely missing. Never propose something a listed Pulse already measures.
- `key_figures`: up to four numbers a reader can hold, which often say more than a paragraph (transits
  per day through a strait, barrels offline, troops deployed, a price). Take a figure ONLY from the
  RESEARCHED claims, exactly as stated, with the date it is for (`as_of`, YYYY-MM-DD) and the source URL
  that gives it. Never compute, estimate, convert or round one yourself, and never take one from a
  headline: a number we cannot trace to our research does not belong, and the desk discards it. When
  the source also gives a baseline (what it was before, or normal), include `baseline` and say what it is
  in `baseline_label` ("pre-crisis"), because a number alone does not tell the reader whether it is high.
  None is better than a weak one.
- `place` on a development: your best latitude and longitude for the named city or site where it
  happened (`name`, `country` as the common English name, `lat`, `lon`), so the reader can see where
  things are happening. Give one only when the development has a specific named location you know the
  coordinates of; for a sea lane or open water use country "sea". A wrong point is worse than none: the
  desk checks every one against a map and drops those that fall outside the country, so omit it when unsure.
Plain words a newcomer can follow; no internal jargon (no claim ids, no pipeline terms). Do not
reproduce passages from sources: facts and short attributed phrases only.
"""

SUMMARY_ROLE = """\
You are the chief editor of an intelligence desk. You are handed today's per-theater sections and write
the top of the daily report: one line for the whole day and the few things that matter most.

- `headline`: one line that says what the day was about, concrete (who, what), not a label. If the day
  was calm, say that.
- `the_day`: 3-6 one-sentence bullets, most important first, each standing alone. Draw them from the
  sections; add nothing the sections do not support. Mark uncertainty where the sections do (reported
  versus researched), and do not let a single-source item read as established fact.
- `cross_theater`: theaters are rarely independent, and the links are often what a reader most needs
  and cannot see from inside one section. Read the sections against each other on purpose, looking for:
  shared actors (the same state, group or leader acting in two places), causal chains (an event in one
  theater that feeds or follows from another), and one theater's move changing another's risk (a
  withdrawal that frees a proxy network, a closed strait that reprices a sanctions fight). Each link is
  one line: the theaters, named exactly as given, and what connects them and in which direction. Prefer
  a few real links over many thin ones, and keep a link only when the sections themselves support it.
  Empty when, after looking, nothing genuinely connects them; do not force one, and do not leave it
  empty out of caution when the connection is plain.
Estimative language for anything about the future. Plain words; no internal jargon.
"""


# ── store ─────────────────────────────────────────────────────────────────────────────────────
def daily_dir(domain: str) -> Path:
    return store_dir() / "daily" / br.safe_name(domain)


def proposals_path() -> Path:
    """The LEGACY proposals file. New proposals go to the Pulse store via the registry; this path is
    only what ``registry.migrate_legacy_proposals`` reads."""
    return store_dir() / "pulse_proposals.jsonl"


def previous_section(domain: str, theater_id: str, *, before: str) -> dict | None:
    """The newest earlier daily section for this theater id (a theater that was not in yesterday's
    report still has a last time it was). None when we have never covered it."""
    folder = daily_dir(domain)
    for path in sorted(folder.glob("*.json"), reverse=True) if theater_id and folder.is_dir() else []:
        if path.stem >= before:
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for sec in rec.get("theaters") or []:
            if sec.get("theater_id") == theater_id:
                return {**sec, "_date": rec.get("date", path.stem)}
    return None


def previous_digest(sec: dict) -> str:
    esc = sec.get("escalation") or {}
    lines = [f"PREVIOUS DAILY SECTION ({sec.get('_date', '?')}):",
             f"Bottom line: {sec.get('bottom_line', '')}",
             f"Escalation: {esc.get('direction', '?')}, {esc.get('pace', '?')}",
             "Developments then:"]
    lines += [f"- {d.get('when', '')} {d.get('headline', '')}" for d in sec.get("developments") or []]
    lines += ["We said to watch:"] + [f"- {w}" for w in sec.get("watch_next") or []]
    return "\n".join(lines)


def _brief_digest(record: dict) -> str:
    inds = "; ".join(f"[{i.get('status', '?')}] {i.get('signal', '')}" for i in record.get("indicators") or [])
    return (f"LATEST DEEP BRIEF ({record.get('as_of', '?')}): {record.get('bottom_line', '')}"
            + (f"\nIndicators it tracks: {inds}" if inds else ""))


# ── evidence ──────────────────────────────────────────────────────────────────────────────────
def research_evidence(profiles: list[dict]) -> tuple[str, set[str]]:
    """Graded claims with their source URLs (the daily needs links; the Pulse evidence block has none),
    plus every URL the research cited: the closed set a 'researched' development may point at."""
    from ..pulse.seed import evidence_block

    urls = {str(s["id"]): str(s["url"]) for p in profiles for s in p.get("source_ledger") or []
            if isinstance(s, dict) and s.get("id") and s.get("url")}
    text, _ids = evidence_block(profiles)
    by_claim = {str(c["id"]): [urls[s] for s in c.get("supported_by") or [] if s in urls]
                for p in profiles for c in p.get("claim_ledger") or [] if isinstance(c, dict) and c.get("id")}
    out = []
    for line in text.splitlines():
        cid = line[3:line.find("]")] if line.startswith("- [") else ""
        out.append(line + (f" [sources: {', '.join(by_claim[cid][:3])}]" if by_claim.get(cid) else ""))
    return "\n".join(out), set(urls.values())


def _norm_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


# ── pulses ────────────────────────────────────────────────────────────────────────────────────
def _held_at(history: list, when: datetime) -> float | None:
    from ..pulse.projection import _ts

    before = [p for p in history if _ts(p.at) <= when]
    return before[-1].position if before else None


def pulse_rows(store: Any, names: list[str], *, now: datetime) -> list[dict]:
    """The Pulse table for a section, from the store: position and band as of ``now``, and how far each
    moved over the last day and week. A change is None when the Pulse had no position back then."""
    from datetime import timedelta

    by_name = {p.name: p for p in store.pulses()}
    out = []
    for name in names:
        pulse = by_name.get(name)
        if pulse is None:
            continue
        st = store.state(pulse.id, as_of=now.isoformat())

        def change(days: int) -> float | None:
            old = _held_at(st.history, now - timedelta(days=days))
            return None if st.position is None or old is None else round(st.position - old, 1)

        out.append({"id": pulse.id, "name": pulse.name, "position": st.position,
                    "band": st.band or "unassessed", "change_24h": change(1), "change_7d": change(7)})
    return out


# ── the writers ───────────────────────────────────────────────────────────────────────────────
def _ask(context: Any, config: Any, model_spec: Any, schema: Any, role: str, task: str) -> Any:
    from langchain_core.messages import HumanMessage, SystemMessage

    from algent_backend.agent_system.prompting import UNIVERSAL_AGENT_BASE, compose_system_prompt

    model = context.model_resolver.resolve(model_spec).client.with_structured_output(schema)
    return model.invoke([SystemMessage(content=compose_system_prompt(UNIVERSAL_AGENT_BASE, role)),
                         HumanMessage(content=task)], config=config)


def write_section(context: Any, config: Any, theater: Theater, heat: dict, *, as_of: str, profiles: list[dict],
                  pulse_table: dict[str, str], model_spec: Any, previous: dict | None = None,
                  brief: dict | None = None, corpus_ctx: Any = None) -> tuple[SectionDraft | None, set[str]]:
    """One structured call for one theater. Returns the raw draft and the URLs it may cite (the research's
    sources plus our earlier corpus claims')."""
    researched, research_urls = research_evidence(profiles)
    research_urls = research_urls | (corpus_ctx.source_urls if corpus_ctx is not None else set())
    task = (f"TODAY: {as_of}. Cover roughly the last three days; older items belong in `context`.\n\n"
            f"THEATER: {theater.name}\n{theater.why}\n\n"
            f"TEMPERATURE: {heat.get('recent', 0)} headlines in the last 3 days vs {heat.get('prior', 0)} before "
            f"({coverage_label(heat.get('trend', '')) or '?'}; how much it is reported, not how severe it is).\n\n"
            + (previous_digest(previous) + "\n\n" if previous
               else "PREVIOUS DAILY SECTION: none; leave since_yesterday empty.\n\n")
            + (_brief_digest(brief) + "\n\n" if brief else "")
            + br.corpus_block(corpus_ctx)
            + f"RESEARCHED CLAIMS (graded by our research):{researched or ' none'}\n\n"
            f"REPORTED HEADLINES (other outlets, unverified):\n{br.reported(theater)}\n\n"
            + ("OHMEGA PULSES (name | situation | position | band); tag `pulses` with names from here only, "
               "and propose a new Pulse only for a dimension none of them measures:\n"
               + "\n".join(pulse_table.values()) + "\n\n" if pulse_table
               else "OHMEGA PULSES: none listed yet.\n\n")
            + "TASK: write today's section for this theater.")
    draft = _ask(context, config, model_spec, SectionDraft, DAILY_ROLE, task)
    return (draft if isinstance(draft, SectionDraft) else None), research_urls


MAX_KEY_FIGURES = 4


def _valid_date(text: str) -> bool:
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except (TypeError, ValueError):
        return False
    return True


def _clean_figures(figures: list, research_urls: set[str]) -> list:
    """Key figures survive only with a finite number, a label, a real date and a source the research cited;
    a baseline that is not a finite number is dropped (with its label), never repaired."""
    known = {_norm_url(u) for u in research_urls}
    out = []
    for f in figures:
        if not f.label.strip() or not math.isfinite(f.value) or _norm_url(f.source) not in known                 or not _valid_date(f.as_of):
            continue
        if f.baseline is None or not math.isfinite(f.baseline):
            f.baseline, f.baseline_label = None, ""
        out.append(f)
    return out[:MAX_KEY_FIGURES]


def normalise_section(draft: SectionDraft, *, pulse_table: dict[str, str], has_previous: bool, researched: bool,
                      research_urls: set[str], reported_urls: set[str],
                      countries: list[geo.Country] | None = None) -> SectionDraft:
    """Enforce what the schema cannot: Pulse names from the table, changes only with a previous section,
    quotes at most 25 words, cited URLs only from the evidence, 'researched' only where our research
    ran and the item actually cites its sources, key figures only from the research's own sources, and
    places only where they validate against the basemap (``countries``; none loaded, none kept)."""
    draft.key_figures = _clean_figures(draft.key_figures, research_urls)
    canon = {n.lower(): n for n in pulse_table}
    draft.pulses = list(dict.fromkeys(canon[p.strip().lower()] for p in draft.pulses if p.strip().lower() in canon))
    if not has_previous:
        draft.since_yesterday = []
    known = {_norm_url(u) for u in research_urls | reported_urls}
    research_known = {_norm_url(u) for u in research_urls}

    def clean(url: str) -> str:
        return url if _norm_url(url) in known else ""

    draft.developments = [d for d in draft.developments if d.headline.strip()]
    for dev in draft.developments:
        valid = geo.validate_place(dev.place, countries)
        dev.place = Place(**valid) if valid else None
        dev.sources = [u for u in dict.fromkeys(dev.sources) if clean(u)]
        grounded = researched and any(_norm_url(u) in research_known for u in dev.sources)
        dev.verification = "researched" if dev.verification == "researched" and grounded else "reported"
        for st in dev.statements:
            st.source = clean(st.source)
            words = st.said.split()
            if st.quote and len(words) > MAX_QUOTE_WORDS:
                # Still the speaker's exact words, so it stays a quote, trimmed the way a journalist
                # trims one. Relabelling verbatim text as our paraphrase would misattribute the wording.
                st.said = " ".join(words[:MAX_QUOTE_WORDS]) + " …"
    for item in draft.context:
        item.source = clean(item.source)
        item.verification = ("researched" if researched and item.verification == "researched"
                             and _norm_url(item.source) in research_known else "reported")
    draft.context = [c for c in draft.context if c.what.strip()]
    seen = {n.lower() for n in pulse_table}
    draft.pulse_proposals = [p for p in draft.pulse_proposals
                             if p.name.strip() and p.question.strip() and p.low_end.strip() and p.high_end.strip()
                             and p.name.strip().lower() not in seen]
    return draft


def write_summary(context: Any, config: Any, sections: list[dict], *, as_of: str, domain: str,
                  model_spec: Any) -> DaySummary | None:
    digest = "\n\n".join(
        f"## {s['name']} ({s['temperature']['coverage'] or s['temperature']['trend']}; escalation {s['escalation']['direction']}, "
        f"{s['escalation']['pace']})\n{s['bottom_line']}\n"
        + "\n".join(f"- [{d['verification']}] {d['when']} {d['headline']}" for d in s["developments"])
        for s in sections)
    task = f"DATE: {as_of}  DOMAIN: {domain}\n\nTODAY'S SECTIONS:\n{digest}\n\nTASK: write the summary."
    out = _ask(context, config, model_spec, DaySummary, SUMMARY_ROLE, task)
    if not isinstance(out, DaySummary):
        return None
    names = {s["name"].lower(): s["name"] for s in sections}
    out.the_day = [b for b in out.the_day if b.strip()][:6]
    for link in out.cross_theater:
        link.theaters = list(dict.fromkeys(names[t.strip().lower()] for t in link.theaters if t.strip().lower() in names))
    out.cross_theater = [c for c in out.cross_theater if len(c.theaters) >= 2 and c.link.strip()]
    return out


# ── proposals ─────────────────────────────────────────────────────────────────────────────────
def record_proposals(store: Any, drafts: list[PulseProposal], *, theater: Theater, domain: str, as_of: str) -> int:
    """Hand the section writer's Pulse proposals to the Pulse registry (the one door). Each is one
    sighting under this day's run; a proposal that recurs across days becomes a Pulse there, not here.
    Never raises into the report. Returns how many sightings were recorded."""
    from algent_backend.agent_system.agents.pulse import registry

    recorded = 0
    for p in drafts:
        try:
            out = registry.propose(store, {
                **p.model_dump(), "at": f"{as_of}T12:00:00+00:00", "situation_hint": theater.name,
                "source": {"kind": "daily", "run_id": f"daily-{domain}-{as_of}", "theater_id": theater.id,
                           "domain": domain}})
            recorded += out["recorded"]
        except Exception:  # noqa: BLE001 - a proposal problem must never cost the day's report
            continue
    return recorded


# ── the engine ────────────────────────────────────────────────────────────────────────────────
def _section(theater: Theater, heat: dict, draft: SectionDraft, pulses: list[dict], brief: dict | None,
             countries: list[geo.Country] | None = None) -> dict:
    d = draft.model_dump()
    return {"theater_id": theater.id, "name": theater.name,
            "temperature": {"heat": heat.get("heat", 0), "trend": heat.get("trend", ""),
                            "coverage": coverage_label(heat.get("trend", "")),
                            "recent_share": heat.get("recent_share", 0.0), "prior_share": heat.get("prior_share", 0.0)},
            "escalation": d["escalation"], "pulses": pulses, "bottom_line": d["bottom_line"],
            "since_yesterday": d["since_yesterday"], "developments": d["developments"], "context": d["context"],
            "outlook": d["outlook"], "watch_next": d["watch_next"],
            "key_figures": d["key_figures"], "brief_slug": (brief or {}).get("slug"),
            "map": geo.build_map(d["developments"], countries)}


def produce_daily(ctx: Any, *, domain: str = "geopolitics", top: int = 5, research: bool = False,
                  model_spec: Any = None, as_of: str, board: dict | None = None, out: Path | None = None) -> dict:
    """Board -> per-theater sections -> summary -> persisted daily record. Returns a report with the
    record, a row per theater (research spend, forecasts settled, proposals, errors) and the HTML path."""
    from algent_backend.agent_system.agents.pulse.repository import pulse_store
    from algent_backend.agent_system.agents.pulse.update import update_quietly
    from algent_backend.agent_system.foundation import cost

    board = board if board is not None else (desk.latest_board() or {"theaters": [], "heat": []})
    theaters = {t["id"]: Theater.model_validate(t) for t in board.get("theaters", [])}
    heats = {h["theater_id"]: h for h in board.get("heat", [])}
    store = pulse_store()
    table = br.pulse_catalog(store)
    countries = geo.load()                                  # the basemap places are validated against
    now = datetime.fromisoformat(f"{as_of}T23:59:59+00:00")
    sections, rows, any_research = [], [], False
    for tid in desk.pick_theaters(board, top, [domain]):
        theater, heat = theaters[tid], heats.get(tid, {})
        row: dict[str, Any] = {"theater": tid, "researched": False, "research_usd": 0.0}
        profiles: list[dict] = []
        if research:
            prof = None
            try:
                with cost.article_scoped(1.0):              # the research agent caps itself; this makes spend visible
                    try:
                        prof = br.commission_research(ctx, None, theater, questions=DAILY_QUESTIONS,
                                                      id_tag=f"daily_{as_of.replace('-', '')}")
                    finally:
                        row["research_usd"] = round(cost.article_spent_usd(), 4)
            except Exception as exc:  # noqa: BLE001 - one theater's research must never kill the day's report
                # Fall back to headlines-only for this theater: the section is still written, from the
                # reported headlines and our earlier corpus, and marked unresearched.
                row["research_error"] = br.describe_failure(exc)
                print(f"[daily] research failed for {tid}; continuing headlines-only: {row['research_error']}",
                      flush=True)
            if prof:
                profiles.append(prof)
                update_quietly(prof, run_id=prof["id"])     # the day's research moves the Pulses it bears on
        row["researched"] = bool(profiles)
        any_research = any_research or bool(profiles)
        evidence = f"{research_evidence(profiles)[0]}\n\nREPORTED HEADLINES:\n{br.reported(theater)}"
        try:
            row["forecasts_settled"] = len(forecasts.resolve_due(ctx, None, model_spec, evidence, as_of=as_of,
                                                                 theater_id=tid))
        except Exception as exc:  # noqa: BLE001 - settling is a side duty of the report, never its gate
            row["forecasts_settled"] = 0
            row["forecasts_error"] = br.describe_failure(exc)
        previous = previous_section(domain, tid, before=as_of)
        latest_brief = desk.previous_brief(tid)
        earlier = br.recall(theater, as_of=as_of, window_days=RESEARCH_WINDOW_DAYS,
                            exclude_ids=[p["id"] for p in profiles])
        try:
            draft, research_urls = write_section(ctx, None, theater, heat, as_of=as_of, profiles=profiles,
                                                 pulse_table=table, model_spec=model_spec, previous=previous,
                                                 brief=latest_brief, corpus_ctx=earlier)
        except Exception as exc:  # noqa: BLE001 - skip this theater, keep the others
            rows.append({**row, "error": f"section writer failed: {br.describe_failure(exc)}"})
            print(f"[daily] section writer failed for {tid}; theater skipped: {rows[-1]['error']}", flush=True)
            continue
        if draft is None:
            rows.append({**row, "error": "section writer returned nothing"})
            continue
        draft = normalise_section(draft, pulse_table=table, has_previous=previous is not None,
                                  researched=bool(profiles) or not earlier.empty,
                                  research_urls=research_urls,
                                  reported_urls={u for m in theater.members for u in m.sources},
                                  countries=countries)
        sections.append(_section(theater, heat, draft, pulse_rows(store, draft.pulses, now=now), latest_brief,
                                 countries))
        proposals = [{"theater": theater.name, **p.model_dump()} for p in draft.pulse_proposals]
        row["proposals_logged"] = record_proposals(store, draft.pulse_proposals, theater=theater, domain=domain,
                                                   as_of=as_of)
        row["proposals"] = proposals
        rows.append(row)
    summary, summary_error = None, ""
    if sections:
        try:
            summary = write_summary(ctx, None, sections, as_of=as_of, domain=domain, model_spec=model_spec)
        except Exception as exc:  # noqa: BLE001 - the sections stand on their own; the top is a convenience
            summary_error = br.describe_failure(exc)
            print(f"[daily] summary writer failed; publishing sections without it: {summary_error}", flush=True)
    record = {"schema": SCHEMA, "domain": domain, "date": as_of, "built_at": datetime.now(UTC).isoformat(),
              "researched": any_research,
              "summary": {"headline": summary.headline if summary else
                          ("No live theaters in this domain today." if not sections else "Today's rundown."),
                          "the_day": summary.the_day if summary else []},
              "theaters": sections,
              "cross_theater": [c.model_dump() for c in summary.cross_theater] if summary else [],
              "pulse_proposals": [p for r in rows for p in r.get("proposals", [])]}
    path = daily_dir(domain) / f"{as_of}.json"
    desk._write(path, record)
    result: dict[str, Any] = {"report": record, "path": str(path), "theaters": rows,
                              "research_usd": round(sum(r["research_usd"] for r in rows), 4)}
    if summary_error:
        result["summary_error"] = summary_error
    if out is not None:
        html = out / f"daily_{br.safe_name(domain)}.html"
        html.write_text(render.render_daily(record), encoding="utf-8")
        result["html"] = str(html)
    return result
