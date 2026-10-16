"""
The tracker comparison contract: our own measured series drawn together (daily visual kind ``tracker_compare``, native).

NO number in this visual comes from a model. The model only chooses WHICH instrument series illuminate the theater
(ids from ``instruments.catalog``), the window, a short label per series and a few event markers taken from the
day's developments. ``ground`` then reads the series from the instruments store itself: every point on the chart is a
stored observation, named by its catalog source. ``components/NativeTrackerCompare.tsx`` draws it as one interactive
chart (indexed to 100 at the start, or each series raw on a shared time axis).

What is allowed: a series that exists in the catalog, may be shown publicly (``public_display``: internal-only
sources such as the unofficial market feeds are refused, the same licence rule as the numbers panel) and holds enough
points inside the window; 2 to 6 of them. A marker's date must be stated by a fact it cites and fall inside the
window. Title and caption carry no number the day's facts lack. What fails is dropped and named in the report; fewer
than two usable series refuses the visual.
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field

from algent_backend.instruments import store as istore
from algent_backend.instruments.catalog import CATALOG, get_series
from algent_backend.instruments.contracts import period_date

from .timeline_spec import Source, valid_date
from .visuals_grounding import mentions_date, ungrounded, word_count

WINDOWS = (30, 60, 90, 180, 365)
MIN_SERIES, MAX_SERIES, MIN_POINTS, MAX_MARKERS = 2, 6, 4, 6
LABEL_WORDS, MARKER_WORDS = 4, 8


class Line(BaseModel):
    id: str
    label: str = ""
    unit: str = ""
    source: str = ""
    source_url: str = ""
    dates: list[str] = Field(default_factory=list)       # YYYY-MM-DD (a monthly period is its first day), oldest first
    values: list[float] = Field(default_factory=list)    # the stored observations, as the source published them


class Marker(BaseModel):
    date: str
    label: str                                           # at most MARKER_WORDS words
    fact_ids: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)  # filled from the cited facts by the producer


class TrackerCompare(BaseModel):
    title: str
    caption: str
    window_days: int = 90
    start: str = ""                                      # the window, set by ``ground``
    end: str = ""
    series: list[Line]
    markers: list[Marker] = Field(default_factory=list)
    alt: str = ""


# -- the WIRE schema the model fills: ids and words only, never a data point ----------------------------

class PickWire(BaseModel):
    id: str                                              # a series id from the list given
    label: str = ""                                      # a plain name for the line, at most LABEL_WORDS words


class MarkerWire(BaseModel):
    date: str
    label: str
    fact_ids: list[str] = Field(default_factory=list)


class TrackerCompareWire(BaseModel):
    title: str
    caption: str
    window_days: int = 90
    series: list[PickWire]
    markers: list[MarkerWire] = Field(default_factory=list)


def from_wire(wire: TrackerCompareWire) -> tuple[TrackerCompare, list[str]]:
    lines = [Line(id=p.id.strip(), label=p.label.strip()) for p in wire.series]
    marks = [Marker(date=m.date, label=m.label, fact_ids=m.fact_ids[:6]) for m in wire.markers]
    return TrackerCompare(title=wire.title, caption=wire.caption, window_days=wire.window_days, series=lines, markers=marks), []


def _window(days: int) -> int:
    return next((w for w in WINDOWS if days <= w), WINDOWS[-1])


def _points(series_id: str, start: date, end: date) -> list[tuple[str, float]]:
    out = []
    for o in istore.history(series_id):
        d = period_date(o.period)
        if start <= d <= end:
            out.append((d.isoformat(), float(f"{o.value:.6g}")))
    return out


def available(as_of: str, window_days: int = 365) -> list[dict]:
    """The series the model may choose from: in the catalog, public, with enough stored points up to ``as_of``.
    One row each: id, name, unit, points, first and last date."""
    if not valid_date(as_of):
        return []
    end = date.fromisoformat(as_of)
    rows = []
    for s in CATALOG:
        if not s.public_display:
            continue
        pts = _points(s.id, end - timedelta(days=window_days), end)
        if len(pts) >= MIN_POINTS:
            rows.append({"id": s.id, "name": s.name, "unit": s.unit, "n": len(pts), "first": pts[0][0], "last": pts[-1][0]})
    return rows


def available_block(as_of: str) -> str:
    """The list of choosable series as the model sees it."""
    rows = available(as_of)
    if not rows:
        return "SERIES YOU MAY COMPARE: none are available today."
    lines = "\n".join(f"- {r['id']}: {r['name']} [{r['unit']}], {r['n']} points, {r['first']} to {r['last']}" for r in rows)
    return ("SERIES YOU MAY COMPARE (choose 2 to 6 by exact id; the numbers come from our own store, you write none; "
            "pick series that share a cause or an effect, and a window of 30, 60, 90, 180 or 365 days that shows it):\n" + lines)


def _line_problem(ln: Line, as_of_d: date, start: date) -> str:
    try:
        s = get_series(ln.id)
    except KeyError:
        return "not a series of the catalog"
    if not s.public_display:
        return "an internal-only source (not cleared for public display)"
    pts = _points(s.id, start, as_of_d)
    if len(pts) < MIN_POINTS:
        return f"fewer than {MIN_POINTS} stored points in the window"
    label = ln.label if ln.label and word_count(ln.label) <= LABEL_WORDS and not any(c.isdigit() for c in ln.label) else s.name
    ln.label, ln.unit, ln.source, ln.source_url = label, s.unit, s.source, s.source_url
    ln.dates, ln.values = [p[0] for p in pts], [p[1] for p in pts]
    return ""


def common_start(spec: TrackerCompare) -> str:
    """The first date every line has a reading on or around: where the index is 100."""
    return max((ln.dates[0] for ln in spec.series if ln.dates), default="")


def ground(spec: TrackerCompare, facts: dict[str, str], as_of: str) -> list[str]:
    """Fill the chosen series from the store and drop what cannot stand (in place); return a line per drop, then any
    spec-level problem prefixed ``REFUSED``. ``facts`` maps fact id to text (the visual's cited facts)."""
    notes: list[str] = []
    if not valid_date(as_of):
        return ["REFUSED: no valid as-of date"]
    end = date.fromisoformat(as_of)
    spec.window_days = _window(spec.window_days if spec.window_days > 0 else 90)
    start = end - timedelta(days=spec.window_days)
    spec.start, spec.end = start.isoformat(), end.isoformat()
    kept: list[Line] = []
    for ln in spec.series:
        if ln.id in {k.id for k in kept}:
            notes.append(f"series {ln.id!r} dropped: chosen twice")
        elif why := _line_problem(ln, end, start):
            notes.append(f"series {ln.id!r} dropped: {why}")
        else:
            kept.append(ln)
    if len(kept) > MAX_SERIES:
        notes.append(f"{len(kept) - MAX_SERIES} series over the limit of {MAX_SERIES} dropped")
    spec.series = kept[:MAX_SERIES]
    cs = common_start(spec)
    overlap = [ln for ln in spec.series if sum(d >= cs for d in ln.dates) >= 2] if cs else []
    if len(spec.series) >= MIN_SERIES and len(overlap) < len(spec.series):
        notes.append("REFUSED: the chosen series do not overlap in time")
    if len(spec.series) < MIN_SERIES:
        notes.append(f"REFUSED: {len(spec.series)} usable series, need {MIN_SERIES} to {MAX_SERIES}")
    marks: list[Marker] = []
    for m in spec.markers:
        m.fact_ids = m.fact_ids[:6]
        cited = " ".join(facts[x] for x in dict.fromkeys(m.fact_ids) if x in facts)
        if not cited or not all(x in facts for x in m.fact_ids):
            why = "cites no fact of the visual (or one that is not)"
        elif not valid_date(m.date) or not mentions_date(cited, m.date):
            why = f"no cited fact states {m.date!r}"
        elif not spec.start <= m.date <= spec.end:
            why = "outside the window"
        elif not m.label.strip() or word_count(m.label) > MARKER_WORDS or ungrounded(m.label, cited):
            why = f"label empty, over {MARKER_WORDS} words, or carries numbers not in its facts"
        else:
            marks.append(m)
            continue
        notes.append(f"marker {m.date!r} dropped: {why}")
    spec.markers = sorted(marks, key=lambda m: m.date)[:MAX_MARKERS]
    if bad := ungrounded(f"{spec.title} {spec.caption}", " ".join(facts.values())):
        notes.append(f"REFUSED: title or caption carries numbers not in the facts ({', '.join(bad[:3])})")
    return notes


def alt_text(spec: TrackerCompare) -> str:
    """Each line's first and last reading as plain text: the alternative to the chart."""
    parts = [f"{ln.label}: {ln.values[0]:g} on {ln.dates[0]} to {ln.values[-1]:g} {ln.unit} on {ln.dates[-1]}." for ln in spec.series if ln.values]
    marks = [f"{m.date}: {m.label}." for m in spec.markers]
    return f"{spec.title}. {spec.caption} " + " ".join(parts + marks)
