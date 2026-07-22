# Map analytics stack (newsroom)

House readers need geography that is **accurate first**, then clear. Zoom-only village
clusters without national context fail that bar — the Lebanon pilot-zone figure was a live
example: three towns in a box, hard to place, easy to misread as "somewhere in the south."

## Goals

| Need | Form |
|---|---|
| Where are these places? | Country (or theater) basemap + labeled points + optional inset |
| How big is this region vs the country? | Same, with scale bar / relative markers |
| Where is intensity highest? | Choropleth from real per-region values only |
| What changed on a front? | Theater map with dated layers + as-of (no invented fills) |

## Composition default

1. **Outer frame:** full country or multi-country theater relevant to the story.
2. **Inset / callout:** local cluster or front when detail matters.
3. **Landmarks:** capital, major city, border, and any line/river the prose uses.
4. **Caption:** what is shown, as-of, coordinate/outline sources.

Never present freehand relative positions as geographic truth. Skip if honest geometry is
unavailable.

## Implementation path (staged)

**Now (worker doctrine, no new installs forced)**
- Analytics router + `analytics_workspace/AGENTS.md` require country-scale default + real
  geocodes when maps are requested.
- Worker may Nominatim/OSM (when `may_source`) for place coords; put rows in `data.csv`.
- Prefer SVG; Ohmega Monster theme tokens already in AGENTS.md.

**Next (when the maintainer adds deps deliberately)**
- Pin a small stack in the analytics/worker environment only, e.g.:
  - `matplotlib` (already intended for charts)
  - `shapely` + `pyproj` for geometry
  - optional `geopandas` or pure GeoJSON + matplotlib `PathPatch`
- Vendor or cache **Natural Earth 110m/50m** admin-0 (and admin-1 when needed) under a
  gitignored data dir the worker may read — not full planet tiles.
- Thin helper module (e.g. `analytics_workspace/lib/maps.py` later): `country_frame(iso)`,
  `plot_points(lons, lats, labels)`, `inset_box(...)`, theme applied once.

**Later (dynamic / multi-run)**
- Choropleth join on ISO/admin codes from public tables.
- Multi-layer conflict maps only with dated claim-backed polygons or official lines.
- Optional interactive (site-side) is a separate product decision; pipeline still ships a
  static SVG/PNG that stands alone.

## What not to do

- Zoom-only cluster with no national context.
- AI-illustrated "map" that looks cartographic but is not geocoded.
- Heatmaps or "areas controlled by X" without real region values or official boundaries.
- Installing packages ad hoc inside a run (`pip install` is forbidden in the sandbox).

## Ownership

- **Router** decides *whether* a map helps and specifies country-scale + data path.
- **Worker** builds only honest figures inside `analytics_workspace/`.
- **Doctrine** (spirit / molecule / comprehension) keeps prose from assuming the reader
  already knows the places; the map supports that orientation, it does not replace it.
