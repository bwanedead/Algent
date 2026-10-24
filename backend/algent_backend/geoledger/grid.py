"""
Grid-impact rollups: what share of a country's installed generating capacity has been CLAIMED struck, REPORTED damaged,
CONFIRMED damaged or destroyed, and RESTORED over a window, split by fuel. Original intelligence, derived from the ledger
(WRI/OSM capacity x the dated status events), labelled ``ohmega_derived`` wherever it is shown.

    rollup(ledger, iso, as_of)       the document: installed MW by fuel, per window (7, 30 days) the four stances in MW
                                     and as a share of installed capacity, affected plants, a 30-day series, caveats
    line(doc)                        the one-sentence form the daily's writer is handed and may cite
    publish_rollups(ledger, ...)     one tiny row per country in ``geo_grid`` (migration 010); never raises

Claims and confirmations are separate numbers that OVERLAP (a plant claimed struck and later confirmed damaged is in both):
they are never added. ``buckets`` is the exclusive view the bar draws: each affected plant counted once, at the firmest
thing said about it in the window (confirmed > reported > claimed), or as restored when restoration is the latest word.

Honest limits, printed with every rollup: WRI is not complete (OSM plants add some), capacity is nameplate not output,
and a status says something was said on a day, not how long the lights were out.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from algent_backend.publishing import site_data
from algent_backend.publishing.published_db import _run

from .contracts import Asset, StatusEvent, latest
from .store import Ledger

WINDOWS = (7, 30)
SERIES_DAYS = 30
MAX_AFFECTED = 60
FUELS = ("thermal", "hydro", "nuclear", "renewables", "other")
STANCES = ("claimed", "reported", "confirmed", "restored")
_STATUS_STANCE = {"claimed_struck": "claimed", "reported_damaged": "reported", "confirmed_damaged": "confirmed", "destroyed": "confirmed"}
_FUEL_CLASS = {
    "thermal": ("coal", "gas", "oil", "petcoke", "cogeneration", "waste", "diesel", "lignite", "peat", "fossil", "natural gas", "heat"),
    "hydro": ("hydro", "water", "pumped"),
    "nuclear": ("nuclear", "uranium"),
    "renewables": ("solar", "wind", "biomass", "geothermal", "wave", "tidal", "biogas", "biofuel"),
}
CAVEATS = (
    "Capacity is nameplate megawatts, not output: a damaged plant may have been idle, and a struck plant may keep part of its output.",
    "A status says something was said on a day, not for how long the plant was out; no outage duration is inferred.",
    "Plants come from the WRI Global Power Plant Database (and OpenStreetMap where it adds named plants); coverage is incomplete, so shares are of capacity the ledger knows.",
    "Claimed and confirmed are separate tallies that overlap; they must not be added.",
)
_MISSING_CAPACITY = "{n} affected plant(s) have no capacity on record and are listed but add no megawatts."


def fuel_class(fuel: str) -> str:
    """thermal | hydro | nuclear | renewables | other, from a WRI primary fuel or an OSM ``plant:source`` value."""
    f = (fuel or "").casefold()
    for cls, words in _FUEL_CLASS.items():
        if any(w in f for w in words):
            return cls
    return "other"


def _mw(a: Asset) -> float | None:
    v = a.attrs.get("capacity_mw")
    return float(v) if isinstance(v, (int, float)) and v > 0 else None


def plants(ledger: Ledger, iso: str) -> list[Asset]:
    return [a for a in ledger.live() if a.type == "power_plant" and a.country == iso]


def _window_events(events: list[StatusEvent], as_of: str, days: int) -> list[StatusEvent]:
    start = (date.fromisoformat(as_of) - timedelta(days=days)).isoformat()
    return [e for e in events if start < e.occurred_on <= as_of]


def _stances(events: list[StatusEvent], as_of: str, days: int) -> tuple[set[str], str]:
    """(stances said about one plant in the window, its exclusive bucket): restored when it is the latest word, else the firmest damage."""
    inside = _window_events(events, as_of, days)
    said = {s for e in inside if (s := _STATUS_STANCE.get(e.status))}
    last = latest(inside)
    if last is not None and last.status == "restored":
        said.add("restored")
        return said, "restored"
    for s in ("confirmed", "reported", "claimed"):
        if s in said:
            return said, s
    return said, ""


def _tally(rows: list[dict], key: str, installed: float) -> dict:
    mw = sum(r["mw"] or 0.0 for r in rows if key in r["stances"])
    n = [r for r in rows if key in r["stances"]]
    return {"plants": len(n), "mw": round(mw, 1), "share": round(mw / installed, 4) if installed else None,
            "no_capacity": sum(1 for r in n if not r["mw"]),
            "by_fuel": {f: round(sum(r["mw"] or 0.0 for r in n if r["fuel_class"] == f), 1) for f in FUELS}}


def _window(ledger: Ledger, ps: list[Asset], as_of: str, days: int, installed: float, *, listing: bool) -> dict:
    rows = []
    for a in ps:
        said, bucket = _stances(ledger.history(a.id), as_of, days)
        if not said:
            continue
        last = ledger.status(a.id)
        inside = _window_events(ledger.history(a.id), as_of, days)
        rows.append({"id": a.id, "name": a.name, "fuel": str(a.attrs.get("fuel", "")), "fuel_class": fuel_class(str(a.attrs.get("fuel", ""))),
                     "mw": _mw(a), "stances": sorted(said), "bucket": bucket, "latest_status": last.status if last else "",
                     "latest_on": last.occurred_on if last else "", "claimants": sorted({e.claimant for e in inside})[:4]})
    rows.sort(key=lambda r: (-(r["mw"] or 0.0), r["name"]))
    out: dict[str, Any] = {"days": days, **{s: _tally(rows, s, installed) for s in STANCES}}
    bucket_rows = [r for r in rows if r["bucket"]]
    out["buckets"] = {b: {f: round(sum(r["mw"] or 0.0 for r in bucket_rows if r["bucket"] == b and r["fuel_class"] == f), 1) for f in FUELS}
                      for b in ("confirmed", "reported", "claimed", "restored")}
    out["plants_affected"] = len(rows)
    if listing:
        out["affected"] = rows[:MAX_AFFECTED]
    return out


def rollup(ledger: Ledger, iso: str, as_of: str | None = None) -> dict:
    """The country's rollup as a plain document (JSON-ready). Empty ``windows`` events means nothing was said in them."""
    iso = iso.upper()
    as_of = as_of or datetime.now(UTC).date().isoformat()
    ps = plants(ledger, iso)
    sized = [(a, _mw(a)) for a in ps]
    installed = sum(mw for _, mw in sized if mw)
    by_fuel = {f: round(sum(mw for a, mw in sized if mw and fuel_class(str(a.attrs.get("fuel", ""))) == f), 1) for f in FUELS}
    windows = {str(d): _window(ledger, ps, as_of, d, installed, listing=True) for d in WINDOWS}
    series = []
    if windows[str(max(WINDOWS))]["plants_affected"]:
        for k in range(SERIES_DAYS - 1, -1, -1):
            day = (date.fromisoformat(as_of) - timedelta(days=k)).isoformat()
            w = _window(ledger, ps, day, min(WINDOWS), installed, listing=False)
            series.append({"day": day, "claimed_mw": w["claimed"]["mw"], "confirmed_mw": w["confirmed"]["mw"],
                           "claimed_share": w["claimed"]["share"], "confirmed_share": w["confirmed"]["share"]})
    n_nocap = max(w[s]["no_capacity"] for w in windows.values() for s in STANCES)
    caveats = [*CAVEATS, *([_MISSING_CAPACITY.format(n=n_nocap)] if n_nocap else [])]
    last = max((e.occurred_on for a in ps for e in ledger.history(a.id) if e.occurred_on <= as_of), default="")
    doc = {"iso": iso, "as_of": as_of, "provenance": "ohmega_derived", "method": "Ledger capacity (WRI/OSM) x dated status events; claims and confirmations kept apart.",
           "installed": {"mw": round(installed, 1), "by_fuel": by_fuel, "plants": len(ps), "plants_with_capacity": sum(1 for _, mw in sized if mw)},
           "windows": windows, "series": series, "last_event_on": last, "caveats": caveats}
    doc["line"] = line(doc)
    return doc


# -- words -----------------------------------------------------------------------------------------
def gw(mw: float) -> str:
    return f"{mw / 1000:.1f} GW" if mw >= 1000 else f"{mw:.0f} MW"


def pct(share: float | None) -> str:
    if share is None:
        return "n/a"
    p = share * 100
    return "<1%" if 0 < p < 1 else f"{p:.0f}%" if p >= 10 else f"{p:.1f}%".replace(".0%", "%")


def _clause(label: str, t: dict, installed: float) -> str:
    if not t["plants"]:
        return ""
    cap = f"{gw(t['mw'])} ({pct(t['share'])})" if t["mw"] else "capacity not on record"
    return f"{label} {cap} at {t['plants']} plant{'s' if t['plants'] != 1 else ''}"


def line(doc: dict) -> str:
    """The rollup in a sentence for a writer or a reader; "" when nothing has been said in the longer window."""
    w = doc["windows"][str(max(WINDOWS))]
    if not w["plants_affected"]:
        return ""
    inst = doc["installed"]["mw"]
    parts = [c for c in (_clause("claimed struck", w["claimed"], inst), _clause("damage reported", w["reported"], inst),
                         _clause("damage confirmed or destroyed", w["confirmed"], inst), _clause("restored", w["restored"], inst)) if c]
    short = doc["windows"][str(min(WINDOWS))]
    recent = ""
    if short["plants_affected"]:
        recent = (f" Last {short['days']} days: claimed {gw(short['claimed']['mw'])} ({pct(short['claimed']['share'])}), "
                  f"confirmed {gw(short['confirmed']['mw'])} ({pct(short['confirmed']['share'])}).")
    return (f"Ohmega analysis, {doc['iso']} grid, {w['days']} days to {doc['as_of']}: " + "; ".join(parts)
            + f". Shares are of {gw(inst)} installed capacity the ledger knows.{recent} Claimed and confirmed overlap and are never added; "
            "capacity is nameplate, not lost output.")


# -- evidence for the desk -------------------------------------------------------------------------
_CACHE: dict[str, Any] = {}


def _signature(base) -> tuple:
    out = []
    for n in ("assets", "events", "merges"):
        try:
            st = (base / f"{n}.jsonl").stat()
            out.append((st.st_size, st.st_mtime_ns))
        except OSError:
            out.append(None)
    return tuple(out)


def cached_ledger() -> Ledger:
    """The on-disk ledger, loaded once per process and reloaded when its files change (a daily asks once per theater)."""
    from .store import root

    base = root()
    sig = (str(base), _signature(base))
    if _CACHE.get("sig") != sig:
        _CACHE.clear()
        _CACHE.update(sig=sig, ledger=Ledger(base), docs={})
    return _CACHE["ledger"]


def evidence_line(iso: str, as_of: str) -> str:
    """The cached rollup line for ``iso`` ("" when nothing was said or there is no ledger). Never raises."""
    try:
        ledger = cached_ledger()
        docs = _CACHE["docs"]
        if (iso, as_of) not in docs:
            docs[(iso, as_of)] = rollup(ledger, iso, as_of)["line"]
        return docs[(iso, as_of)]
    except Exception:  # noqa: BLE001 - an aid to the writer, never its gate
        return ""


def countries_with_events(ledger: Ledger, as_of: str, days: int = max(WINDOWS)) -> list[str]:
    """ISO codes of countries with a power-plant event inside the window."""
    out: set[str] = set()
    for a in ledger.live():
        if a.type == "power_plant" and a.country and _window_events(ledger.history(a.id), as_of, days):
            out.add(a.country)
    return sorted(out)


# -- publish (migration 010: geo_grid, one row per country) ---------------------------------------
_ROW = """
insert into geo_grid (iso, as_of, doc) values (%s, %s, %s::jsonb)
on conflict (iso) do update set as_of = excluded.as_of, doc = excluded.doc, updated_at = now()
"""


def publish_rollups(ledger: Ledger | None = None, *, as_of: str | None = None, isos: list[str] | None = None,
                    connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Upsert the rollup of each country with plant events in the last 30 days (or ``isos``). Never raises; a no-op without a database."""
    import json

    try:
        ledger = ledger or Ledger()
        as_of = as_of or datetime.now(UTC).date().isoformat()
        codes = [i.upper() for i in isos] if isos else countries_with_events(ledger, as_of)
        if not codes:
            return {"db": True, "grid": 0, "note": "no country has plant events in the window"}
        docs = [rollup(ledger, c, as_of) for c in codes]
    except Exception as exc:  # noqa: BLE001
        return {"db": False, "grid": 0, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}

    files = site_data.publish_built(lambda: {f"geo/grid/{d['iso']}.json": d for d in docs})

    def work(conn: Any) -> dict:
        with conn.cursor() as cur:
            cur.executemany(_ROW, [(d["iso"], d["as_of"], json.dumps(d, ensure_ascii=False).replace("\\u0000", "")) for d in docs])
        return {"grid": len(docs)}

    return site_data.also_postgres(files, work, connect)
