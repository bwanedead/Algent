"""
The dailies and the briefs behind them (the intel store): per desk and day, a summary document and one document per theater section; each
development is a dated event and a claim carrying the URLs the desk cited; key figures are observations; theaters are situation entities that
link to their Pulses. Briefs add a document, a timeline of events, typed edges between the actors and the desk's probability judgments as claims.
"""

from __future__ import annotations

from collections.abc import Iterator

from algent_backend.agent_system.agents.intel import desk, heat
from algent_backend.agent_system.agents.intel.daily import daily_dir

from .. import flags
from ..norm import clip, day, digest, slug
from ..sink import Sink
from .base import Source, Unit, digest_of, file_digest, mark, read_json, rel, tree_mark


def situation_id(theater_id: str) -> str:
    return f"situation:{theater_id}"


def _section_body(s: dict) -> str:
    parts = [s.get(k) for k in ("bottom_line", "since_yesterday", "outlook")]
    wn = s.get("watch_next") or []
    parts += [("Watch next: " + " | ".join(wn if isinstance(wn, list) else [wn])) if wn else ""]
    parts += [d.get("headline") for d in (s.get("developments") or []) if isinstance(d, dict)]
    return " ".join(str(x) for x in parts if x)


def _since_list(v) -> list[str]:
    return [str(x) for x in (v if isinstance(v, list) else [v]) if x]


def _emit_section(domain: str, d: str, s: dict, url: str, sink: Sink) -> None:
    tid = s["theater_id"]
    doc = f"daily:{d}:{tid}"
    sit = situation_id(tid)
    sink.declare(sit, "situation", s.get("name") or tid, rank=flags.RANK_DECLARED, attrs={"domain": domain})
    sink.document(doc, "daily", domain=domain, date=d, title=f"{s.get('name', '')} (daily of {d})", url=url, status="researched", body=_section_body(s))
    sink.mention(entity=sit, document=doc, role="theater", date=d)
    for p in s.get("pulses") or []:
        if isinstance(p, dict) and p.get("id"):
            sink.relation("has_pulse", src=sit, dst=f"pulse:{p['id']}", document=doc, date=d)
    for fig in s.get("key_figures") or []:
        if isinstance(fig, dict) and isinstance(fig.get("value"), (int, float)) and fig.get("label"):
            sink.observation(f"kf.{slug(fig['label'])}", day(fig.get("as_of")) or d, fig["value"], entity=sit, unit=str(fig.get("unit") or ""),
                             basis="reported", label=str(fig["label"]), source_url=str(fig.get("source") or ""),
                             note=f"key figure of the {domain} daily; a cited figure, not our count")
    for dev in s.get("developments") or []:
        if not isinstance(dev, dict) or not dev.get("headline"):
            continue
        key = digest(d, tid, dev.get("when"), dev["headline"])        # per report: a development repeated in tomorrow's daily is that daily's own row
        place = dev.get("place") if isinstance(dev.get("place"), dict) else {}
        urls = [u for u in (dev.get("sources") or []) if isinstance(u, str)]
        text = clip(f"{dev['headline']}. {dev.get('detail') or ''}", 900)
        sink.event(f"dev:{key}", "development", date=dev.get("when") or d, title=dev["headline"], detail=" ".join([str(dev.get("detail") or ""), str(dev.get("significance") or "")]),
                   status=str(dev.get("verification") or ""), place=str(place.get("name") or dev.get("where") or ""), lat=place.get("lat"), lon=place.get("lon"),
                   document=doc, url=urls[0] if urls else "", actors=[a for a in dev.get("actors") or [] if isinstance(a, str)], actor_ids=[sit], role="theater")
        cid = f"claim:dev:{key}"
        sink.claim(cid, text, document_id=doc, status=str(dev.get("verification") or ""), grounding="cited" if urls else "uncited", created_at=d)
        for u in urls:
            sink.cite(cid, u)


def _emit_daily(domain: str, d: str, rec: dict, sink: Sink) -> None:
    url = f"/daily/{domain}/{d}"
    summary = rec.get("summary") or {}
    sink.document(f"daily:{d}:{domain}", "daily_summary", domain=domain, date=d, title=str(summary.get("headline") or f"{domain} daily {d}"), url=url,
                  status="researched" if rec.get("researched") else "", body=" ".join(_since_list(summary.get("the_day"))))
    for s in rec.get("theaters") or []:
        if isinstance(s, dict) and s.get("theater_id"):
            _emit_section(domain, d, s, url, sink)
    for link in rec.get("cross_theater") or []:
        names = link.get("theaters") or []
        if len(names) >= 2:
            sink.relation("linked_to", src_surface=names[0], dst_surface=names[1], document=f"daily:{d}:{domain}", date=d, note=str(link.get("link") or ""))


def _emit_brief(rec: dict, sink: Sink) -> None:
    slug_ = rec["slug"]
    doc = f"brief:{slug_}"
    d = day(rec.get("as_of"))
    sit = situation_id(rec["theater_id"]) if rec.get("theater_id") else None
    sink.document(doc, "brief", date=d, title=str(rec.get("title") or slug_), url=f"/intel/briefs/{slug_}", status="researched" if rec.get("researched") else "",
                  body=" ".join([str(rec.get("bottom_line") or ""), str(rec.get("situation") or ""), *map(str, rec.get("unknowns") or [])]))
    if sit:
        sink.declare(sit, "situation", str(rec.get("theater_name") or rec["theater_id"]), rank=flags.RANK_DECLARED)
        sink.mention(entity=sit, document=doc, role="theater", date=d)
    for i, t in enumerate(rec.get("timeline") or []):
        if isinstance(t, dict) and t.get("what"):
            sink.event(f"brief-timeline:{slug_}:{i}", "brief_timeline", date=str(t.get("date") or d), title=clip(t["what"], 200), detail=str(t["what"]),
                       status=str(t.get("verification") or ""), document=doc, actors=[a for a in t.get("actors") or [] if isinstance(a, str)])
    for r in rec.get("relations") or []:
        if isinstance(r, dict) and r.get("source") and r.get("target"):
            sink.relation(f"brief:{slug(r.get('kind') or 'related')}", src_surface=str(r["source"]), dst_surface=str(r["target"]), document=doc,
                          date=str(r.get("date") or d), note=str(r.get("note") or ""))
    for i, j in enumerate(rec.get("judgments") or []):
        if isinstance(j, dict) and j.get("statement"):
            cid = f"claim:brief:{slug_}:{i}"
            sink.claim(cid, f"{j['statement']} (by {j.get('horizon') or 'no date'})", document_id=doc, status="forecast", grounding="judgment",
                       confidence=f"{j.get('probability')}%", created_at=d)


def _daily_units() -> Iterator[Unit]:
    root = daily_dir("x").parent
    for folder in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else ():
        domain = folder.name
        for path in sorted(folder.glob("*.json")):
            yield Unit(f"daily:{domain}:{path.stem}", file_digest(path),
                       lambda sink, path=path, domain=domain: _emit_daily(domain, path.stem, read_json(path) or {}, sink),
                       date=path.stem, path=rel(path, root.parent))


def _brief_units() -> Iterator[Unit]:
    folder = desk.briefs_dir()
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else ():
        yield Unit(f"brief:{path.stem}", file_digest(path), lambda sink, path=path: _emit_brief(read_json(path) or {"slug": path.stem}, sink),
                   date=path.stem[:10], path=rel(path, folder.parent.parent))


def _theaters() -> Iterator[Unit]:
    reg = heat.registry()

    def emit(sink: Sink) -> None:
        for tid, t in sorted(reg.items()):
            sink.declare(situation_id(tid), "situation", str(t.get("name") or tid), rank=flags.RANK_DECLARED,
                         attrs={k: t.get(k) for k in ("domain", "state", "first_seen", "last_seen", "description") if t.get(k)})
    yield Unit("theaters:registry", digest_of(reg), emit, path="intel_store/theaters.json")


def _units() -> Iterator[Unit]:
    yield from _theaters()
    yield from _daily_units()
    yield from _brief_units()


def _watermark() -> str:
    root = daily_dir("x").parent
    return "|".join([tree_mark(root, "*.json"), tree_mark(desk.briefs_dir(), "*.json"), mark([heat.store_dir() / "theaters.json"])])


SOURCE = Source("dailies", "dailies", _units, _watermark)
