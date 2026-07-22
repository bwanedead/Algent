"""Prove the analytics venv + basemap can draw a chart, a country map, and a tiny GIF."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "_smoke"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    import pandas as pd

    from lib.animate import frames_to_gif, render_frame_series
    from lib.charts import bar_chart, line_chart
    from lib.maps import basemap_available, country_points_map, world_highlight_map
    from lib.theme import DARK

    print("theme:", DARK.name)
    print("basemap available:", basemap_available())
    if not basemap_available():
        print("run: python scripts/download_basemap.py", file=sys.stderr)
        return 1

    # Chart
    df = pd.DataFrame({"month": ["Mar", "Apr", "May", "Jun"], "value": [1.1, 1.4, 1.2, 1.8]})
    p1 = line_chart(
        df, x="month", y="value", title="Smoke: monthly index",
        ylabel="index", out=OUT / "chart.svg", as_of="smoke",
    )
    print("chart:", p1, p1.stat().st_size, "bytes")

    bars = pd.DataFrame({"place": ["A", "B", "C"], "count": [12, 7, 19]})
    p2 = bar_chart(
        bars, category="place", value="count", title="Smoke: places",
        xlabel="count", out=OUT / "bars.svg", as_of="smoke",
    )
    print("bars:", p2)

    # Country map — Lebanon-ish sample points (real-ish coords for smoke only)
    p3 = country_points_map(
        countries=["LBN", "ISR", "SYR"],
        points=[
            {"name": "Beirut", "lon": 35.5018, "lat": 33.8938},
            {"name": "sample village", "lon": 35.35, "lat": 33.25},
        ],
        title="Smoke: Lebanon theater + points",
        out=OUT / "map.svg",
        as_of="smoke",
        inset={"lon_min": 35.2, "lon_max": 35.5, "lat_min": 33.1, "lat_max": 33.4, "label": "south cluster"},
    )
    print("map:", p3, p3.stat().st_size, "bytes")

    p4 = world_highlight_map(
        highlight=["LBN", "USA"],
        title="Smoke: world highlight",
        out=OUT / "world.svg",
        as_of="smoke",
    )
    print("world:", p4)

    # Tiny GIF
    def draw(ax, i, theme):
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 1)
        ax.barh([0], [i + 1], color=theme.series1, height=0.4)
        ax.set_title(f"frame {i}", color=theme.emphasis, loc="left")
        ax.set_yticks([])

    frames = render_frame_series(draw, n_frames=5, out_dir=OUT / "frames")
    gif = frames_to_gif(frames, OUT / "motion.gif", fps=3)
    print("gif:", gif, gif.stat().st_size, "bytes")
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
