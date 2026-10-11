"""
The daily's sourced material, numbered — the ground a daily visual may stand on.

``visuals`` plans from, and its figures are checked against, ONLY what is here: each theater's developments,
key figures, tracker readings and the annual statistics of its actors, every line carrying the sources the
record already holds for it. Deterministic, no model, no network. A number that is not in a ``Fact`` is not
grounded, and the planner may cite facts by id but may not write numbers of its own.

``profile_of`` is the small adapter that lets the article analytics worker (which is built around a
``SignalProfile``) draw from these facts unchanged: one Claim per fact, one SourceArtifact per source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from algent_backend.agent_system.agents.research.profile import Claim, SignalProfile, SourceArtifact

TREND_FACTS_PER_ACTOR = 4      # prompt-size bounds, not judgements about the data
ACTORS_PER_THEATER = 3
_BARE_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass
class Fact:
    id: str                       # f<theater index>.<n>, the id the planner cites
    theater_id: str
    kind: str                     # development | figure | tracker | actor | trend
    text: str
    sources: list[str] = field(default_factory=list)    # URLs, or a named dataset when there is no URL

    @property
    def has_number(self) -> bool:
        """A figure beyond dates and years (the only facts a chart can be drawn from)."""
        return any(len(n) > 2 or "." in n for n in _BARE_NUMBER.findall(_DATE.sub("", self.text)))


def num(v: float) -> str:
    """A plain decimal, never scientific and never with thousands commas (the worker's figure check reads digits)."""
    return f"{float(v):.4f}".rstrip("0").rstrip(".")


def _dev_facts(tid: str, ti: int, devs: list[dict], out: list[Fact]) -> None:
    for d in devs:
        bits = [d.get("headline", ""), d.get("detail", ""), d.get("significance", "")]
        for s in d.get("statements") or []:
            if s.get("said"):
                bits.append(f"{s.get('who', '')}: {s['said']}")
        text = " ".join(b.strip() for b in bits if b and b.strip())
        when = d.get("when") or ""
        if text:
            out.append(Fact(f"f{ti}.{len(out) + 1}", tid, "development", f"{when}: {text}" if when else text,
                            list(d.get("sources") or [])))


def _figure_facts(tid: str, ti: int, figs: list[dict], out: list[Fact]) -> None:
    for f in figs:
        text = f"{f.get('label', '')}: {num(f['value'])} {f.get('unit', '')}".strip()
        if f.get("baseline") is not None:
            text += f" (against {f.get('baseline_label') or 'baseline'}: {num(f['baseline'])})"
        if f.get("as_of"):
            text += f", as of {f['as_of']}"
        out.append(Fact(f"f{ti}.{len(out) + 1}", tid, "figure", text, [f["source"]] if f.get("source") else []))


def _numbers_facts(tid: str, ti: int, block: dict, out: list[Fact]) -> None:
    for t in block.get("trackers") or []:
        text = f"{t.get('name', '')}: {num(t['value'])} {t.get('unit', '')}, as of {t.get('as_of', '')}".strip()
        spark = [num(v) for v in (t.get("spark") or [])[-12:]]
        if spark:
            text += f"; latest readings oldest to newest: {', '.join(spark)}"
        out.append(Fact(f"f{ti}.{len(out) + 1}", tid, "tracker", text,
                        [t["source_url"]] if t.get("source_url") else ([t["source"]] if t.get("source") else [])))
    for a in (block.get("actors") or [])[:ACTORS_PER_THEATER]:
        metrics = a.get("metrics") or {}
        latest = "; ".join(f"{m['label']} {num(m['value'])} {m.get('unit', '')} ({m.get('year', '')})".replace("  ", " ")
                           for m in metrics.values() if m.get("label") and m.get("value") is not None)
        if latest:
            out.append(Fact(f"f{ti}.{len(out) + 1}", tid, "actor", f"{a.get('name', '')}, latest annual statistics: {latest}",
                            sorted({m.get("source", "") for m in metrics.values() if m.get("source")})))
        trended = [m for m in metrics.values() if len(m.get("trend") or []) >= 5]
        for m in trended[:TREND_FACTS_PER_ACTOR]:
            pts = ", ".join(f"{int(y)}={num(v)}" for y, v in m["trend"])
            out.append(Fact(f"f{ti}.{len(out) + 1}", tid, "trend",
                            f"{a.get('name', '')} {m.get('label', '')} ({m.get('unit', '')}) by year: {pts}",
                            [m["source"]] if m.get("source") else []))


def collect(sections: list[dict]) -> list[Fact]:
    """Every sourced line of the day, numbered per theater. Tolerates a missing or odd block."""
    facts: list[Fact] = []
    for ti, s in enumerate(sections, 1):
        tid = str(s.get("theater_id") or "")
        mine: list[Fact] = []
        for fn, key in ((_dev_facts, "developments"), (_figure_facts, "key_figures")):
            try:
                fn(tid, ti, s.get(key) or [], mine)
            except (KeyError, TypeError, ValueError):
                continue
        try:
            _numbers_facts(tid, ti, s.get("numbers") or {}, mine)
        except (KeyError, TypeError, ValueError):
            pass
        facts.extend(mine)
    return facts


def source_label(src: str) -> tuple[str, str]:
    """(label, url) for a fact source: a URL gets its host, a dataset key stays a name with no link."""
    if src.startswith(("http://", "https://")):
        return urlparse(src).hostname.removeprefix("www.") if urlparse(src).hostname else src, src
    return {"wb": "World Bank", "owid": "Our World in Data", "imf": "IMF", "bis": "BIS"}.get(src, src), ""


def profile_of(facts: list[Fact], *, domain: str, as_of: str) -> SignalProfile:
    """The worker's input: a SignalProfile whose claims ARE the facts (ids kept), sources the facts' sources."""
    sources: dict[str, SourceArtifact] = {}
    for f in facts:
        for src in f.sources:
            if src not in sources:
                label, url = source_label(src)
                sources[src] = SourceArtifact(id=f"dvs{len(sources) + 1}", url=url, title=label, publisher=label)
    claims = [Claim(id=f.id, text=f.text, status="likely", grounding="snippet_only" if f.sources else "unsourced",
                    supported_by=[sources[s].id for s in f.sources]) for f in facts]
    return SignalProfile(id=f"daily_{domain}_{as_of}", title=f"{domain} daily {as_of}",
                         summary="The day's sourced developments, statistics and readings.", as_of=as_of,
                         source_ledger=list(sources.values()), claim_ledger=claims)
