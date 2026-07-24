"""Honest theater maps from Natural Earth 110m + real lat/lon points.

Looks like a map snapshot of a region: ocean, labeled countries, annotated points —
not bare silhouettes on a blank plot.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path as MplPath
from shapely.geometry import MultiPolygon, Polygon, box, shape
from shapely.geometry.base import BaseGeometry

from .theme import DARK, Theme, apply_theme

_WORKSPACE = Path(__file__).resolve().parents[1]
_DEFAULT_NE = _WORKSPACE / "data" / "natural_earth" / "ne_110m_admin_0_countries.geojson"

_ISO_KEYS = ("ISO_A3", "ADM0_A3", "ISO_A3_EH")
_NAME_KEYS = ("NAME", "NAME_EN", "ADMIN", "NAME_LONG")

# Short display names for common countries (avoid NATURAL EARTH long forms).
_SHORT_NAME = {
    "RUS": "Russia",
    "UKR": "Ukraine",
    "BLR": "Belarus",
    "POL": "Poland",
    "ROU": "Romania",
    "MDA": "Moldova",
    "TUR": "Turkey",
    "GEO": "Georgia",
    "SAU": "Saudi Arabia",
    "YEM": "Yemen",
    "OMN": "Oman",
    "ARE": "UAE",
    "QAT": "Qatar",
    "BHR": "Bahrain",
    "KWT": "Kuwait",
    "IRQ": "Iraq",
    "IRN": "Iran",
    "JOR": "Jordan",
    "EGY": "Egypt",
    "SDN": "Sudan",
    "ERI": "Eritrea",
    "DJI": "Djibouti",
    "SOM": "Somalia",
    "ETH": "Ethiopia",
    "ISR": "Israel",
    "PSE": "Palestine",
    "LBN": "Lebanon",
    "SYR": "Syria",
}


def basemap_path() -> Path:
    return _DEFAULT_NE


def basemap_available() -> bool:
    return _DEFAULT_NE.is_file() and _DEFAULT_NE.stat().st_size > 1000


def _feature_props(feat: dict) -> dict:
    return feat.get("properties") or {}


def _iso(props: dict) -> str:
    for field in _ISO_KEYS:
        val = str(props.get(field) or "").upper()
        if len(val) == 3 and val.isalpha() and val != "-99":
            return val
    return ""


def _match_country(props: dict, key: str) -> bool:
    k = key.strip().upper()
    if len(k) == 3 and k.isalpha():
        return _iso(props) == k
    for field in _NAME_KEYS:
        val = str(props.get(field) or "")
        if val.casefold() == key.casefold() or key.casefold() in val.casefold():
            return True
    return False


def _display_name(label: str, props: dict) -> str:
    iso = _iso(props)
    if iso in _SHORT_NAME:
        return _SHORT_NAME[iso]
    # Prefer short NAME over long ADMIN
    for field in ("NAME", "NAME_EN", "ADMIN"):
        val = str(props.get(field) or "").strip()
        if val:
            return val
    return label


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
            zorder=1,
        ))


def _theater_bounds(
    feats: list[tuple[str, BaseGeometry, dict]],
    rows: list[dict],
    *,
    min_span_deg: float = 8.0,
    max_span_deg: float = 28.0,
    pad_frac: float = 0.4,
) -> tuple[float, float, float, float]:
    """Viewport from point cluster (not full continental country outline)."""
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
        if span < min_span_deg:
            lo, hi = mid - min_span_deg / 2.0, mid + min_span_deg / 2.0
            span = min_span_deg
        lo -= span * pad_frac + 0.4
        hi += span * pad_frac + 0.4
        span = hi - lo
        if span > max_span_deg:
            mid = (lo + hi) / 2.0
            lo, hi = mid - max_span_deg / 2.0, mid + max_span_deg / 2.0
        return lo, hi

    minx, maxx = _expand(minx, maxx)
    miny, maxy = _expand(miny, maxy)
    return minx, miny, maxx, maxy


def _label_point(geom: BaseGeometry, view: BaseGeometry) -> tuple[float, float] | None:
    """Representative lon/lat for a country label inside the viewport."""
    try:
        clipped = geom.intersection(view)
        if clipped.is_empty:
            return None
        # Prefer largest polygon piece in view
        if isinstance(clipped, MultiPolygon):
            clipped = max(clipped.geoms, key=lambda g: g.area)
        c = clipped.representative_point()
        return float(c.x), float(c.y)
    except Exception:  # noqa: BLE001 — label is optional
        return None


def country_points_map(
    *,
    countries: Sequence[str],
    points: Iterable[dict],
    title: str,
    out: Path | str,
    theme: Theme = DARK,
    as_of: str | None = None,
    source_note: str = "basemap: Natural Earth 110m",
    pad: float = 0.6,
    inset: dict | None = None,
    min_span_deg: float = 8.0,
    max_span_deg: float = 28.0,
    region_labels: Sequence[dict] | None = None,
) -> Path:
    """Theater map: ocean + labeled countries + annotated points.

    ``points``: ``{"name", "lon", "lat"}``.
    ``countries``: focus countries (drawn brighter + always labeled).
    Neighbors that fall in the viewport are drawn and labeled too so the reader
    can place the theater (Ukraine next to Russia, Yemen next to Saudi, etc.).
    Optional ``region_labels``: ``{"name", "lon", "lat"}`` for seas/chokepoints/regions.
    """
    if not basemap_available():
        raise FileNotFoundError(
            f"basemap not installed at {_DEFAULT_NE}. Run scripts/download_basemap.py"
        )
    apply_theme(theme)
    rows = list(points)
    focus_keys = [str(c).strip() for c in countries if str(c).strip()]
    focus_feats = load_countries(focus_keys) if focus_keys else []

    minx, miny, maxx, maxy = _theater_bounds(
        focus_feats or load_countries(None)[:1],
        rows,
        min_span_deg=min_span_deg,
        max_span_deg=max_span_deg,
    )
    view = box(minx, miny, maxx, maxy)

    # All countries that intersect the viewport (context neighbors).
    all_feats = load_countries(None)
    visible: list[tuple[str, BaseGeometry, dict, bool]] = []
    focus_iso = set()
    for lab, geom, props in focus_feats:
        focus_iso.add(_iso(props))
    for lab, geom, props in all_feats:
        try:
            if not geom.intersects(view):
                continue
        except Exception:  # noqa: BLE001
            continue
        iso = _iso(props)
        is_focus = iso in focus_iso or any(_match_country(props, k) for k in focus_keys)
        visible.append((lab, geom, props, is_focus))

    dx, dy = max(maxx - minx, 0.1), max(maxy - miny, 0.1)
    aspect = dx / dy
    height = 5.6
    width = max(5.8, min(9.0, height * aspect))
    fig, ax = plt.subplots(figsize=(width, height))

    # Ocean / background — distinct from land so "what's that dark shape?" is readable.
    ocean = "#0a1628" if theme is DARK or getattr(theme, "name", "") != "paper" else "#c5d4e0"
    land_focus = "#2a3d36" if theme is DARK or True else "#d8e0d4"
    land_other = "#1a2830" if theme is DARK or True else "#e8ebe6"
    edge = theme.grid_strong
    # Use theme panel as fallback only for paper; prefer ocean fill.
    ax.set_facecolor(ocean)

    for _lab, geom, _props, is_focus in visible:
        _add_polygon(
            ax, geom,
            facecolor=land_focus if is_focus else land_other,
            edgecolor=edge,
            lw=0.75 if is_focus else 0.55,
        )

    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(False)
    # Map snapshot, not a scientific plot — drop lon/lat axes clutter.
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(theme.grid)
        spine.set_linewidth(0.6)
    ax.set_title(title, color=theme.emphasis, loc="left", pad=10)

    # Country labels (focus first, then larger neighbors in view).
    labeled = 0
    max_labels = 10
    # Sort: focus countries first, then by visible area
    def _sort_key(item: tuple[str, BaseGeometry, dict, bool]) -> tuple:
        lab, geom, props, is_focus = item
        try:
            area = geom.intersection(view).area
        except Exception:  # noqa: BLE001
            area = 0.0
        return (0 if is_focus else 1, -area)

    for lab, geom, props, is_focus in sorted(visible, key=_sort_key):
        if labeled >= max_labels:
            break
        # Skip tiny slivers in view
        try:
            if geom.intersection(view).area < (dx * dy) * 0.008 and not is_focus:
                continue
        except Exception:  # noqa: BLE001
            continue
        pt = _label_point(geom, view)
        if not pt:
            continue
        name = _display_name(lab, props)
        ax.text(
            pt[0], pt[1], name,
            color=theme.muted if not is_focus else theme.text,
            fontsize=9 if is_focus else 8,
            ha="center", va="center",
            fontstyle="italic" if not is_focus else "normal",
            zorder=3,
            path_effects=[],
        )
        labeled += 1

    # Optional region / water labels (Black Sea, Bab el-Mandeb, etc.)
    for reg in region_labels or []:
        try:
            lon, lat = float(reg["lon"]), float(reg["lat"])
            name = str(reg.get("name") or "")
        except (KeyError, TypeError, ValueError):
            continue
        if not name or not (minx <= lon <= maxx and miny <= lat <= maxy):
            continue
        ax.text(
            lon, lat, name,
            color=theme.series2,
            fontsize=8,
            ha="center", va="center",
            fontstyle="italic",
            zorder=3,
            alpha=0.9,
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
        ax.text(x0, y1, lab, color=theme.series2, fontsize=8, va="bottom", ha="left", zorder=4)

    # Story points on top
    offsets = [(8, 7), (8, -11), (-10, 9), (-10, -12), (12, 1), (-14, 3)]
    for i, p in enumerate(rows):
        lon, lat = float(p["lon"]), float(p["lat"])
        ax.plot(lon, lat, "o", color=theme.series1, markersize=8, zorder=5,
                markeredgecolor=theme.emphasis, markeredgewidth=0.6)
        name = str(p.get("name") or "")
        if name:
            ox, oy = offsets[i % len(offsets)]
            ax.annotate(
                name, (lon, lat), textcoords="offset points", xytext=(ox, oy),
                color=theme.emphasis, fontsize=9, fontweight="medium", zorder=6,
            )

    footer = source_note
    if as_of:
        footer = f"as of {as_of} · {footer}"
    fig.text(0.01, 0.01, footer, color=theme.muted, fontsize=8)
    fig.tight_layout()
    out_p = Path(out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_p, bbox_inches="tight", pad_inches=0.15, facecolor=fig.get_facecolor())
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
    ax.set_facecolor("#0a1628")
    for label, geom, props in all_feats:
        iso = _iso(props)
        name = label.upper()
        on = iso in hi or any(h in name or name in h for h in hi if len(h) > 2)
        face = theme.series1 if on else "#1a2830"
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
