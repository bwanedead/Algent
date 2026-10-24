"""
Corpus-only research for the bots. A forecast or a trade decision reads what OUR corpus holds (the query API in ``corpus/query``), never the open
web, so the track record measures the corpus and nothing else drives the outcome.

The model harness here has no tool calling (``forecast.default_ask`` is one structured call), so this is PLANNED RETRIEVAL: a cheap planning call
proposes queries over six tools (``entity``, ``about``, ``search``, ``timeline``, ``related``, ``series``), we run them against the corpus index,
and the decision call reads the results. A second planning round sees the first round's result lines and may ask for more; rounds, queries and
characters are capped in ``flags``. Every result row carries an id the decision can cite.

Blindness. The corpus also ingests the Polymarket mirror and our own forecasts and decisions (``corpus/sources/markets.py``). None of that may reach
a forecaster: a row of product ``markets``, a ``market:`` entity or a ``market.*`` series is dropped here, whatever tool returned it.

A gap is not looked up. When the corpus does not hold what the question needs, the decision says so (``evidence`` + ``gap_topic``) and ``gaps.py``
records the request; the daily fill job turns the best requests into research runs, and the bot sees the answer next time as corpus content.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field

from . import flags
from .contracts import Market, QueryRun

TOOLS = ("entity", "about", "search", "timeline", "related", "series")

PLAN_ROLE = """\
You plan a literature search over the desk's own corpus: dated documents (dailies, briefs, statements, sanctions, calendar items, research
profiles, articles), sourced claims, events, entities (countries, people, organisations, situations, places, vessels, pulses) and time series. You
do not answer anything. For each question you are shown, name the corpus queries whose results a forecaster would most want to read. There is no
web search: only the corpus.

Tools (arg is a name or words):
- entity(arg): who/what an entity is, its latest status, situations, relations and recent timeline. arg is a name: "Iran", "Strait of Hormuz".
- about(arg, since, kinds): documents, claims and events involving the entity since a date. kinds may narrow to document kinds (daily, statement,
  profile...) or the words claim / event / document.
- search(arg, since, kinds): full text over documents, claims and events. arg is a few distinctive words, not a sentence.
- timeline(arg, since): the entity's events and documents in date order: how a situation got here.
- related(arg): what the entity is most connected to.
- series(arg): numbers over time for an entity or a metric id (pulse positions, indicators, counts).

Good plans: the entities the question turns on (the countries, the actors, the place), then a search on the specific trigger the resolution rules
name, then a timeline of the live situation. Prefer few precise queries to many vague ones. since is an ISO date; leave it empty for the default
recent window. If the results already shown are enough, or nothing more could help, return no queries.
"""

Tool = Literal["entity", "about", "search", "timeline", "related", "series"]


class Query(BaseModel):
    market: str = Field(default="M1", description="The label of the question this query is for, exactly as shown (M1, M2, ...).")
    tool: Tool
    arg: str = Field(description="An entity name, or a few distinctive search words.")
    since: str = Field(default="", description="ISO date to start from, or empty for the default window.")
    kinds: list[str] = Field(default_factory=list, description="Optional narrowing: document kinds, or claim / event / document.")


class Plan(BaseModel):
    queries: list[Query] = Field(default_factory=list, description="The queries to run; empty when the results shown are enough.")


@dataclass
class Item:
    """One question to research (a market), as the planner is shown it. Carries no price."""

    label: str
    question: str
    rules: str = ""
    end_date: str = ""
    countries: list[str] = field(default_factory=list)
    theaters: list[str] = field(default_factory=list)


@dataclass
class Hit:
    id: str
    kind: str
    date: str
    title: str
    text: str = ""

    def line(self, chars: int = 360) -> str:
        body = " ".join(f"{self.title}. {self.text}".split()) if self.text and self.text != self.title else " ".join(self.title.split())
        return f"[{self.id}] {self.date[:10]} {self.kind}: {body[:chars]}"


@dataclass
class Found:
    hits: dict[str, Hit] = field(default_factory=dict)
    runs: list[QueryRun] = field(default_factory=list)

    def add(self, hits: list[Hit]) -> list[str]:
        new = []
        for h in hits:
            if h.id not in self.hits:
                self.hits[h.id] = h
                new.append(h.id)
        return new

    def render(self, chars: int = flags.RESEARCH_CHARS_PER_MARKET) -> tuple[str, list[str]]:
        """The text shown to the decision and the ids actually shown in it (newest first, cut at ``chars``)."""
        out, ids, used = [], [], 0
        for h in sorted(self.hits.values(), key=lambda h: h.date, reverse=True):
            ln = h.line()
            if used + len(ln) > chars and out:
                break
            out.append(ln)
            ids.append(h.id)
            used += len(ln) + 1
        return "\n".join(out), ids


@dataclass
class Researched:
    """What research returned for one item, ready for the decision and the trace."""

    text: str = ""
    ids: list[str] = field(default_factory=list)
    returned: list[str] = field(default_factory=list)
    runs: list[QueryRun] = field(default_factory=list)
    rounds: int = 0
    mode: str = "corpus"
    usd: float = 0.0                        # this item's share of the planning spend
    ms: int = 0
    tokens: int = 0                         # estimated (characters / 4): the harness reports cost, not tokens


# ── the corpus doors ─────────────────────────────────────────────────────────────────────────────
def _blocked(row: dict[str, Any]) -> bool:
    """A row that would leak a price or our own earlier call (see module doc)."""
    return (row.get("product") == "markets" or str(row.get("id", "")).startswith(("market:", "event:market:")) or str(row.get("entity", "")).startswith("market:")
            or str(row.get("metric", "")).startswith("market.") or row.get("kind") == "market")


def _doc_hit(r: dict[str, Any], kind: str = "") -> Hit:
    return Hit(str(r.get("id", "")), kind or str(r.get("kind", r.get("type", ""))), str(r.get("date") or r.get("at") or ""), str(r.get("title") or r.get("text") or ""),
               str(r.get("detail") or r.get("snippet") or ""))


def _claim_hit(r: dict[str, Any]) -> Hit:
    return Hit(str(r["id"]), "claim", str(r.get("at") or r.get("created_at") or r.get("date") or ""), str(r.get("text") or r.get("snippet") or r.get("title") or ""),
               f"({r.get('status', '')})")


def _entity_hits(prof: dict[str, Any]) -> list[Hit]:
    e = prof["entity"]
    if e.get("kind") == "market":
        return []
    c = prof.get("counts", {})
    bits = [f"{e.get('kind')}; {c.get('documents', 0)} documents, {c.get('claims', 0)} claims, {c.get('events', 0)} events"]
    latest = prof.get("latest") or {}
    ev = latest.get("event")
    if ev and not _blocked(ev):
        bits.append(f"last event {str(ev.get('date', ''))[:10]}: {ev.get('title', '')}")
    else:
        ev = None
    obs = [f"{o['label'] or o['metric']} {o['value']} {o['unit']} ({o['basis']}, {str(o['ts'])[:10]})" for o in latest.get("observations", [])
           if not str(o.get("metric", "")).startswith("market.")]
    if obs:
        bits.append("latest numbers: " + "; ".join(obs[:4]))
    if prof.get("situations"):
        bits.append("situations: " + ", ".join(s["name"] for s in prof["situations"][:3]))
    rel = [f"{r['rel']} {r['name']}" for r in prof.get("relations", []) if not str(r.get("entity", "")).startswith("market:")][:5]
    if rel:
        bits.append("relations: " + "; ".join(rel))
    out = [Hit(f"entity:{e['id']}", "entity", str((ev or {}).get("date", "")), e.get("name", ""), " | ".join(bits))]
    out += [_doc_hit(t) for t in prof.get("timeline", [])[-4:] if not _blocked(t)]
    return out


def run_query(corpus: Any, q: Query, *, today: date) -> list[Hit]:
    """One planned query against the corpus, blind-filtered and capped. Raises on an unknown tool or a corpus error (the caller records it)."""
    since = q.since if q.since[:4].isdigit() else (today - timedelta(days=flags.RESEARCH_LOOKBACK_DAYS)).isoformat()
    kinds = {k for k in q.kinds if k} or None
    n = flags.RESEARCH_ROWS_PER_QUERY
    arg = q.arg.strip()
    hits: list[Hit]
    if q.tool == "entity":
        p = corpus.entity(arg)
        hits = _entity_hits(p) if p else []
    elif q.tool == "about":
        a = corpus.about(arg, since=since, kinds=kinds, limit=n)
        hits = []
        if a:
            hits = [*(_doc_hit(d) for d in a["documents"] if not _blocked(d)), *(_claim_hit(c) for c in a["claims"] if not _blocked(c)),
                    *(_doc_hit(e, e.get("kind", "event")) for e in a["events"] if not _blocked(e))]
    elif q.tool == "search":
        rows = [r for r in corpus.search(arg, kinds=kinds, since=since, limit=n * 2) if not _blocked(r)]
        hits = [_claim_hit(r) if r.get("type") == "claim" else _doc_hit(r) for r in rows]
    elif q.tool == "timeline":
        hits = [_doc_hit(r) for r in (corpus.timeline(arg, since=since, kinds=kinds, limit=n * 2) or []) if not _blocked(r)]
    elif q.tool == "related":
        rows = [r for r in (corpus.related(arg, limit=n * 2) or []) if not _blocked(r)]
        hits = [Hit(f"entity:{r['entity']}", "entity", "", r["name"], f"{r['kind']}; connection {r['score']} ({', '.join(f'{k} {v}' for k, v in r['via'].items())})")
                for r in rows]
    elif q.tool == "series":
        rows = [r for r in corpus.series(arg, since=since, points=True, limit=n * 2) if not _blocked(r)]
        hits = [Hit(f"series:{r['entity']}:{r['metric']}", "series", str((r.get("latest") or {}).get("ts", r["last"])), r["label"] or r["metric"],
                    f"{r.get('entity_name', '')}: {r['n']} points {str(r['first'])[:10]} to {str(r['last'])[:10]}; latest {(r.get('latest') or {}).get('value')} "
                    f"{r['unit']} ({r['basis']})") for r in rows]
    else:
        raise ValueError(f"unknown tool {q.tool!r}")
    return [h for h in hits if h.id][:n]


# ── the planner ──────────────────────────────────────────────────────────────────────────────────
def default_plan_ask() -> Any:
    from . import forecast

    return forecast.default_ask(PLAN_ROLE, Plan, flags.RESEARCH_PLAN_CAP_USD, flags.RESEARCH_PLAN_EFFORT, max_tokens=1200)


def plan_task(items: list[Item], found: dict[str, Found], today: date, round_no: int) -> str:
    parts = [f"TODAY: {today.isoformat()}", f"ROUND: {round_no + 1} of {flags.RESEARCH_MAX_ROUNDS}. Name at most {flags.RESEARCH_QUERIES_PER_ROUND} queries per question."]
    for it in items:
        parts.append(f"### {it.label}  {it.question}\nEnds: {it.end_date[:10] or 'unspecified'}\nRules: {' '.join(it.rules.split())[:500] or '(none)'}\n"
                     f"Countries: {', '.join(it.countries) or 'none'}; situations: {', '.join(it.theaters) or 'none'}")
        f = found.get(it.label)
        if f and f.hits:
            shown = [f"  [{h.id}] {h.title[:90]}" for h in list(f.hits.values())[:12]]
            parts.append(f"Already found for {it.label} ({len(f.hits)} items):\n" + "\n".join(shown))
        elif round_no:
            parts.append(f"Already found for {it.label}: nothing.")
    return "\n\n".join(parts) + "\n\nTASK: the corpus queries to run, each tagged with its question's label."


def research(items: list[Item], *, plan_ask: Any, corpus: Any, today: date, chars: int = flags.RESEARCH_CHARS_PER_MARKET) -> dict[str, Researched]:
    """Plan, run and read for a set of questions (one market, or a trade batch: the plan is one call either way). Per-item results; the planning
    cost and time are split evenly. A failed plan or query is recorded and the item simply has less to read; a budget refusal propagates."""
    t0 = time.monotonic()
    labels = {it.label for it in items}
    found = {it.label: Found() for it in items}
    usd, rounds = 0.0, 0
    for r in range(flags.RESEARCH_MAX_ROUNDS):
        try:
            out, spent = plan_ask(plan_task(items, found, today, r), PLAN_ROLE)
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ == "BudgetRefusedError":
                raise
            break
        usd += float(spent or 0.0)
        per: dict[str, int] = {}
        todo = []
        for q in getattr(out, "queries", None) or []:
            lab = (q.market or "").strip().upper() or (items[0].label if len(items) == 1 else "")
            if len(items) == 1:
                lab = items[0].label                 # one question: any label the planner wrote is that question
            if lab in labels and q.tool in TOOLS and q.arg.strip() and per.get(lab, 0) < flags.RESEARCH_QUERIES_PER_ROUND:
                per[lab] = per.get(lab, 0) + 1
                todo.append((lab, q))
        if not todo:
            break
        rounds += 1
        for lab, q in todo:
            s = time.monotonic()
            try:
                hits, err = run_query(corpus, q, today=today), ""
            except Exception as exc:  # noqa: BLE001
                hits, err = [], f"{type(exc).__name__}: {str(exc)[:100]}"
            new = found[lab].add(hits)
            found[lab].runs.append(QueryRun(tool=q.tool, arg=q.arg.strip()[:120], since=q.since, kinds=list(q.kinds), n=len(hits), ids=[h.id for h in hits],
                                            new=len(new), ms=int((time.monotonic() - s) * 1000), error=err))
    ms = int((time.monotonic() - t0) * 1000)
    share = round(usd / max(1, len(items)), 6)
    result = {}
    for it in items:
        f = found[it.label]
        text, ids = f.render(chars)
        result[it.label] = Researched(text=text, ids=ids, returned=list(f.hits), runs=f.runs, rounds=rounds, usd=share, ms=ms // max(1, len(items)),
                                      tokens=(len(text) + len(it.question) * 2) // 4)
    return result


def open_corpus() -> Any | None:
    """A read-only corpus handle, or None when no index was built here (the caller falls back and says so)."""
    try:
        from algent_backend.corpus.query import Corpus

        return Corpus.open()
    except Exception:  # noqa: BLE001 - CorpusMissing or an unreadable file: research is unavailable, not fatal
        return None


def item_for(label: str, m: Market) -> Item:
    return Item(label=label, question=m.question, rules=m.description, end_date=m.end_date, countries=list(m.countries), theaters=list(m.theaters))
