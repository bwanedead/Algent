"""Honest country-scale maps from Natural Earth 110m + real lat/lon points.

Requires basemap GeoJSON from ``scripts/download_basemap.py`` (tiny cultural layer —
not planet tiles).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path as MplPath
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry

from .theme import DARK, Theme, apply_theme

_WORKSPACE = Path(__file__).resolve().parents[1]
_DEFAULT_NE = _WORKSPACE / "data" / "natural_earth" / "ne_110m_admin_0_countries.geojson"

# ISO_A3 / NAME keys Natural Earth uses
_ISO_KEYS = ("ISO_A3", "ADM0_A3", "ISO_A3_EH")
_NAME_KEYS = ("NAME", "NAME_EN", "ADMIN", "NAME_LONG")


def basemap_path() -> Path:
    return _DEFAULT_NE


def basemap_available() -> bool:
    return _DEFAULT_NE.is_file() and _DEFAULT_NE.stat().st_size > 1000


def _feature_props(feat: dict) -> dict:
    return feat.get("properties") or {}


def _match_country(props: dict, key: str) -> bool:
    k = key.strip().upper()
    if len(k) == 3 and k.isalpha():
        for field in _ISO_KEYS:
            val = str(props.get(field) or "").upper()
            if val == k:
                return True
        return False
    # name match (case-insensitive contains / equality)
    for field in _NAME_KEYS:
        val = str(props.get(field) or "")
        if val.casefold() == key.casefold() or key.casefold() in val.casefold():
            return True
    return False


def load_countries(
    keys: Sequence[str] | None = None,
    *,
    path: Path | None = None,
) -> list[tuple[str, BaseGeometry, dict]]:
    """Load country polygons. ``keys`` are ISO-A3 codes or name fragments; None = all."""
    p = path or _DEFAULT_NE
    if not p.is_file():
        raise FileNotFoundError(
            f"Natural Earth basemap missing at {p}. Run: "
            f"python scripts/download_basemap.py"
        )
    data = json.loads(p.read_text(encoding="utf-8"))
    out: list[tuple[str, BaseGeometry, dict]] = []
    for feat in data.get("features") or []:
        props = _feature_props(feat)
        if keys:
            if not any(_match_country(props, k) for k in keys):
                continue
        label = next((str(props[f]) for f in _NAME_KEYS if props.get(f)), "country")
        geom = shape(feat["geometry"])
        if geom.is_empty:
            continue
        out.append((label, geom, props))
    if keys and not out:
        raise ValueError(f"no countries matched keys={list(keys)!r} in {p.name}")
    return out


def _rings(geom: BaseGeometry) -> list[list[tuple[float, float]]]:
    polys: list[Polygon] = []
    if isinstance(geom, Polygon):
        polys = [geom]
    elif isinstance(geom, MultiPolygon):
        polys = list(geom.geoms)
    else:
        return []
    rings: list[list[tuple[float, float]]] = []
    for poly in polys:
        # exterior only at 110m — interiors (lakes) optional for clarity
        rings.append(list(poly.exterior.coords))
    return rings


def _add_polygon(ax, geom: BaseGeometry, *, facecolor: str, edgecolor: str, lw: float = 0.6) -> None:
    for ring in _rings(geom):
        if len(ring) < 3:
            continue
        codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(ring) - 2) + [MplPath.CLOSEPOLY]
        path = MplPath(ring, codes)
        ax.add_patch(PathPatch(
            path, facecolor=facecolor, edgecolor=edgecolor, linewidth=lw, joinstyle="round",
        ))


def _theater_bounds(
    feats: list[tuple[str, BaseGeometry, dict]],
    rows: list[dict],
    *,
    min_span_deg: float = 8.0,
    max_span_deg: float = 28.0,
    pad_frac: float = 0.4,
) -> tuple[float, float, float, float]:
    """Viewport that shows the story's places, not an entire continental country outline.

    Full-country bounds for Russia/Canada/USA make a 3-city cluster unreadable (tiny dots on a
    vast empty frame). Prefer the point cluster, expanded to a readable min span, capped so we
    never zoom out to planet-scale emptiness. Country polygons still draw underneath for context.
    """
    if rows:
        lons = [float(p["lon"]) for p in rows]
        lats = [float(p["lat"]) for p in rows]
        minx, maxx = min(lons), max(lons)
        miny, maxy = min(lats), max(lats)
    else:
        minx = min(g.bounds[0] for _, g, _ in feats)
        miny = min(g.bounds[1] for _, g, _ in feats)
        maxx = max(g.bounds[2] for _, g, _ in feats)
        maxy = max(g.bounds[3] for _, g, _ in feats)

    def _expand(lo: float, hi: float) -> tuple[float, float]:
        span = max(hi - lo, 0.25)
        mid = (lo + hi) / 2.0
        # Floor: enough context to place the cluster.
        if span < min_span_deg:
            lo, hi = mid - min_span_deg / 2.0, mid + min_span_deg / 2.0
            span = min_span_deg
        # Pad around the (possibly expanded) span.
        lo -= span * pad_frac + 0.4
        hi += span * pad_frac + 0.4
        span = hi - lo
        # Ceiling: Russia-scale emptiness is worse than a tight theater crop.
        if span > max_span_deg:
            mid = (lo + hi) / 2.0
            lo, hi = mid - max_span_deg / 2.0, mid + max_span_deg / 2.0
        return lo, hi

    minx, maxx = _expand(minx, maxx)
    miny, maxy = _expand(miny, maxy)
    return minx, miny, maxx, maxy


def country_points_map(
    *,
    countries: Sequence[str],
    points: Iterable[dict],
    title: str,
    out: Path | str,
    theme: Theme = DARK,
    as_of: str | None = None,
    source_note: str = "basemap: Natural Earth 110m",
    pad: float = 0.6,  # retained for call-site compat; framing uses _theater_bounds
    inset: dict | None = None,
    min_span_deg: float = 8.0,
    max_span_deg: float = 28.0,
) -> Path:
    """Country (or multi-country theater) frame + labeled lat/lon points.

    ``points`` items: ``{"name": str, "lon": float, "lat": float, ...}``.
    Viewport follows the **point cluster** (readable theater), not full-country bounds —
    critical for Russia/Canada/USA where country geometry is continent-sized.
    Optional ``inset``: ``{"lon_min", "lon_max", "lat_min", "lat_max", "label"}`` draws a
    callout box on the main map.
    """
    if not basemap_available():
        raise FileNotFoundError(
            f"basemap not installed at {_DEFAULT_NE}. Run scripts/download_basemap.py"
        )
    apply_theme(theme)
    rows = list(points)
    feats = load_countries(list(countries))

    minx, miny, maxx, maxy = _theater_bounds(
        feats, rows, min_span_deg=min_span_deg, max_span_deg=max_span_deg,
    )
    dx, dy = max(maxx - minx, 0.1), max(maxy - miny, 0.1)
    # Figure size tracks aspect so the SVG isn't a tall black slab of empty ocean.
    aspect = dx / dy
    height = 5.4
    width = max(5.5, min(8.5, height * aspect))
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_facecolor(theme.panel)
    for _label, geom, _props in feats:
        _add_polygon(ax, geom, facecolor="#1a221e", edgecolor=theme.grid_strong, lw=0.7)

    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(False)
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_title(title, color=theme.emphasis, loc="left", pad=10)

    # Stagger label offsets so tight city clusters don't pile on one another.
    offsets = [(7, 6), (7, -10), (-8, 8), (-8, -12), (10, 0), (-12, 2)]
    for i, p in enumerate(rows):
        lon, lat = float(p["lon"]), float(p["lat"])
        ax.plot(lon, lat, "o", color=theme.series1, markersize=8, zorder=5)
        name = str(p.get("name") or "")
        if name:
            ox, oy = offsets[i % len(offsets)]
            ax.annotate(
                name, (lon, lat), textcoords="offset points", xytext=(ox, oy),
                color=theme.text, fontsize=9, zorder=6,
            )

    if inset:
        x0, x1 = float(inset["lon_min"]), float(inset["lon_max"])
        y0, y1 = float(inset["lat_min"]), float(inset["lat_max"])
        rect = Rectangle(
            (x0, y0), x1 - x0, y1 - y0,
            fill=False, edgecolor=theme.series2, linewidth=1.2, linestyle="--", zorder=4,
        )
        ax.add_patch(rect)
        lab = str(inset.get("label") or "detail")
        ax.text(x0, y1, lab, color=theme.series2, fontsize=8, va="bottom", ha="left")

    footer = source_note
    if as_of:
        footer = f"as of {as_of} · {footer}"
    fig.text(0.01, 0.01, footer, color=theme.muted, fontsize=8)
    fig.tight_layout()
    out_p = Path(out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_p, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    return out_p


def world_highlight_map(
    *,
    highlight: Sequence[str],
    title: str,
    out: Path | str,
    theme: Theme = DARK,
    as_of: str | None = None,
) -> Path:
    """Small world map with selected countries filled (context, not choropleth values)."""
    apply_theme(theme)
    all_feats = load_countries(None)
    hi = {k.strip().upper() for k in highlight}
    fig, ax = plt.subplots(figsize=(8.0, 4.4))
    ax.set_facecolor(theme.panel)
    for label, geom, props in all_feats:
        iso = str(props.get("ISO_A3") or props.get("ADM0_A3") or "").upper()
        name = label.upper()
        on = iso in hi or any(h in name or name in h for h in hi if len(h) > 2)
        face = theme.series1 if on else "#1a221e"
        edge = theme.emphasis if on else theme.grid
        _add_polygon(ax, geom, facecolor=face, edgecolor=edge, lw=0.35)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-60, 85)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(False)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, color=theme.emphasis, loc="left", pad=8)
    footer = "basemap: Natural Earth 110m"
    if as_of:
        footer = f"as of {as_of} · {footer}"
    fig.text(0.01, 0.01, footer, color=theme.muted, fontsize=8)
    fig.tight_layout()
    out_p = Path(out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_p, bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    return out_p
