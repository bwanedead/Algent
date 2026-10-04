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

## Daily-report maps (spec v2)

The geopolitics daily and the theater dossiers draw ONE map: `geo.build_map` (backend/algent_backend/agent_system/agents/intel/geo.py, with `geo_draw.py` for pure geometry and `geo_layers.py` for reference layers) produces a self-contained spec embedded in the daily record; `sites/ohmega-monster/components/map/GeoMap.tsx` draws it for both `/geopolitics` and `/intel/theaters/[id]`. Doctrine: `docs/ethos/information-ergonomics-ethos.md` — clear, accurate, utilitarian, not stylised.

**Data** (`analytics_workspace/scripts/download_basemap.py`, Natural Earth, public domain, gitignored under `data/natural_earth/`): 110m countries (~0.8 MB, fallback), 50m countries (3.1 MB, drawing and validation), 10m populated places simple (4.9 MB), 50m rivers + lake centerlines (0.8 MB), 50m lakes (0.9 MB). Every layer is optional: without 50m the map draws from 110m; without the rest it is land + marks. Crimea is drawn as Ukraine (`_RECOGNISED`) for land, validation and cities.

**Spec v2** (version 1 specs in stored records have only `bbox/projection/width/height/countries/points/credit`; the site defaults every v2 layer to empty):
`version, bbox, projection, width(1000), height, countries[{name,d}], labels[{name,x,y,r,key}], rivers[{d}], lakes[{d}], cities[{name,x,y,capital}], annotations[{kind,x,y,title,lines,series_id,source}], scale{km,px,label}, locator{width,height,d,rect}|null, points[...], credit`.
- Frame: points padded 35%, never narrower than 12 degrees, aspect 0.5-0.9 — a reader can always place the region.
- Simplification: Douglas-Peucker, tolerance 0.6 frame units at a 12-degree frame (~0.4 px), growing with sqrt(span), capped at 2.
- Labels: country name at a point inside its largest visible piece (`r` = room); countries holding an event are `key`.
- Cities: capitals first (all at country scale, fewer as the frame widens, but capitals of event countries always), then largest cities by population with minimum spacing and a budget that falls with frame width.
- Scale bar: round 1-2-5 km, exact at mid-latitude. Locator: world inset with the frame outlined, omitted for frames over half the world.
- Annotations: tracked chokepoints (`instruments/catalog.chokepoint_sites()`; hand-set coordinates, PortWatch gives none) inside the frame get the latest stored reading beside a year-ago reading ("37 ships/day · 35 a year ago / as of 27 Sep"). Store only, never network; `public_display` series only; nothing when the store is empty.

**Style** (map-local colours in `geopolitics.css`, identical in both themes — a light printed-map panel): pale water, light land, grey borders, thin blue rivers, dark labels with a white halo, numbered markers matching the development list (solid = researched, hollow = reported), small city dots, capitals bold, teal callout for instrument readings. Label placement is client-side (`layout.ts`) from the real rendered width: marks, callout, place names, capitals, country names, other cities, collision-checked — fewer labels on a phone, never overlapping ones.
