"""
Theater dossiers — one living page per theater that accumulates what Ohmega has learned about that
dynamic across every daily report and brief.

Mostly a deterministic aggregation over the desk's stores (cheap, and it compounds: every new report
makes every dossier a little richer). The one model-written part is the primer (``primers.py``): stable
background a newcomer lacks. Everything else is read, grouped and merged here with plain Python; no
numbers or claims are invented, and nothing is overwritten (the sources stay the source of truth).

Pure functions over plain dicts: ``build_all(Inputs)`` takes the already-read stores and returns
``{"theaters": {theater_id: dossier}, "index": index}``. Reading the stores and writing the files belong to
``publishing/intel_page.py``. Contract ``ohmega.dossier/1`` is documented in that module's docstring.

Rules this module owns:
- Identity is ``theater_id`` (the heat registry keeps ids stable across boards). A theater with at least one
  daily section or brief has a dossier.
- ``built_at`` is the time of the newest input that fed the dossier (not the wall clock), so an unchanged
  dossier is byte-identical and is never rewritten or re-committed.
- Reader-safe: every free text passes ``reader_safe``; internal ids (``src_...``) and non-http(s) URLs are
  dropped; a brief relation whose endpoints are not names (an id, or several relations jammed into one
  string) is skipped.
- Timeline merging lives in ``dossier_timeline.py`` (the merge rule is documented there).
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from . import dossier_timeline as tl
from . import geo, on_record
from .contracts import coverage_label

SCHEMA = "ohmega.dossier/1"
INDEX_SCHEMA = "ohmega.dossier.index/1"
TOP_ACTORS = 15
RECENT_STATEMENTS = 12
MAX_ON_RECORD = 150            # the theater's visible record: every statement its reports showed, newest first, bounded
MAP_HALF_LIFE_DAYS = 14.0       # a place's pull on the map halves every two weeks (ranking weight, not a gate)
_BANDS = ("unassessed", "calm", "elevated", "severe", "critical")
_HEADLINE_LIMIT, _DETAIL_LIMIT, _TEXT_LIMIT = 300, 1500, 700
_URL = re.compile(r"^https?://\S+$", re.I)
_INTERNAL_ID = re.compile(r"^src_[0-9a-f]+$", re.I)
_MONTH = (r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?")
_DATEISH = re.compile(rf"\b{_MONTH}\s*\d{{1,2}}(?:\s*[-–/]\s*\d{{1,2}})?\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b", re.I)
_DANGLING = re.compile(r"[\s,(\-–]*\b(?:on|as of|since|by|in|for|during|until|to)?[\s,)]*$", re.I)


@dataclass
class Inputs:
    """The stores, already read. ``boards`` newest first (a lazy iterable is fine); ``pulses`` is the Pulse
    registry catalog (None without a Pulse store); ``countries`` a basemap or a loader called only when a
    dossier has places."""

    reports: list[dict] = field(default_factory=list)
    briefs: list[dict] = field(default_factory=list)
    boards: Iterable[dict] = ()
    registry: dict[str, dict] = field(default_factory=dict)
    forecasts: list[dict] = field(default_factory=list)
    pulses: list[dict] | None = None
    primers: dict[str, dict] = field(default_factory=dict)
    countries: list | Callable[[], list | None] | None = None


# ── small helpers ─────────────────────────────────────────────────────────────────────────────
def _clean(text: Any, limit: int) -> str:
    # Lazy: the reader-safety rule is owned by the publishing layer; the desk must not import it at load.
    from algent_backend.publishing.agent_feed import reader_safe

    return reader_safe(str(text or ""), limit)


def _urls(items: Iterable[Any]) -> list[str]:
    return list(dict.fromkeys(u.strip() for u in items if isinstance(u, str) and _URL.match(u.strip())))


def _key(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _name(text: Any) -> str:
    """A usable actor/endpoint name, or '' (an internal id or a jammed-together blob is not a name)."""
    s = " ".join(str(text or "").split())
    return "" if not s or _INTERNAL_ID.match(s) or "->" in s or ";" in s else _clean(s, 120)


def _when(stamp: str) -> datetime:
    dt = datetime.fromisoformat((stamp or "1970-01-01").replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _newest(stamps: Iterable[str]) -> str:
    best, best_dt = "", None
    for s in stamps:
        try:
            dt = _when(s)
        except ValueError:
            continue
        if best_dt is None or dt > best_dt:
            best, best_dt = s, dt
    return best


def _daily_url(day: str) -> str:
    return f"/geopolitics/{day}"


def _brief_url(slug: str) -> str:
    return f"/intel/briefs/{slug}"


def _split_headline(what: str) -> tuple[str, str]:
    """A brief timeline item is one sentence: it is its own headline, and its own detail when long."""
    text = _clean(what, _DETAIL_LIMIT)
    if len(text) <= _HEADLINE_LIMIT:
        return text, ""
    return _clean(text, _HEADLINE_LIMIT), text


def _figure_label(label: str) -> str:
    """The label without the date the writer baked into it ('drones launched Oct 2-3' -> 'drones launched'),
    so the same figure on different days becomes one series."""
    out = " ".join(_DATEISH.sub(" ", label or "").replace("()", " ").split())
    out = " ".join(_DANGLING.sub("", out).split())
    return out or " ".join((label or "").split())


# ── per-theater accumulation ──────────────────────────────────────────────────────────────────
@dataclass
class _Acc:
    sections: dict[str, tuple[dict, dict]] = field(default_factory=dict)   # date -> (report, section)
    briefs: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)


def _collect(inp: Inputs) -> dict[str, _Acc]:
    acc: dict[str, _Acc] = defaultdict(_Acc)
    for report in sorted(inp.reports, key=lambda r: (r.get("date", ""), r.get("built_at", ""))):
        sections = [s for s in report.get("theaters") or [] if s.get("theater_id")]
        ids = {_key(s.get("name", "")): s["theater_id"] for s in sections}
        for s in sections:
            a = acc[s["theater_id"]]
            a.sections[report["date"]] = (report, s)             # a later build of the same day wins
            for cross in report.get("cross_theater") or []:
                names = [n for n in cross.get("theaters") or [] if isinstance(n, str)]
                if _key(s.get("name", "")) not in {_key(n) for n in names}:
                    continue
                for other in names:
                    if _key(other) != _key(s.get("name", "")):
                        a.links.append({"theater_id": ids.get(_key(other), ""), "name": other,
                                        "link": _clean(cross.get("link", ""), _TEXT_LIMIT), "date": report["date"]})
    for b in inp.briefs:
        if b.get("theater_id"):
            acc[b["theater_id"]].briefs.append(b)
    for a in acc.values():
        a.briefs.sort(key=lambda b: (b.get("as_of", ""), b.get("built_at", "")))
    return acc


def newest_board_rows(boards: Iterable[dict], wanted: set[str]) -> dict[str, dict]:
    """Per theater: its newest heat-board row and meta (``{row, theater}``); reads boards newest first and
    stops once every wanted theater is found."""
    found: dict[str, dict] = {}
    for board in boards:
        metas = {t.get("id"): t for t in board.get("theaters") or []}
        for row in board.get("heat") or []:
            tid = row.get("theater_id")
            if tid in wanted and tid not in found:
                found[tid] = {"row": row, "theater": metas.get(tid, {})}
        if wanted <= found.keys():
            break
    return found


# ── sections of the dossier ───────────────────────────────────────────────────────────────────
def _timeline(acc: _Acc) -> list[dict]:
    entries: list[tl.Entry] = []
    for day, (_report, s) in acc.sections.items():
        for d in s.get("developments") or []:
            if not (d.get("headline") or "").strip():
                continue
            entries.append(tl.Entry(
                date=tl.day_of(d.get("when", ""), day), headline=_clean(d["headline"], _HEADLINE_LIMIT),
                detail=_clean(d.get("detail", ""), _DETAIL_LIMIT), where=_clean(d.get("where", ""), 160),
                verification=d.get("verification") or "reported", sources=_urls(d.get("sources") or []),
                origin=_daily_url(day)))
    for b in acc.briefs:
        for item in b.get("timeline") or []:
            if not (item.get("what") or "").strip():
                continue
            headline, detail = _split_headline(item["what"])
            entries.append(tl.Entry(date=tl.day_of(item.get("date", ""), b.get("as_of", "")), headline=headline,
                                    detail=detail, verification=item.get("verification") or "reported",
                                    sources=_urls([item.get("source", "")]), origin=_brief_url(b["slug"])))
    return tl.merge(entries)


def _recency_weights(items: list[tuple[str, str]]) -> dict[str, float]:
    """key -> summed recency weight, normalised so the strongest is 1. Age is measured from the newest date
    in the dossier, never the wall clock, so a dossier does not change just because time passed."""
    newest = max((d for _k, d in items if d), default="")
    raw: dict[str, float] = defaultdict(float)
    for k, d in items:
        try:
            age = (date.fromisoformat(newest) - date.fromisoformat(d)).days
        except ValueError:
            age = 0
        raw[k] += 0.5 ** (max(age, 0) / MAP_HALF_LIFE_DAYS)
    top = max(raw.values(), default=0.0) or 1.0
    return {k: round(v / top, 3) for k, v in raw.items()}


def _place_of(d: dict) -> dict | None:
    """A development's place when it is well-formed (the desk already validated it against the basemap)."""
    p = d.get("place")
    try:
        lat, lon = float(p["lat"]), float(p["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    ok = p.get("name") and math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180
    return {"name": p["name"], "country": p.get("country", ""), "lat": lat, "lon": lon} if ok else None


def _places_and_map(acc: _Acc, countries: Any) -> tuple[list[dict], dict | None]:
    seen: dict[str, dict] = {}
    mentions: list[tuple[str, str]] = []
    for day, (_r, s) in sorted(acc.sections.items()):
        for d in s.get("developments") or []:
            p = _place_of(d)
            if p is None:
                continue
            key = f"{_key(p['name'])}|{_key(p['country'])}"
            at = tl.day_of(d.get("when", ""), day)
            row = seen.setdefault(key, {**p, "count": 0, "last_date": "", "verification": "reported"})
            row["count"] += 1
            if at >= row["last_date"]:
                row.update(lat=p["lat"], lon=p["lon"], last_date=at)
            if d.get("verification") == "researched":
                row["verification"] = "researched"
            mentions.append((key, at))
    weights = _recency_weights(mentions)
    ranked = sorted(seen.items(), key=lambda kv: (-weights[kv[0]], -kv[1]["count"], kv[1]["name"]))
    places = [{k: v for k, v in row.items() if k != "verification"} for _k, row in ranked]
    if not places:
        return [], None
    basemap = countries() if callable(countries) else countries
    spec = geo.build_map([{"place": {k: p[k] for k in ("name", "country", "lat", "lon")}, "when": p["last_date"],
                           "verification": row["verification"]} for p, (_k, row) in zip(places, ranked, strict=True)],
                         basemap)
    for pt in (spec or {}).get("points", []):        # n is 1-based into `places`; weight lets a page label what matters
        pt["weight"] = weights[ranked[pt["n"] - 1][0]]
    return places, spec


def _actors_and_relations(acc: _Acc) -> tuple[list[dict], list[dict]]:
    mentions: dict[str, dict] = {}

    def see(name: str, at: str) -> None:
        k = _key(name)
        row = mentions.setdefault(k, {"names": Counter(), "mentions": 0, "first": at, "last": at})
        row["names"][name] += 1
        row["mentions"] += 1
        row["first"], row["last"] = min(row["first"], at), max(row["last"], at)

    for day, (_r, s) in sorted(acc.sections.items()):
        for d in s.get("developments") or []:
            who = {n for n in (_name(x) for x in (d.get("actors") or []) +
                                                    [st.get("who") for st in d.get("statements") or []]) if n}
            for name in {_key(n): n for n in who}.values():          # once per development
                see(name, tl.day_of(d.get("when", ""), day))
    rel: dict[tuple[str, str, str], dict] = {}
    for b in acc.briefs:
        for r in b.get("relations") or []:
            src, dst = _name(r.get("source")), _name(r.get("target"))
            if not src or not dst:
                continue
            at = r.get("date") or b.get("as_of", "")
            see(src, at)
            see(dst, at)
            kind = r.get("kind") or "other"
            row = rel.setdefault((_key(src), _key(dst), kind), {"source": src, "target": dst, "kind": kind,
                                                                "count": 0, "last_date": "", "note": ""})
            row["count"] += 1
            if at >= row["last_date"]:
                row.update(last_date=at, note=_clean(r.get("note", ""), _TEXT_LIMIT))
    actors = sorted(({"name": r["names"].most_common(1)[0][0], "mentions": r["mentions"], "first": r["first"],
                      "last": r["last"]} for r in mentions.values()),
                    key=lambda a: (-a["mentions"], a["name"]))[:TOP_ACTORS]
    relations = sorted(rel.values(), key=lambda r: (-r["count"], r["last_date"], r["source"]))
    return actors, relations


def _figures(acc: _Acc) -> list[dict]:
    groups: dict[str, dict] = {}
    for day, (_r, s) in sorted(acc.sections.items()):
        for f in s.get("key_figures") or []:
            label = _figure_label(str(f.get("label") or ""))
            if not label or not isinstance(f.get("value"), (int, float)):
                continue
            unit = str(f.get("unit") or "")
            g = groups.setdefault(f"{_key(label)}|{_key(unit)}", {"label": label, "unit": unit, "series": {}})
            g["label"] = label                                                   # the newest wording
            as_of = tl.day_of(str(f.get("as_of") or ""), day)
            g["series"][as_of] = {"as_of": as_of, "value": f["value"], "source": (_urls([f.get("source", "")]) or [""])[0]}
    rows = [{"label": _clean(g["label"], 160), "unit": g["unit"], "series": [g["series"][k] for k in sorted(g["series"])]}
            for g in groups.values()]
    rows.sort(key=lambda g: g["label"])                   # then newest reading first, longest series first
    rows.sort(key=lambda g: g["series"][-1]["as_of"], reverse=True)
    return sorted(rows, key=lambda g: -len(g["series"]))


def _indicators(acc: _Acc) -> list[dict]:
    by_signal: dict[str, dict] = {}
    for b in acc.briefs:                                      # oldest first; a later brief the same day wins
        for i in b.get("indicators") or []:
            signal = " ".join(str(i.get("signal") or "").split())
            if signal:
                row = by_signal.setdefault(signal, {"signal": signal, "history": {}})
                row["history"][b.get("as_of", "")] = i.get("status", "")
    rows = [{"signal": r["signal"], "history": [{"date": d, "status": s} for d, s in sorted(r["history"].items())]}
            for r in by_signal.values()]
    return sorted(rows, key=lambda r: (r["history"][-1]["date"], len(r["history"])), reverse=True)


def _statements(acc: _Acc) -> list[dict]:
    seen: dict[tuple[str, str], tuple[str, dict]] = {}
    for day, (_r, s) in sorted(acc.sections.items()):
        for d in s.get("developments") or []:
            for st in d.get("statements") or []:
                if not (st.get("who") and st.get("said")):
                    continue
                at = tl.day_of(st.get("when", ""), day)
                seen[(_key(st["who"]), _key(st["said"]))] = (at, {
                    "who": _clean(st["who"], 120), "role": _clean(st.get("role", ""), 160),
                    "said": _clean(st["said"], _TEXT_LIMIT), "quote": bool(st.get("quote")),
                    "when": st.get("when", ""), "source": (_urls([st.get("source", "")]) or [""])[0]})
    return [row for _at, row in sorted(seen.values(), key=lambda v: v[0], reverse=True)[:RECENT_STATEMENTS]]


def _on_record(acc: _Acc) -> list[dict]:
    """Every statement the theater's dailies and briefs showed (their ``on_record``), deduped by statement
    id, newest first. Reports older than the field contribute nothing."""
    return on_record.merge([*(s.get("on_record") for _d, (_r, s) in sorted(acc.sections.items())),
                            *(b.get("on_record") for b in acc.briefs)], limit=MAX_ON_RECORD)


def _forecasts(tid: str, rows: list[dict]) -> list[dict]:
    mine = [f for f in rows if f.get("theater_id") == tid]
    open_ = sorted((f for f in mine if f["status"] == "open"), key=lambda f: f["horizon"])
    done = sorted((f for f in mine if f["status"] != "open"), key=lambda f: f.get("resolved_at", ""), reverse=True)
    mine = open_ + done                                   # what is still to be decided first, then the record
    return [{"id": f["id"], "statement": _clean(f["statement"], _TEXT_LIMIT), "probability": f["probability"],
             "horizon": f["horizon"], "status": f["status"],
             "resolution": None if f["status"] == "open" else
             {"resolved_at": f.get("resolved_at", ""), "outcome": f["status"],
              "evidence": _clean(f.get("evidence", ""), _TEXT_LIMIT)}} for f in mine]


def _pulses(acc: _Acc, catalog: list[dict] | None) -> list[dict]:
    """The Pulses this theater's sections and briefs reference, with their current values. Without a Pulse
    store the section rows' last-recorded values stand in (no history)."""
    named: dict[str, dict] = {}
    for _day, (_r, s) in sorted(acc.sections.items()):
        for p in s.get("pulses") or []:
            named[p.get("id") or p.get("name", "")] = p
    names = {p["name"] for p in named.values()}
    for b in acc.briefs:
        names.update(n for n in b.get("pulses") or [] if isinstance(n, str))
    if catalog is None:
        rows = [{"id": p.get("id", ""), "name": p.get("name", ""), "situation": "", "position": p.get("position"),
                 "band": p.get("band") or "unassessed", "history": []} for p in named.values() if p.get("name")]
    else:
        rows = [{"id": c["id"], "name": c["name"], "situation": c.get("situation", ""), "position": c.get("position"),
                 "band": c.get("band") or "unassessed", "history": c.get("history") or []}
                for c in catalog if c["id"] in named or c["name"] in names]
    return sorted(rows, key=lambda r: (r["position"] is None, -(r["position"] or 0), r["name"]))


# ── one dossier ───────────────────────────────────────────────────────────────────────────────
def _current(acc: _Acc, coverage: str) -> dict | None:
    daily = max(acc.sections.items(), key=lambda kv: kv[0], default=None)
    brief = acc.briefs[-1] if acc.briefs else None
    if daily and (brief is None or daily[0] >= brief.get("as_of", "")):
        day, (_r, s) = daily
        esc = s.get("escalation") or {}
        return {"date": day, "bottom_line": _clean(s.get("bottom_line", ""), _TEXT_LIMIT),
                "escalation": {"direction": esc.get("direction", "unclear"), "pace": esc.get("pace", "gradual")},
                "coverage": (s.get("temperature") or {}).get("coverage") or coverage, "source": "daily",
                "url": _daily_url(day)}
    if brief is None:
        return None
    esc = brief.get("escalation") or {}
    return {"date": brief.get("as_of", ""), "bottom_line": _clean(brief.get("bottom_line", ""), _TEXT_LIMIT),
            "escalation": {"direction": esc.get("direction", "unclear"), "pace": esc.get("pace", "gradual")},
            "coverage": coverage, "source": "brief", "url": _brief_url(brief["slug"])}


def build_one(tid: str, acc: _Acc, inp: Inputs, board: dict) -> dict:
    meta, row, theater = inp.registry.get(tid, {}), board.get("row") or {}, board.get("theater") or {}
    newest_section = acc.sections[max(acc.sections)][1] if acc.sections else {}
    newest_report = acc.sections[max(acc.sections)][0] if acc.sections else {}
    name = (meta.get("name") or theater.get("name") or newest_section.get("name")
            or (acc.briefs[-1].get("theater_name") if acc.briefs else "") or tid)
    days = sorted(acc.sections)
    coverage = coverage_label(row.get("trend", "")) if row else ""
    places, spec = _places_and_map(acc, inp.countries)
    actors, relations = _actors_and_relations(acc)
    pulses = _pulses(acc, inp.pulses)
    primer = inp.primers.get(tid)
    forecasts = _forecasts(tid, inp.forecasts)
    covered = [*days, *(b.get("as_of", "") for b in acc.briefs)]
    built = _newest([*(acc.sections[d][0].get("built_at", "") for d in days),
                     *(b.get("built_at", "") for b in acc.briefs), (primer or {}).get("built_at", ""),
                     *(h["at"] for p in pulses for h in p["history"][-1:])])
    return {
        "schema": SCHEMA, "theater_id": tid, "name": name,
        "domain": meta.get("domain") or theater.get("domain") or newest_report.get("domain", ""),
        "built_at": built, "first_seen": min((d for d in [meta.get("first_seen", ""), row.get("first_seen", ""), *covered] if d),
                          default=""),
        "last_seen": max((d for d in [meta.get("last_seen", ""), *covered] if d), default=""),
        "days_covered": len(days),
        "primer": {"text": primer["text"], "built_at": primer.get("built_at", "")} if primer else None,
        "current": _current(acc, coverage), "pulses": pulses,
        "escalation_history": [{"date": d, "direction": (acc.sections[d][1].get("escalation") or {}).get("direction", ""),
                                "pace": (acc.sections[d][1].get("escalation") or {}).get("pace", "")} for d in days],
        "coverage_series": [{"day": p.get("day", ""), "count": p.get("count", 0), "editions": p.get("editions", 0)}
                            for p in row.get("series") or []],
        "timeline": _timeline(acc), "places": places, "map": spec, "actors": actors, "relations": relations,
        "figures": _figures(acc), "forecasts": forecasts, "indicators": _indicators(acc),
        "statements": _statements(acc), "on_record": _on_record(acc),
        "links": _links(acc),
        "reports": [{"date": d, "url": _daily_url(d)} for d in reversed(days)],
        "briefs": [{"slug": b["slug"], "title": _clean(b.get("title", ""), _HEADLINE_LIMIT), "as_of": b.get("as_of", ""),
                    "url": _brief_url(b["slug"])} for b in reversed(acc.briefs)],
    }


def _links(acc: _Acc) -> list[dict]:
    out = {(_key(link["name"]), link["link"]): link for link in sorted(acc.links, key=lambda x: x["date"])}
    return sorted(out.values(), key=lambda x: x["date"], reverse=True)


def _row(d: dict, board: dict) -> dict:
    cur = d["current"] or {}
    band = max((p["band"] for p in d["pulses"]), key=lambda b: _BANDS.index(b) if b in _BANDS else 0, default="")
    row = board.get("row") or {}
    return {"theater_id": d["theater_id"], "name": d["name"], "domain": d["domain"], "first_seen": d["first_seen"],
            "last_seen": d["last_seen"], "days_covered": d["days_covered"], "heat": row.get("heat", 0.0),
            "coverage": cur.get("coverage") or (coverage_label(row.get("trend", "")) if row else ""),
            "escalation_direction": (cur.get("escalation") or {}).get("direction", ""), "max_band": band,
            "url": f"/intel/theaters/{d['theater_id']}"}


def build_all(inp: Inputs) -> dict:
    """Every theater's dossier and the index. ``{"theaters": {id: dossier}, "index": {...}}``."""
    acc = _collect(inp)
    boards = newest_board_rows(inp.boards, set(acc))
    dossiers = {tid: build_one(tid, a, inp, boards.get(tid, {})) for tid, a in sorted(acc.items())}
    rows = [_row(d, boards.get(tid, {})) for tid, d in dossiers.items()]
    rows.sort(key=lambda r: (r["last_seen"], r["heat"]), reverse=True)
    return {"theaters": dossiers,
            "index": {"schema": INDEX_SCHEMA, "built_at": _newest(d["built_at"] for d in dossiers.values()),
                      "theaters": rows}}
