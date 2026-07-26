"""Common chart helpers — trajectory, bars, comparisons."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import pandas as pd

from .theme import DARK, Theme, apply_theme, series_colors


def _save(fig: plt.Figure, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    return path


def line_chart(
    df: pd.DataFrame,
    *,
    x: str,
    y: str | Sequence[str],
    title: str,
    ylabel: str,
    xlabel: str = "",
    out: Path | str,
    theme: Theme = DARK,
    as_of: str | None = None,
) -> Path:
    """Multi-series line chart. ``y`` may be one column name or several."""
    apply_theme(theme)
    cols = [y] if isinstance(y, str) else list(y)
    colors = series_colors(theme)
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    for i, col in enumerate(cols):
        ax.plot(df[x], df[col], color=colors[i % len(colors)], linewidth=1.8, label=col)
    ax.set_title(title, color=theme.emphasis, loc="left", pad=10)
    ax.set_ylabel(ylabel)
    if xlabel:
        ax.set_xlabel(xlabel)
    if len(cols) > 1:
        ax.legend(frameon=False, labelcolor=theme.text)
    if as_of:
        fig.text(0.01, 0.01, f"as of {as_of}", color=theme.muted, fontsize=8)
    fig.tight_layout()
    return _save(fig, Path(out))


def bar_chart(
    df: pd.DataFrame,
    *,
    category: str,
    value: str,
    title: str,
    xlabel: str,
    out: Path | str,
    theme: Theme = DARK,
    horizontal: bool = True,
    as_of: str | None = None,
) -> Path:
    """Ranked bar chart (default horizontal — best for place names)."""
    apply_theme(theme)
    data = df.sort_values(value, ascending=True if horizontal else False)
    fig, ax = plt.subplots(figsize=(7.2, max(3.2, 0.35 * len(data) + 1.2)))
    if horizontal:
        ax.barh(data[category], data[value], color=theme.series1, height=0.65)
        ax.set_xlabel(xlabel)
    else:
        ax.bar(data[category], data[value], color=theme.series1, width=0.65)
        ax.set_ylabel(xlabel)
        ax.tick_params(axis="x", rotation=30)
    ax.set_title(title, color=theme.emphasis, loc="left", pad=10)
    if as_of:
        fig.text(0.01, 0.01, f"as of {as_of}", color=theme.muted, fontsize=8)
    fig.tight_layout()
    return _save(fig, Path(out))
