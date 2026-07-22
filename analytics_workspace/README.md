# analytics_workspace

Sandbox for newsroom **charts, maps, and short animations**. The editorial analytics worker
(grok-build) runs per-request scratch folders here. Doctrine: `AGENTS.md`.

## Managed stack (dedicated venv)

Do **not** install analytics packages into the system Python or the backend app venv unless
you intentionally want them there. This workspace has its own environment:

```powershell
cd analytics_workspace
powershell -File scripts\setup_venv.ps1
# or step by step:
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\download_basemap.py
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

| Package | Role |
|---------|------|
| numpy, pandas | tables / series |
| matplotlib | charts + map rendering |
| shapely, pyproj | honest geometry |
| Pillow, imageio | PNG/GIF frames |

**Not** included (on purpose): geopandas, GDAL, cartopy, folium — heavy native builds and
overkill for static country-scale SVG/PNG.

## Layout

```
analytics_workspace/
  AGENTS.md           worker doctrine (tracked)
  requirements.txt    pinned deps (tracked)
  lib/                theme, charts, maps, animate (tracked)
  scripts/            setup, basemap download, smoke (tracked)
  data/natural_earth/ basemap geojson (local, gitignored)
  .venv/              python env (local, gitignored)
  <request_id>/       per-run scratch (local, gitignored)
```

## Helpers (from a request folder)

```python
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]  # analytics_workspace/
sys.path.insert(0, str(ROOT))

from lib.charts import line_chart, bar_chart
from lib.maps import country_points_map, world_highlight_map
from lib.animate import frames_to_gif, render_frame_series
```

Use the venv interpreter:

```text
../.venv/Scripts/python.exe   # from a scratch subfolder on Windows
```

## Maps

Default composition: **country or theater frame** + labeled real lat/lon + optional inset box.
Basemap: Natural Earth 110m only. Accuracy rules in `AGENTS.md` and
`docs/architecture/map-analytics-stack.md`.
