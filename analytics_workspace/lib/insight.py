"""Phone-first insight figures — takeaway in the title, one thing to look at, source on the image.

These are the only forms the insight lane may emit. Generic line/bar helpers stay in
``charts.py`` for article sidecars; this module is the public chart, not a notebook dump.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Sequence

import matplotlib.pyplot as plt
import pandas as pd

from .animate import frames_to_gif
from .theme import DARK, Theme, apply_theme, series_colors, watermark

#: Leave a footer strip for source (left) + brand (right). Watermark used to
#: sit on the series at figure (0.88, 0.14); it lives in this band now.
_FOOTER = (0, 0.14, 1, 1)

#: 4:5-ish, readable in the X crop. Wider notebooks hide the takeaway.
_SIZE = (7.2, 9.0)
_MAX_BARS = 8
_MAX_SLOPE = 6
_MAX_GIF_FRAMES = 12


def _wrap(title: str, width: int = 36) -> str:
    return "\n".join(textwrap.wrap((title or "").strip(), width=width) or [""])


def _footer(fig: plt.Figure, theme: Theme, source: str, as_of: str) -> None:
    bits = [p for p in (source.strip(), f"as of {as_of}" if as_of else "") if p]
    if bits:
        fig.text(0.04, 0.02, " · ".join(bits), color=theme.muted, fontsize=8, ha="left")


def _save(fig: plt.Figure, path: Path, theme: Theme = DARK) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    watermark(fig, theme)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.36)
    plt.close(fig)
    return path


def takeaway_bars(
    rows: Sequence[dict[str, Any]],
    *,
    title: str,
    unit: str,
    out: Path | str,
    highlight: str = "",
    source: str = "",
    as_of: str = "",
    theme: Theme = DARK,
) -> Path:
    """Horizontal bars. The highlighted row is the one the title is about."""
    apply_theme(theme)
    data = list(rows)[:_MAX_BARS]
    if not data:
        raise ValueError("takeaway_bars needs rows")
    labels = [str(r["label"]) for r in data]
    values = [float(r["value"]) for r in data]
    needle = (highlight or "").casefold()
    colors = [
        theme.series1 if needle and needle in lab.casefold() else theme.muted
        for lab in labels
    ]
    if highlight and theme.series1 not in colors:
        colors[-1] = theme.series1

    order = sorted(range(len(values)), key=lambda i: values[i])
    labels = [labels[i] for i in order]
    values = [values[i] for i in order]
    colors = [colors[i] for i in order]

    fig, ax = plt.subplots(figsize=_SIZE)
    ax.barh(labels, values, color=colors, height=0.62)
    ax.set_xlabel(unit)
    ax.set_title(_wrap(title), color=theme.emphasis, loc="left", pad=12, fontsize=15)
    xmax = max(values) if values else 1.0
    ax.set_xlim(0, xmax * 1.18)
    for lab, val in zip(labels, values, strict=True):
        ax.text(val + xmax * 0.02, lab, _fmt(val), va="center", color=theme.text, fontsize=9)
    _footer(fig, theme, source, as_of)
    fig.tight_layout(rect=_FOOTER)
    return _save(fig, Path(out), theme)


def takeaway_slope(
    rows: Sequence[dict[str, Any]],
    *,
    title: str,
    unit: str,
    out: Path | str,
    series: Sequence[str],
    source: str = "",
    as_of: str = "",
    highlight: str = "",
    theme: Theme = DARK,
) -> Path:
    """Two-state slopegraph — then/now or A/B per row. Not a ranked bar list."""
    apply_theme(theme)
    left = (series[0] if series else "before")
    right = (series[1] if len(series) > 1 else "after")
    items: list[tuple[str, float, float]] = []
    for r in list(rows)[:_MAX_SLOPE]:
        lab = str(r.get("label") or r.get("x") or "").strip()
        a = r.get(left, r.get("y"))
        b = r.get(right, r.get("y2"))
        if not lab or a is None or b is None:
            continue
        items.append((lab, float(a), float(b)))
    if len(items) < 2:
        raise ValueError("takeaway_slope needs two rows with both ends")
    needle = (highlight or "").casefold()
    fig, ax = plt.subplots(figsize=_SIZE)
    ymin = min(v for _, a, b in items for v in (a, b))
    ymax = max(v for _, a, b in items for v in (a, b))
    pad = (ymax - ymin) * 0.14 or 1.0
    ax.set_xlim(-0.55, 1.25)
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.set_xticks([0, 1], [left, right])
    ax.set_ylabel(unit)
    ax.set_title(_wrap(title), color=theme.emphasis, loc="left", pad=12, fontsize=15)
    for lab, a, b in items:
        hot = bool(needle) and needle in lab.casefold()
        color = theme.series1 if hot else theme.muted
        ax.plot([0, 1], [a, b], color=color, linewidth=2.4 if hot else 1.5, zorder=2)
        ax.scatter([0, 1], [a, b], color=color, s=42 if hot else 28, zorder=3)
        ax.text(-0.04, a, f"{lab}  {_fmt(a)}", ha="right", va="center",
                color=theme.emphasis if hot else theme.text, fontsize=8)
        ax.text(1.04, b, _fmt(b), ha="left", va="center",
                color=theme.emphasis if hot else theme.text, fontsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    _footer(fig, theme, source, as_of)
    fig.tight_layout(rect=_FOOTER)
    return _save(fig, Path(out), theme)


def takeaway_line(
    rows: Sequence[dict[str, Any]],
    *,
    title: str,
    unit: str,
    x_key: str,
    series: Sequence[str],
    out: Path | str,
    source: str = "",
    as_of: str = "",
    callout: str = "",
    theme: Theme = DARK,
) -> Path:
    """One or few lines. ``callout`` is the last-point label for the first series."""
    apply_theme(theme)
    df = pd.DataFrame(list(rows))
    if df.empty or x_key not in df.columns:
        raise ValueError("takeaway_line needs rows with the x column")
    colors = series_colors(theme)
    fig, ax = plt.subplots(figsize=_SIZE)
    for i, col in enumerate(series):
        if col not in df.columns:
            continue
        ax.plot(df[x_key], df[col], color=colors[i % len(colors)], linewidth=2.2, label=col)
        last = df[col].iloc[-1]
        ax.scatter(df[x_key].iloc[-1], last, color=colors[i % len(colors)], s=36, zorder=3)
        if i == 0:
            label = callout or _fmt(float(last))
            ax.annotate(
                label, (df[x_key].iloc[-1], last),
                textcoords="offset points", xytext=(-4, 10),
                ha="right", color=theme.emphasis, fontsize=10,
            )
    ax.set_ylabel(unit)
    ax.set_title(_wrap(title), color=theme.emphasis, loc="left", pad=12, fontsize=15)
    if len([c for c in series if c in df.columns]) > 1:
        ax.legend(frameon=False, labelcolor=theme.text, loc="upper left")
    _footer(fig, theme, source, as_of)
    fig.tight_layout(rect=_FOOTER)
    return _save(fig, Path(out), theme)


def growing_line_gif(
    rows: Sequence[dict[str, Any]],
    *,
    title: str,
    unit: str,
    x_key: str,
    series: Sequence[str],
    out: Path | str,
    source: str = "",
    as_of: str = "",
    theme: Theme = DARK,
    fps: float = 3.0,
) -> Path:
    """Reveal competing curves over time. Last frames hold so the end state is readable."""
    apply_theme(theme)
    df = pd.DataFrame(list(rows))
    if df.empty or x_key not in df.columns:
        raise ValueError("growing_line_gif needs a time column")
    cols = [c for c in series if c in df.columns][:3]
    if not cols:
        raise ValueError("growing_line_gif needs at least one series column")
    n = min(len(df), _MAX_GIF_FRAMES)
    idx = [max(1, round((i + 1) * len(df) / n)) for i in range(n)]
    idx = sorted(set(idx))
    if idx[-1] != len(df):
        idx.append(len(df))
    colors = series_colors(theme)
    ymin = min(float(df[c].min()) for c in cols)
    ymax = max(float(df[c].max()) for c in cols)
    pad = (ymax - ymin) * 0.12 or 1.0
    frames: list[Path] = []
    tmp = Path(out).parent / "_gif_frames"
    tmp.mkdir(parents=True, exist_ok=True)
    hold = list(idx) + [idx[-1], idx[-1]]
    for f, end in enumerate(hold):
        slice_df = df.iloc[:end]
        fig, ax = plt.subplots(figsize=_SIZE)
        for i, col in enumerate(cols):
            ax.plot(slice_df[x_key], slice_df[col], color=colors[i], linewidth=2.2, label=col)
            ax.scatter(slice_df[x_key].iloc[-1], slice_df[col].iloc[-1],
                       color=colors[i], s=36, zorder=3)
        ax.set_ylim(ymin - pad, ymax + pad)
        ax.set_xlim(df[x_key].iloc[0], df[x_key].iloc[-1])
        ax.set_ylabel(unit)
        ax.set_title(_wrap(title), color=theme.emphasis, loc="left", pad=12, fontsize=15)
        if len(cols) > 1:
            ax.legend(frameon=False, labelcolor=theme.text, loc="upper left")
        _footer(fig, theme, source, as_of)
        fig.tight_layout(rect=_FOOTER)
        watermark(fig, theme)
        frame = tmp / f"f{f:03d}.png"
        fig.savefig(frame, bbox_inches="tight", pad_inches=0.36)
        plt.close(fig)
        frames.append(frame)
    gif = frames_to_gif(frames, out, fps=fps)
    for p in frames:
        p.unlink(missing_ok=True)
    return gif


def _fmt(value: float) -> str:
    if abs(value) >= 100:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:,.1f}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")
