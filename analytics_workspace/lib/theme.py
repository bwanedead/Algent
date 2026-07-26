"""Ohmega Monster visual tokens for charts and maps."""

from __future__ import annotations

from dataclasses import dataclass

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
