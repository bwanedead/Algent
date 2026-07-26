# Map & analytics stack (newsroom)

House readers need geography that is **accurate first**, then clear. Zoom-only village
clusters without national context fail that bar — the Lebanon pilot-zone figure was a live
example: three towns in a box, hard to place, easy to misread as "somewhere in the south."

## Managed install (dedicated venv)

Analytics packages live in **`analytics_workspace/.venv`**, not the system Python and not
(necessarily) `backend/.venv`. Pin list: `analytics_workspace/requirements.txt`.

```powershell
cd analytics_workspace
powershell -File scripts\setup_venv.ps1
```

| Package | Role |
|---------|------|
| numpy, pandas | series / tables |
| matplotlib | charts + map draw |
| shapely, pyproj | honest geometry |
| Pillow, imageio | PNG / short GIF |

**Excluded on purpose:** geopandas, GDAL, cartopy (heavy native builds). Country outlines come
from a **~1–2 MB** Natural Earth **110m** admin-0 GeoJSON (`scripts/download_basemap.py`).

Helpers (tracked): `analytics_workspace/lib/{theme,charts,maps,animate}.py`.

## Goals

| Need | Form |
|---|---|
| Where are these places? | Country (or theater) basemap + labeled points + optional inset |
| How big is this region vs the country? | Same, with relative frame |
| Where is intensity highest? | Choropleth from real per-region values only (later) |
| What changed on a front? | Theater map with dated layers + as-of (no invented fills) |
| Explain a sequence | Short GIF via `lib.animate` (few frames, under size cap) |

## Composition default

1. **Outer frame:** full country or multi-country theater.
2. **Inset / callout:** local cluster when detail matters.
3. **Landmarks:** capital, major city, border, named river only if prose uses it.
4. **Caption:** what is shown, as-of, coordinate/outline sources.

Never present freehand relative positions as geographic truth. Skip if honest geometry is
unavailable.

## Worker integration

- Doctrine: `analytics_workspace/AGENTS.md` points at the venv + `lib/`.
- Harness: `analytics_worker` REQUEST.md / prompt tell the grok worker to use
  `../.venv/.../python` and allow `.gif` / `map.svg` outputs.
- Scratch folders remain gitignored; stack + doctrine are tracked.

## Later

- Admin-1 / selective higher-res outlines when a story needs provinces (still not planet tiles).
- Choropleth join on ISO codes from public tables.
- Site-side interactive maps only as a separate product decision; pipeline still ships static SVG/PNG/GIF.

## What not to do

- Zoom-only cluster with no national context.
- AI-illustrated "map" that looks cartographic but is not geocoded.
- Heatmaps or "areas controlled by X" without real region values or official boundaries.
- `pip install` inside a run; mid-run dependency sprawl.
- Downloading global OSM/elevation dumps into the workspace.
