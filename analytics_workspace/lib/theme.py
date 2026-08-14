"""Ohmega Monster visual tokens for charts and maps."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib as mpl
from matplotlib import font_manager


@dataclass(frozen=True)
class Theme:
    name: str
    background: str
    panel: str
    text: str
    emphasis: str
    muted: str
    grid: str
    grid_strong: str
    series1: str
    series2: str
    series3: str


DARK = Theme(
    name="dark",
    background="#0c0f0e",
    panel="#111513",
    text="#d3d0c8",
    emphasis="#f0ede4",
    muted="#858981",
    grid="#2b302d",
    grid_strong="#454b46",
    series1="#f0a33a",
    series2="#5eb8c9",
    series3="#c98bb8",
)

PAPER = Theme(
    name="paper",
    background="#f0eee6",
    panel="#e8e5dc",
    text="#242722",
    emphasis="#0e110f",
    muted="#666b64",
    grid="#cbc9c0",
    grid_strong="#9b9d96",
    series1="#99500c",
    series2="#0f6e7a",
    series3="#7a3d68",
)

# Prefer site monospace; fall back cleanly.
_FONT_CANDIDATES = (
    "IBM Plex Mono",
    "Cascadia Mono",
    "Cascadia Code",
    "Menlo",
    "Consolas",
    "DejaVu Sans Mono",
    "monospace",
)


def resolve_font() -> str:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in _FONT_CANDIDATES:
        if name in available or name == "monospace":
            return name
    return "DejaVu Sans Mono"


def apply_theme(theme: Theme = DARK) -> Theme:
    """Apply rcParams for a cold, terminal/newswire figure. Returns the theme used."""
    font = resolve_font()
    mpl.rcParams.update({
        "figure.facecolor": theme.background,
        "axes.facecolor": theme.panel,
        "savefig.facecolor": theme.background,
        "text.color": theme.text,
        "axes.labelcolor": theme.text,
        "axes.edgecolor": theme.grid_strong,
        "xtick.color": theme.muted,
        "ytick.color": theme.muted,
        "grid.color": theme.grid,
        "grid.linewidth": 0.6,
        "axes.grid": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.family": font,
        "font.size": 10,
        "axes.titlesize": 12,
        "axes.labelsize": 10,
        "legend.fontsize": 9,
        "figure.dpi": 120,
        "savefig.dpi": 140,
        "svg.fonttype": "none",  # real text in SVG, not paths
    })
    return theme


def series_colors(theme: Theme = DARK) -> list[str]:
    return [theme.series1, theme.series2, theme.series3]


# Wordmark + silhouette live in this workspace so the grok worker never reaches into sites/.
_MARK = Path(__file__).resolve().parent / "assets" / "mark.png"
_WORDMARK = "OHMEGA MONSTER"
_SITE = "ohmega.monster"


def mark_path() -> Path | None:
    return _MARK if _MARK.is_file() else None


def watermark(fig, theme: Theme | None = None) -> None:
    """Stacked mark + wordmark as one brand unit. Never raises."""
    try:
        used = theme or DARK
        if not fig.axes:
            return
        pack = _brand_stack(used)
        from matplotlib.offsetbox import AnnotationBbox

        artist = AnnotationBbox(
            pack, (0.88, 0.14),
            xycoords="figure fraction",
            frameon=False, pad=0, zorder=8,
        )
        fig.axes[0].add_artist(artist)
    except Exception:  # noqa: BLE001 — branding must not kill a chart
        return


def _brand_stack(theme: Theme):
    """Mark beside the name — one lockup, not a floating icon and a stray caption."""
    from matplotlib.offsetbox import HPacker, OffsetImage, TextArea, VPacker

    font = resolve_font()
    name = TextArea(
        _WORDMARK,
        textprops={
            "fontsize": 13,
            "color": theme.emphasis,
            "alpha": 0.7,
            "fontfamily": font,
            "fontweight": "bold",
            "va": "center",
        },
    )
    site = TextArea(
        _SITE,
        textprops={
            "fontsize": 9,
            "color": theme.muted,
            "alpha": 0.5,
            "fontfamily": font,
            "va": "center",
        },
    )
    words = VPacker(children=[name, site], align="left", pad=0, sep=1)
    path = mark_path()
    if path is None:
        return words
    rgba = _silhouette(path, theme)
    if rgba is None:
        return words
    h, w = rgba.shape[:2]
    zoom = min(0.22, 88.0 / max(h, w, 1))
    mark = OffsetImage(rgba, zoom=zoom)
    return HPacker(children=[mark, words], align="center", pad=2, sep=6)


def _silhouette(path: Path, theme: Theme) -> object | None:
    """Dark-on-black mark → tinted RGBA so it reads on both dark and paper charts."""
    import numpy as np
    from PIL import Image

    gray = np.asarray(Image.open(path).convert("L"))
    mask = gray > 18
    if not mask.any():
        return None
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    r0, r1 = int(np.argmax(rows)), int(len(rows) - np.argmax(rows[::-1]))
    c0, c1 = int(np.argmax(cols)), int(len(cols) - np.argmax(cols[::-1]))
    crop = mask[r0:r1, c0:c1]
    r, g, b = _rgb(theme.emphasis)
    rgba = np.zeros((crop.shape[0], crop.shape[1], 4), dtype=np.uint8)
    rgba[crop, 0] = r
    rgba[crop, 1] = g
    rgba[crop, 2] = b
    rgba[crop, 3] = 58  # ~23% — name sits on it; still a watermark, not a stamp
    return rgba


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
