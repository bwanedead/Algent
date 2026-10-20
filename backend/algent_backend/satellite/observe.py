"""
One site, one look: choose the clearest scenes, keep the chips, judge the pair, judge the night lights, append the record.

Baseline rule. A site with a dated damage statement gets its baseline from the clearest scene BEFORE that day (so the first look already is a
before / after); any other site's baseline is its first clear look. The baseline then never moves: every later scene is compared with it, and
the site's own history of those scores is what "unusual" means (``change.judge``). Failure of a source (SourceError) is recorded for the site, never
raised: one site's trouble must not stop the pass.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from algent_backend.polite_http import SourceError

from . import change, flags, png, store
from .sources import Imagery, Scene
from .watchlist import Site, bbox_of


@dataclass
class Pick:
    scene: Scene
    classes: list[int]
    quality: dict[str, float]
    scl_png: bytes


def pick_scene(src: Imagery, bbox: Any, start: str, end: str) -> Pick | None:
    """The clearest of the newest ``CANDIDATES`` scenes over the bbox (measured on the chip's own classes, not the tile's cloud); ties go to the newer."""
    best: Pick | None = None
    for sc in sorted(src.search(bbox, start, end), key=lambda s: s.datetime, reverse=True)[:flags.CANDIDATES]:
        raw = src.scl(sc, bbox)
        classes = change.scl_classes(png.decode(raw))
        q = change.chip_quality(classes)
        if q["nodata_pct"] / 100.0 > flags.MAX_NODATA:
            continue
        if best is None or q["cloud_pct"] < best.quality["cloud_pct"]:     # newest first, so a tie stays with the newer scene
            best = Pick(sc, classes, q, raw)
    return best


def chip_name(scene: Scene) -> str:
    return f"{scene.date}-{hashlib.sha1(scene.id.encode()).hexdigest()[:6]}.png"


def _meta(site: Site, pick: Pick) -> dict[str, Any]:
    return {"scene": pick.scene.id, "date": pick.scene.date, "tile_cloud_pct": round(pick.scene.tile_cloud, 1),
            "local_cloud_pct": pick.quality["cloud_pct"], "nodata_pct": pick.quality["nodata_pct"],
            "chip": f"satellite/{site.id}/{chip_name(pick.scene)}", "source": "Copernicus Sentinel-2 L2A via Microsoft Planetary Computer"}


def _save_chip(site: Site, pick: Pick, rgb: bytes) -> None:
    store.write_bytes(f"chips/{site.id}/{chip_name(pick.scene)}", rgb)


def _optical(site: Site, src: Imagery, state: dict[str, Any], hist: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    bbox = bbox_of(site.lat, site.lon, site.half_km)
    today = now.date()
    latest = pick_scene(src, bbox, (today - timedelta(days=flags.LOOKBACK_DAYS)).isoformat(), today.isoformat())
    if latest is None:
        return {"state": "no_scene", "note": f"no usable Sentinel-2 scene in the last {flags.LOOKBACK_DAYS} days"}
    base_meta = state.get("baseline")
    if base_meta is None:
        before = None
        if site.event_on:
            ev = date.fromisoformat(site.event_on)
            before = pick_scene(src, bbox, (ev - timedelta(days=flags.BASELINE_LOOKBACK_DAYS)).isoformat(), (ev - timedelta(days=1)).isoformat())
        first = before or latest
        rgb = src.rgb(first.scene, bbox)
        store.write_bytes(f"sites/{site.id}/baseline.png", rgb)
        store.write_bytes(f"sites/{site.id}/baseline_scl.png", first.scl_png)
        _save_chip(site, first, rgb)
        base_meta = {**_meta(site, first), "before_event": before is not None}
        state["baseline"] = base_meta
    out: dict[str, Any] = {"state": "ok", "baseline": base_meta}
    last = state.get("latest")
    if last and last["scene"] == latest.scene.id:
        out.update(state="repeat", latest=last, judgement=state.get("judgement"))
        return out
    rgb = src.rgb(latest.scene, bbox)
    meta = _meta(site, latest)
    out["latest"] = meta
    if latest.scene.date <= base_meta["date"]:
        out.update(state="waiting", note="no scene newer than the baseline yet")
        store.write_bytes(f"sites/{site.id}/last.png", rgb)
        store.write_bytes(f"sites/{site.id}/last_scl.png", latest.scl_png)
        _save_chip(site, latest, rgb)
        return out
    base_img = png.decode(store.read_bytes(f"sites/{site.id}/baseline.png") or b"")
    base_scl = change.scl_classes(png.decode(store.read_bytes(f"sites/{site.id}/baseline_scl.png") or b""))
    pair = change.compare(base_img, base_scl, png.decode(rgb), latest.classes)
    scores = [r["optical"]["judgement"]["score"] for r in hist
              if (r.get("optical") or {}).get("state") == "ok" and (r["optical"].get("baseline") or {}).get("scene") == base_meta["scene"]
              and (r["optical"].get("judgement") or {}).get("label") != "inconclusive" and (r["optical"]["judgement"].get("score") is not None)]
    since = hist[0]["at"][:10] if hist else now.date().isoformat()
    out["judgement"] = change.judge(pair, scores, since)
    store.write_bytes(f"sites/{site.id}/last.png", rgb)
    store.write_bytes(f"sites/{site.id}/last_scl.png", latest.scl_png)
    _save_chip(site, latest, rgb)
    return out


def _night(site: Site, src: Imagery, state: dict[str, Any], hist: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    day = (now - timedelta(days=flags.NIGHT_LAG_DAYS)).date().isoformat()
    if (state.get("night") or {}).get("date") == day:
        return state["night"]
    box = (site.lon - flags.NIGHT_HALF_DEG, site.lat - flags.NIGHT_HALF_DEG, site.lon + flags.NIGHT_HALF_DEG, site.lat + flags.NIGHT_HALF_DEG)
    stats = change.night_stats(png.decode(src.night(box, day)))
    seen = {(r["night"] or {}).get("date"): (r["night"] or {}).get("value") for r in hist if (r.get("night") or {}).get("value") is not None}
    since = hist[0]["at"][:10] if hist else now.date().isoformat()
    verdict = change.judge_night(stats["mean"], [v for d, v in seen.items() if d != day], since)
    return {"date": day, "lit_share": stats["lit_share"], "source": "NASA GIBS VIIRS DayNightBand (gap-filled, lunar and BRDF corrected)", **verdict}


def observe(site: Site, src: Imagery, now: datetime, pass_id: str) -> dict[str, Any]:
    """Look at one site; update its state, append its record, return the record."""
    state = store.read_json(f"sites/{site.id}/state.json", {}) or {}
    hist = store.records(site.id)
    rec: dict[str, Any] = {"v": 1, "at": now.isoformat(timespec="seconds"), "pass_id": pass_id, "site_id": site.id}
    try:
        opt = _optical(site, src, state, hist, now)
    except (SourceError, ValueError) as exc:
        opt = {"state": "error", "note": f"{type(exc).__name__}: {str(exc)[:160]}"}
    rec["optical"] = opt
    if site.kind == "asset":
        try:
            rec["night"] = _night(site, src, state, hist, now)
        except (SourceError, ValueError) as exc:
            rec["night"] = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    store.append_record(rec)
    if opt["state"] in ("ok", "waiting", "repeat"):
        state["latest"] = opt.get("latest", state.get("latest"))
        if opt.get("judgement"):
            state["judgement"] = opt["judgement"]
    if rec.get("night") and "error" not in rec["night"]:
        state["night"] = rec["night"]
    state.update(checked_at=now.timestamp(), state=opt["state"], note=opt.get("note", ""))
    store.write_json(f"sites/{site.id}/state.json", state)
    keep = {m["chip"].rsplit("/", 1)[-1] for m in (state.get("baseline"), state.get("latest")) if m}
    store.prune_chips(site.id, keep | _recent(site.id, state))
    return rec


def _recent(site_id: str, state: dict[str, Any]) -> set[str]:
    """The newest ``KEEP_DATED`` dated chips on disk (by file name, which leads with the scene date)."""
    d = store.root() / "chips" / site_id
    names = sorted((p.name for p in d.glob("*.png")), reverse=True) if d.is_dir() else []
    return set(names[:store.KEEP_DATED])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
