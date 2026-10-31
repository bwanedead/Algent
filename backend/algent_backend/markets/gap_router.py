"""
The gap router: which FREE feed should answer an ask, and does the corpus already hold the answer? Deterministic, no model call, offline over the local index.

Every gap cluster (``gaps.clusters``) is classified into a KIND by keyword rules (``classify``), then routed:

* ``feed:<product>``  a registered product is meant to answer this kind (``FEEDS``); the corpus is probed restricted to that product (``held``):
  ``retrieval_miss`` = the product holds matching items and the bot did not find them (fix retrieval, not coverage), ``coverage_miss`` = it does not hold them
  (the feed is missing something: a WANTED feed), "" = not probed (no index here, or past ``GAP_ROUTE_MAX_PROBES``);
* ``research``        no product answers this kind: the existing paid fill (``gaps.fill``) is the only way;
* ``unknowable``      a result or event dated after today: nothing, paid or free, can hold it yet.

``gaps.fill`` skips what a free feed answers (``skip_reason``); ``block`` is the published "what the bots asked for that we don't hold" view. Rules are
ordered, first match wins, and are tried on the topic, then topic + why, then the market question, so a Polymarket question never outvotes the ask.
"""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from . import flags, gaps

KINDS = ("poll", "result", "event", "schedule", "statement", "series", "status", "other")
LABEL = {"poll": "opinion polls", "result": "official election results", "event": "whether an event happened", "schedule": "meetings, dates and deadlines",
         "statement": "what officials said", "series": "numbers over time", "status": "who holds an office, or how things stand now", "other": "something else"}
#: kind -> the registered product (``ops/products/registry.py``) meant to answer it. ``other`` has none: only a paid research run can.
FEEDS = {"poll": "elections", "result": "elections", "event": "conflict", "schedule": "calendar", "statement": "statements", "series": "instruments", "status": "actors"}
#: A series ask about ship tracking goes to the AIS counter, not the chokepoint numbers.
_SHIPS = re.compile(r"\b(?:ais|dark fleet|shadow fleet|vessel positions?|ship positions?)\b", re.I)
PRODUCT_LABEL = {"elections": "elections feed", "conflict": "attack log", "calendar": "calendar", "statements": "statements record", "instruments": "numbers feed",
                 "actors": "country profiles", "maritime": "ship tracking"}

_ELECTION = r"election|vote|voting|ballot|runoff|run-off|referendum|primary|primaries|parliament\w*|presidential|gubernatorial|senate|congress\w*|mayoral"
#: (kind, pattern), first match wins. Word-bounded and lower-case folded; documented by tests/test_markets_gap_router.py.
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple((k, re.compile(p, re.I)) for k, p in (
    ("poll", r"\b(?:polls?|polling|pollsters?|seat projections?|generic ballot|approval ratings?|favou?rability|voting intentions?|exit polls?|margin of error)\b"),
    ("result", r"\b(?:cec|tse|ceni|inec|iec|electoral (?:commission|council|board)|certified (?:count|results?)|official results?|final results?|vote count)\b"
              rf"|(?=.*\b(?:{_ELECTION})\b)(?=.*\b(?:results?|counts?|tally|outcome|turnout|winners?|certified)\b)"),
    ("statement", r"\b(?:statements?|remarks|said|says|spokes(?:man|woman|person)|press conference|comments?|rhetoric|official position|declared|warned|vowed|pledged)\b"),
    ("event", r"\b(?:strikes?|struck|attacks?|attacked|bomb(?:ed|ing|ings)?|invasion|invade[sd]?|missiles?|drones?|shelling|clash(?:es)?|airstrikes?|raids?|explosions?|killed|"
             r"casualt(?:y|ies)|ceasefire|offensive|seiz(?:ed|ure)|shot down|sank|occurred|took place|happened)\b"),
    ("schedule", r"\b(?:meetings?|meet|summit|visit|talks|scheduled?|deadline|agenda|calendar|confirmed|planned|announced|postponed?|hearing|decisions?|dates?|when)\b"),
    ("series", r"\b(?:arrivals?|transits?|throughput|volumes?|prices?|indices|index|yields?|barrels|exports?|imports?|inflation|cpi|gdp|unemployment|portwatch|time series|"
              r"daily counts?|flows?|traffic|output|production|inventor(?:y|ies)|reserves|rates?|levels?)\b"),
    ("status", r"\b(?:current|currently|incumbent|head of (?:state|government)|prime minister|president of|who is|who leads|leader of|in office|holds? office|status of|acting)\b"),
))

_MON = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
_M = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_DATES = (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
          re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_M}(?:,?\s+(20\d\d))?", re.I),
          re.compile(rf"\b{_M}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(20\d\d))?", re.I))


def classify(topic: str, why: str = "", question: str = "") -> str:
    """The kind of ask: the first rule that matches the topic, else topic + why, else the market question; ``other`` when none does."""
    for text in (topic, f"{topic} {why}", question):
        for kind, pat in _RULES:
            if pat.search(text or ""):
                return kind
    return "other"


def cue_dates(text: str, today: date) -> list[date]:
    """Days written in ``text`` ("2026-11-05", "Oct 29", "29 October 2026"). A day with no year is this year's, or next year's when that is more than 200 days gone."""
    out: list[date] = []
    for i, pat in enumerate(_DATES):
        for m in pat.finditer(text or ""):
            g = m.groups()
            try:
                if i == 0:
                    d = date(int(g[0]), int(g[1]), int(g[2]))
                else:
                    day, mon, year = (int(g[0]), _MON[g[1][:3].lower()], g[2]) if i == 1 else (int(g[1]), _MON[g[0][:3].lower()], g[2])
                    d = date(int(year) if year else today.year, mon, day)
                    if not year and (today - d).days > 200:
                        d = date(today.year + 1, mon, day)
            except (ValueError, KeyError):
                continue
            out.append(d)
    return out


def unknowable(kind: str, text: str, today: date) -> str:
    """Why nothing can hold this yet, or "": a result or an event dated after today. A poll for a coming vote is knowable, so polls never qualify."""
    if kind not in ("result", "event"):
        return ""
    later = [d for d in cue_dates(text, today) if d > today]
    return f"dated {max(later).isoformat()}, after today" if later else ""


def route_of(kind: str, text: str = "") -> str:
    product = FEEDS.get(kind, "")
    if product == "instruments" and _SHIPS.search(text):
        product = "maritime"
    return f"feed:{product}" if product else "research"


# ── is it in the corpus? ─────────────────────────────────────────────────────────────────────
def _stems(words: Any) -> frozenset[str]:
    return frozenset(re.sub(r"(?:ing|ed|es|s)$", "", w) if len(w) > 4 else w for w in words)


def _overlap(topic: str, row: dict[str, Any]) -> bool:
    toks = _stems(gaps.tokens(topic))
    need = min(flags.GAP_ROUTE_MIN_OVERLAP, len(toks))
    return bool(toks) and len(toks & _stems(gaps.tokens(f"{row.get('title', '')} {row.get('snippet', '')}"))) >= need


def _door(corpus: Any, product: str, name: str) -> int:
    """Products that hold numbers or relations rather than searchable text: the series of an entity, or a country's leaders."""
    if product == "actors":
        prof = corpus.entity(name)
        return int(bool(prof and (prof.get("latest") or {}).get("leaders")))
    return sum(s.get("product") == product for s in corpus.series(name, points=False, limit=5))


def held(corpus: Any, product: str, topic: str) -> int:
    """How many items of ``product`` match the ask (0 = the product does not hold it). Full text restricted to the product, then, by the names in the ask, the
    product's series or leaders. Raises on a corpus error (the caller leaves the cluster unprobed)."""
    n = sum(_overlap(topic, r) for r in corpus.search(topic, products={product}, limit=10))
    if n:
        return n
    return sum(_door(corpus, product, name) for name in re.findall(r"\b[A-Z][A-Za-z]{3,}\b", topic)[:4])


@dataclass(frozen=True)
class Routed:
    key: str
    topic: str
    asks: int
    kind: str
    route: str
    diagnosis: str = ""                  # retrieval_miss | coverage_miss | "" (not probed, or no feed)
    held: int = 0
    reason: str = ""                     # set for unknowable

    @property
    def product(self) -> str:
        return self.route.removeprefix("feed:") if self.route.startswith("feed:") else ""

    def skip_reason(self) -> str:
        """Why ``gaps.fill`` should not pay to research this, or "" to leave it a candidate."""
        if self.route == "unknowable":
            return f"cannot be known yet ({self.reason})"
        if self.product == "elections":
            return "the free elections feed answers polls and results"
        if self.diagnosis == "retrieval_miss":
            return f"the {self.product} feed already holds it: the bot did not find it"
        return ""


def route_clusters(clusters: list[gaps.Cluster], now: datetime | None = None, corpus: Any | None = None) -> list[Routed]:
    """Classify and route every cluster; probe the first ``GAP_ROUTE_MAX_PROBES`` feed routes against ``corpus`` (None = open the local index; none there = unprobed)."""
    now = now or datetime.now(UTC)
    own = corpus is None
    if own:
        from .research import open_corpus
        corpus = open_corpus()
    out, probes = [], 0
    try:
        for c in clusters:
            text = f"{c.topic} {c.why}"
            kind = classify(c.topic, c.why, c.questions[0] if c.questions else "")
            why_not = unknowable(kind, text, now.date())
            route = "unknowable" if why_not else route_of(kind, text)
            diag, n = "", 0
            if route.startswith("feed:") and corpus is not None and probes < flags.GAP_ROUTE_MAX_PROBES:
                probes += 1
                try:
                    n = held(corpus, route[5:], c.topic)
                    diag = "retrieval_miss" if n >= flags.GAP_ROUTE_MIN_HITS else "coverage_miss"
                except Exception:  # noqa: BLE001 - an unreadable index leaves the cluster unprobed, never fails the job
                    diag = ""
            out.append(Routed(c.key, c.topic, c.asks, kind, route, diag, n, why_not))
    finally:
        if own and corpus is not None:
            corpus.close()
    return out


# ── the published view ───────────────────────────────────────────────────────────────────────
def route_label(route: str) -> str:
    if route == "unknowable":
        return "cannot be known yet"
    return PRODUCT_LABEL.get(route.removeprefix("feed:"), "a paid research run") if route.startswith("feed:") else "a paid research run"


def block(now: datetime | None = None, routed: list[Routed] | None = None) -> dict[str, Any]:
    """The ``routing`` block of the evidence section: asks per kind and route with held-but-missed vs not held, and the wanted feeds. Counts are asks."""
    now = now or datetime.now(UTC)
    routed = route_clusters(gaps.clusters(now), now) if routed is None else routed
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    wanted: dict[str, dict[str, Any]] = defaultdict(lambda: {"asks": 0, "clusters": 0, "topics": []})
    tot = {"clusters": len(routed), "asks": 0, "held_missed": 0, "not_held": 0, "unchecked": 0, "no_feed": 0, "unknowable": 0}
    for r in routed:
        row = rows.setdefault((r.kind, r.route), {"kind": r.kind, "label": LABEL[r.kind], "route": r.route, "route_label": route_label(r.route), "asks": 0, "clusters": 0,
                                                   "held_missed": 0, "not_held": 0, "unchecked": 0})
        row["asks"] += r.asks
        row["clusters"] += 1
        tot["asks"] += r.asks
        if r.route == "unknowable":
            tot["unknowable"] += r.asks
        elif not r.product:
            tot["no_feed"] += r.asks
        else:
            bucket = {"retrieval_miss": "held_missed", "coverage_miss": "not_held"}.get(r.diagnosis, "unchecked")
            row[bucket] += r.asks
            tot[bucket] += r.asks
        if r.route != "unknowable" and (r.diagnosis == "coverage_miss" or not r.product):
            w = wanted[r.kind]
            w.update(kind=r.kind, label=LABEL[r.kind], product=r.product, route_label=route_label(r.route))
            w["asks"] += r.asks
            w["clusters"] += 1
            if len(w["topics"]) < 3:
                w["topics"].append(r.topic)
    return {**tot, "rows": sorted(rows.values(), key=lambda x: -x["asks"]),
            "wanted": sorted(wanted.values(), key=lambda x: -x["asks"])[:flags.GAP_ROUTE_WANTED_SHOWN],
            "basis": ("Each ask is sorted by keyword rules into a kind of thing, then matched to the feed we run for that kind. 'We hold it but the bot did not find it' means that "
                      "feed has matching items in the corpus; 'not held' means it has none. Asks are counted per market that asked; similar asks are merged. "
                      f"Only the {flags.GAP_ROUTE_MAX_PROBES} most-asked topics are checked against the corpus each time.")}


def table(b: dict[str, Any]) -> str:
    """The block as plain text (``newsroom markets gaps route``)."""
    head = f"{'kind':<10}{'asks':>6}  {'route':<22}{'held, missed':>13}{'not held':>10}{'unchecked':>10}"
    lines = [f"{b['asks']} asks in {b['clusters']} topics; {b['held_missed']} held but missed, {b['not_held']} not held, {b['unchecked']} unchecked, "
             f"{b['no_feed']} need a paid run, {b['unknowable']} cannot be known yet", "", head]
    lines += [f"{r['kind']:<10}{r['asks']:>6}  {r['route']:<22}{r['held_missed']:>13}{r['not_held']:>10}{r['unchecked']:>10}" for r in b["rows"]]
    if b["wanted"]:
        lines += ["", "wanted feeds (asks, kind, product, examples):"]
        lines += [f"  {w['asks']:>4}  {w['kind']:<10}{w['product'] or '-':<12}{'; '.join(w['topics'])}" for w in b["wanted"]]
    return "\n".join(lines)
