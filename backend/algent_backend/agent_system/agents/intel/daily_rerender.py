"""
Redo a day's daily WITHOUT the model: re-render from the draft archive, or (for old days) tag places once.

``rerender`` re-derives a saved record from ``daily_drafts`` (the models' raw output plus the guards' inputs):
every section's guards, places and maps, numbers panel, Pulse table, on-record order, the summary's derived
bits and the sweep's validation. It makes ZERO model calls, so fixing the environment (a basemap that was
missing on the server) or adding a display feature never re-buys content that was fine. It is the path the
targeted rerun already is, minus the paying: ``--theater`` limits it to those sections.

``tag_places`` is a REPAIR TOOL for reports made before the archive existed (their drafts were never kept, so
their places were lost with the basemap): ONE small structured call per report, never per section, gives each
development a place from its headline; the existing text is not touched, every place is checked against the
basemap, and the maps are rebuilt deterministically. Not a normal step; a day with an archive needs
``rerender`` instead.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from pydantic import BaseModel, Field

from . import daily, daily_drafts, daily_editions, desk, geo, render
from . import sweep as sweep_mod
from .brief import safe_name
from .contracts import DaySummary, Place


def _load_record(domain: str, as_of: str) -> tuple[Any, dict | None]:
    path = daily.daily_dir(domain) / f"{as_of}.json"
    return path, (json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None)


def _publish_html(record: dict, domain: str, out: Any, result: dict) -> None:
    if out is not None:
        html = out / f"daily_{safe_name(domain)}.html"
        html.write_text(render.render_daily(record), encoding="utf-8")
        result["html"] = str(html)


def rerender(domain: str, as_of: str, *, only: list[str] | tuple[str, ...] = (), out: Any = None,
             countries: list[geo.Country] | None = None, store: Any = None) -> dict:
    """Re-derive ``as_of``'s record from its draft archive and write it back; nothing is asked of any model.

    ``only`` limits the sections redone (ids or unique name fragments, as ``--theater``); the summary's and
    the sweep's derived bits are redone whenever the whole day is. ``countries`` defaults to the installed
    basemap and ``store`` to the Pulse store; a missing basemap is reported as a warning (places stay
    dropped from the PUBLISHED record, but remain in the archive for the next rerender). Returns
    ``{"report", "path", "redone", "kept", "warnings"}`` or ``{"error"}``."""
    from algent_backend.agent_system.agents.pulse.repository import pulse_store

    path, record = _load_record(domain, as_of)
    if record is None:
        return {"error": f"no daily record at {path}"}
    archives = {n: daily_drafts.load(domain, as_of, n) for n in daily_drafts.editions_present(domain, as_of)}
    if not archives:
        return {"error": f"no draft archive for {domain} {as_of} (it was produced before drafts were kept, so there "
                         f"is nothing to rerender; `--tag-places` can restore its places with one small call)"}
    countries = geo.load() if countries is None else countries
    store = store if store is not None else pulse_store()
    in_record = [SimpleNamespace(id=s.get("theater_id", ""), name=s.get("name", "")) for s in record.get("theaters") or []]
    try:
        chosen = ({t.id for t in daily.resolve_theaters(list(only), {t.id: t for t in in_record})} if only
                  else {t.id for t in in_record})
    except ValueError as exc:
        return {"error": str(exc)}
    now = datetime.fromisoformat(f"{as_of}T23:59:59+00:00")
    redone, kept = [], []

    def redo(sec: dict) -> dict:
        """One section (or update) re-derived from its own edition's draft; left as published without one."""
        tid, n = sec.get("theater_id", ""), sec.get("edition", 1)
        saved = ((archives.get(n) or {}).get("theaters") or {}).get(tid)
        if tid not in chosen:
            return sec
        if saved is None:                      # chosen, but its draft was never kept: left as published
            kept.append(tid)
            return sec
        new, _ = daily.finish_section(saved["draft"], saved["inputs"], tid=tid, countries=countries, store=store,
                                      now=now, as_of=as_of, brief=desk.previous_brief(tid))
        new["edition"] = n
        for key in ("spotlight", "kind", "update_of"):      # what the slot is, not what the text says
            if sec.get(key):
                new[key] = sec[key]
        redone.append(tid)
        return new

    sections = []
    for sec in record.get("theaters") or []:
        new = redo(sec)
        if sec.get("updates"):
            new["updates"] = [redo(u) for u in sec["updates"]]
        sections.append(new)
    record["theaters"] = sections
    if not only:
        _rederive_top(record, archives, countries)
    desk._write(path, record)
    result: dict[str, Any] = {"report": record, "path": str(path), "redone": redone, "kept": kept,
                              "warnings": [] if countries else ["no basemap loaded: places and maps stay off the "
                                                                "published record (the drafts keep them)"]}
    _publish_html(record, domain, out, result)
    return result


def _rederive_top(record: dict, archives: dict[int, dict | None], countries: list[geo.Country] | None) -> None:
    """The summary's and the sweep's derived bits from their saved raw drafts, one edition at a time (each only
    when it was saved). The last edition's summary is the day's; each part's ``editions`` row keeps its own, built
    from the sections that existed at that part."""
    known_iso = {k.upper() for c in (countries or ()) for k in (c.keys or ()) if len(k) == 2} or None
    spot = ((record.get("sweep") or {}).get("spotlight") or {}).get("text", "")
    regions: list[dict] | None = None
    for n in sorted(archives):
        arc = archives[n] or {}
        upto = [{**s, "updates": [u for u in s.get("updates") or [] if u.get("edition", 1) <= n]}
                for s in record["theaters"] if s.get("edition", 1) <= n]
        if (raw := (arc.get("summary") or {}).get("draft")) is not None:
            summary = daily.normalise_summary(DaySummary.model_validate(raw), upto)
            record["summary"] = {"headline": summary.headline, "the_day": summary.the_day}
            record["cross_theater"] = [c.model_dump() for c in summary.cross_theater]
            for entry in record.get("editions") or []:
                if entry.get("n") == n:
                    entry["summary"] = dict(record["summary"])
        if arc.get("sweep") and isinstance(record.get("sweep"), dict):
            got = sweep_mod.regions_from_archive(arc["sweep"], known_iso=known_iso, spotlight_text=spot)
            regions = got if regions is None else daily_editions.merge_regions(regions, got, n)
    if regions is not None and isinstance(record.get("sweep"), dict):
        record["sweep"]["regions"] = regions


# ── the repair tool for days that have no archive ─────────────────────────────────────────────
TAG_ROLE = """\
You place news developments on a map. For each numbered development (given by its headline and the place
text the desk wrote for it) give the named city or site where it happened as `name`, `country` (the common
English name; "sea" for a sea lane or open water), `lat` and `lon`. Give a place ONLY when the development has
a specific named location whose coordinates you know; omit it when unsure. A wrong point is worse than none:
the desk checks every one against a map and drops those outside the country. Do not rewrite or judge the
developments; you only locate them.
"""


class PlaceTag(BaseModel):
    ref: str = Field(description="The development's reference exactly as listed, like T2.4.")
    place: Place | None = None


class PlaceTags(BaseModel):
    tags: list[PlaceTag] = Field(default_factory=list)


def tag_places(ctx: Any, model_spec: Any, domain: str, as_of: str, *, out: Any = None,
               countries: list[geo.Country] | None = None) -> dict:
    """Give an archive-less record's developments places: ONE structured call for the whole report. Text is
    never changed; only developments with no place gain one, and only if it validates against the basemap.
    The maps are rebuilt. Returns ``{"report", "path", "tagged", "asked"}`` or ``{"error"}``."""
    path, record = _load_record(domain, as_of)
    if record is None:
        return {"error": f"no daily record at {path}"}
    countries = geo.load() if countries is None else countries
    if not countries:
        return {"error": "no basemap loaded: places cannot be validated, so none would be kept; fix that first"}
    refs: dict[str, dict] = {}
    lines = []
    for si, sec in enumerate(record.get("theaters") or []):
        lines.append(f"T{si} {sec.get('name', '')}")
        for di, dev in enumerate(sec.get("developments") or []):
            if not dev.get("place"):
                refs[f"T{si}.{di}"] = dev
                lines.append(f"  T{si}.{di}: {dev.get('headline', '')} [{dev.get('where', '')}]")
    if not refs:
        return {"report": record, "path": str(path), "tagged": 0, "asked": 0}
    got = daily._ask(ctx, None, model_spec, PlaceTags, TAG_ROLE,
                     "DEVELOPMENTS (theater, then reference: headline [where]):\n" + "\n".join(lines)
                     + "\n\nTASK: place the developments you can.")
    if not isinstance(got, PlaceTags):   # a failed call is an error to report, never a silent "nothing to place"
        return {"error": f"place tagging call returned no result ({type(got).__name__}); nothing changed"}
    tagged = 0
    for tag in got.tags:
        dev = refs.get(tag.ref.strip())
        valid = geo.validate_place(tag.place, countries) if dev is not None else None
        if valid:
            dev["place"] = valid
            tagged += 1
    for sec in record["theaters"]:
        sec["map"] = geo.build_map(sec.get("developments") or [], countries)
    desk._write(path, record)
    result: dict[str, Any] = {"report": record, "path": str(path), "tagged": tagged, "asked": len(refs)}
    _publish_html(record, domain, out, result)
    return result
