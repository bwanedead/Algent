"""
Anomalies — the record of "this place is outside its normal", its plain sentence, and the table the site reads (migration 011).

An ``Anomaly`` is a CONFIRMED run (``detect.Run``): a place (a 1-degree cell or a named area), a series (``ship.tanker``), a start,
an end or still-ongoing, how far from normal (ratio and a plain sentence), a confidence and the provenance ``ohmega_derived`` -
we computed it from public sensor feeds; no model, no source says it. Appended to ``anomalies/log.jsonl`` when a run is confirmed and
again when it ends (append-only); the current picture (``collapse``) merges what is one event - a cell inside an area that is itself
flagged, neighbouring cells flagged together - and is what is published to ``live_anomalies``, what the daily's evidence block
reads and what the API serves.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from algent_backend.publishing.published_db import _run

from . import flags, hours
from .areas import PHRASE, WORLD, layer_of, place_countries, place_kind, place_label, place_lonlat, place_tags
from .detect import Run

Provenance = Literal["ohmega_derived"]


class Anomaly(BaseModel):
    id: str                                   # series:place:start hour, stable for the life of the run
    series: str                               # ship.tanker
    layer: str                                # ship | air | fire
    klass: str                                # tanker
    place_kind: str                           # cell | gate | region | fire
    place_id: str                             # "c12345" for a cell, "gate:hormuz" for an area
    label: str
    lat: float | None = None
    lon: float | None = None
    countries: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    direction: Literal["above", "below"]
    starts_at: str
    ends_at: str | None = None                # None = still going
    last_seen: str = ""                       # end of the last hour it was still outside normal
    hours: int = 1
    value: float = 0.0                        # latest reading (objects present)
    normal: float = 0.0                       # the median for this hour of the week
    ratio: float | None = None                # value / normal (None when normal is about zero)
    score: float = 0.0                        # strongest robust z
    confidence: float = 0.0                   # 0..1: saturating in score and in how long it has lasted; halved while learning
    learning: bool = False                    # baseline still young (fewer than the full set of weeks)
    n_cells: int = 1                          # cells merged into this one event
    sentence: str = ""
    provenance: Provenance = "ohmega_derived"

    @property
    def active(self) -> bool:
        return self.ends_at is None


# ── words ───────────────────────────────────────────────────────────────────────────────────────
def duration_text(h: int) -> str:
    if h < 48:
        return f"{h} h"
    d, r = divmod(h, 24)
    return f"{d} d" + (f" {r} h" if r and d < 7 else "")


def magnitude_text(direction: str, value: float, normal: float) -> str:
    if normal < 1.0:
        return f"{value:.0f} present, normally none" if direction == "above" else "absent"
    ratio = value / normal
    if direction == "above" and ratio >= 2:
        return f"{ratio:.1f}x normal"
    return f"{abs(ratio - 1) * 100:.0f}% {direction} normal"


def sentence_of(a: Anomaly) -> str:
    more = f" (and {a.n_cells - 1} nearby cell{'s' if a.n_cells > 2 else ''})" if a.n_cells > 1 else ""
    return f"{a.label}: {PHRASE.get(a.series, a.series)} {magnitude_text(a.direction, a.value, a.normal)} for {duration_text(a.hours)}{more}"


def _sat(x: float) -> float:
    return max(0.0, min(1.0, x))


def confidence_of(mean_score: float, hours_: int, series: str, learning: bool) -> float:
    from .detect import persist_needed

    c = _sat(mean_score / (2 * flags.Z_ENTER)) * _sat(hours_ / (2 * persist_needed(series)))
    return round(c * (0.5 if learning else 1.0), 3)


def _country_label(place: int | str) -> str:
    """A cell's label gains the country when the cell's middle is on land (the basemap; never required)."""
    if not isinstance(place, int):
        return ""
    try:
        from .. import places
        from .areas import cell_center

        name = places.country_at(*cell_center(place))
        return f" ({name})" if name else ""
    except Exception:  # noqa: BLE001
        return ""


def from_run(run: Run, end: int | None = None) -> Anomaly:
    lonlat = place_lonlat(run.place)
    span = max(1, run.last_flag - run.start + 1)
    ratio = run.value / run.normal if run.normal >= 1.0 else None
    a = Anomaly(
        id=f"{run.series}:{run.place if isinstance(run.place, str) else f'c{run.place}'}:{hours.stamp(run.start)}",
        series=run.series, layer=layer_of(run.series), klass=run.series.split(".", 1)[1], place_kind=place_kind(run.place),
        place_id=run.place if isinstance(run.place, str) else f"c{run.place}", label=place_label(run.place) + _country_label(run.place),
        lat=lonlat[0] if lonlat else None, lon=lonlat[1] if lonlat else None, countries=place_countries(run.place), tags=place_tags(run.place),
        direction="above" if run.direction > 0 else "below", starts_at=hours.iso_hour(run.start),
        ends_at=hours.iso_hour(end) if end is not None else None, last_seen=hours.iso_hour(run.last_flag + 1), hours=span,
        value=round(run.value, 2), normal=round(run.normal, 2), ratio=round(ratio, 2) if ratio is not None else None,
        score=round(run.peak, 2), confidence=confidence_of(run.mean_score, run.obs, run.series, run.learning), learning=run.learning)
    a.sentence = sentence_of(a)
    return a


# ── the current picture ─────────────────────────────────────────────────────────────────────────
def _overlap(a: Anomaly, b: Anomaly) -> bool:
    return a.starts_at < (b.ends_at or "9999") and b.starts_at < (a.ends_at or "9999")


def _inside(area: Anomaly, a: Anomaly) -> bool:
    from .areas import BY_ID

    box = BY_ID[area.place_id].box if area.place_id in BY_ID else None
    return bool(box and a.lat is not None and a.lon is not None and box[0] <= a.lat <= box[2] and box[1] <= a.lon <= box[3])


def collapse(anoms: list[Anomaly]) -> list[Anomaly]:
    """One event is one row: drop cells that lie inside a flagged named area of the same series and direction, merge neighbouring
    flagged cells into the strongest, order active first then by confidence, cap at ``MAX_PUBLISHED``."""
    anoms = [a for a in anoms if a.place_id != WORLD]
    areas = [a for a in anoms if a.place_kind != "cell"]
    cells = [a for a in anoms if a.place_kind == "cell"]
    cells = [c for c in cells if not any(a.series == c.series and a.direction == c.direction and _overlap(a, c) and _inside(a, c) for a in areas)]
    cells.sort(key=lambda a: (-a.confidence, -a.score))
    kept: list[Anomaly] = []
    for c in cells:
        host = next((k for k in kept if k.series == c.series and k.direction == c.direction and _overlap(k, c)
                     and abs(k.lat - c.lat) <= flags.CLUSTER_DEG and abs(k.lon - c.lon) <= flags.CLUSTER_DEG), None)  # type: ignore[operator]
        if host is None:
            kept.append(c.model_copy())
        else:
            host.n_cells += 1
            host.starts_at = min(host.starts_at, c.starts_at)
    out = [*areas, *kept]
    for a in out:
        a.sentence = sentence_of(a)
    out.sort(key=lambda a: (not a.active, -a.confidence, -a.score))
    return out[:flags.MAX_PUBLISHED]


# ── disk ────────────────────────────────────────────────────────────────────────────────────────
def anomaly_dir():
    return hours.root() / "anomalies"


def log_event(event: str, a: Anomaly, at: str) -> None:
    path = anomaly_dir() / "log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"event": event, "at": at, "anomaly": a.model_dump()}, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_current(anoms: list[Anomaly], as_of: str) -> None:
    from .. import store

    store._write(anomaly_dir() / "current.json", {"as_of": as_of, "anomalies": [a.model_dump() for a in anoms]})


def read_current() -> list[Anomaly]:
    """The current anomalies as the last tick left them (empty when memory has not run)."""
    from .. import store

    doc = store._read(anomaly_dir() / "current.json", {})
    out = []
    for d in doc.get("anomalies", []):
        try:
            out.append(Anomaly.model_validate(d))
        except ValueError:
            continue
    return out


# ── the site's table (migration 011) ───────────────────────────────────────────────────────────
_COLUMNS = ("id", "series", "layer", "klass", "place_kind", "place_id", "label", "lat", "lon", "countries", "direction", "starts_at",
            "ends_at", "last_seen", "active", "hours", "value", "normal", "ratio", "score", "confidence", "learning", "n_cells",
            "sentence", "provenance")
_UPSERT = f"""
insert into live_anomalies ({', '.join(_COLUMNS)})
values ({', '.join(['%s'] * len(_COLUMNS))})
on conflict (id) do update set {', '.join(f'{c} = excluded.{c}' for c in _COLUMNS if c != 'id')}, updated_at = now()
"""
_RETIRE = "update live_anomalies set active = false, updated_at = now() where active and not (id = any(%s))"
_PRUNE = "delete from live_anomalies where not active and coalesce(ends_at, updated_at) < now() - make_interval(days => %s)"


def _row(a: Anomaly) -> tuple:
    d = a.model_dump()
    d["active"] = a.active
    d["last_seen"] = a.last_seen or None
    return tuple(d[c] for c in _COLUMNS)


def publish(anoms: list[Anomaly], *, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    """Upsert the current anomalies, retire rows no longer in the picture, drop rows closed longer than ``RETAIN_DAYS`` ago.
    Never raises; a no-op without ``DATABASE_URL``."""

    def work(conn: Any) -> dict:
        with conn.cursor() as cur:
            for a in anoms:
                cur.execute(_UPSERT, _row(a))
            cur.execute(_RETIRE, ([a.id for a in anoms],))
            cur.execute(_PRUNE, (flags.RETAIN_DAYS,))
        return {"anomalies": len(anoms)}

    return _run(work, connect)
