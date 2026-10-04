"""Short GIF helpers for explanatory motion (not video pipelines).

Keep GIFs small: few frames, modest resolution, under the worker size cap (~2MB).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

import imageio.v2 as imageio
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from .theme import DARK, Theme, apply_theme, watermark


def frames_to_gif(
    frames: Sequence[Path | str | np.ndarray],
    out: Path | str,
    *,
    fps: float = 4.0,
    loop: int = 0,
) -> Path:
    """Assemble image paths or RGB arrays into a GIF."""
    out_p = Path(out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    imgs: list[np.ndarray] = []
    for f in frames:
        if isinstance(f, (str, Path)):
            imgs.append(np.asarray(Image.open(f).convert("RGB")))
        else:
            imgs.append(np.asarray(f))
    if not imgs:
        raise ValueError("no frames")
    duration = 1.0 / max(fps, 0.1)
    imageio.mimsave(out_p, imgs, duration=duration, loop=loop)
    return out_p


def render_frame_series(
    draw: Callable[[plt.Axes, int, Theme], None],
    *,
    n_frames: int,
    out_dir: Path | str,
    theme: Theme = DARK,
    figsize: tuple[float, float] = (6.4, 3.6),
    dpi: int = 100,
) -> list[Path]:
    """Call ``draw(ax, i, theme)`` for i in 0..n-1; save PNG frames; return paths."""
    apply_theme(theme)
    out_d = Path(out_dir)
    out_d.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i in range(n_frames):
        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
        draw(ax, i, theme)
        watermark(fig, theme)
        path = out_d / f"frame_{i:03d}.png"
        fig.savefig(path, bbox_inches="tight", pad_inches=0.15)
        plt.close(fig)
        paths.append(path)
    return paths
