# Map data sources — what we may draw, from what

Researched 2026-10-01 for the daily geopolitics report's maps. Licences change: DeepState's says it
can be amended unilaterally. **Re-read a source's terms before its first publication and when in
doubt.** A public endpoint is not a licence.

## Verdicts

| Source | What it gives | Terms (source) | Verdict |
|---|---|---|---|
| **Natural Earth** | country/admin/coast base layers | public domain, credit unnecessary ([terms](https://www.naturalearthdata.com/about/terms-of-use/)) | **Use** for base maps and the disputed-areas layer (`ne_10m_admin_0_disputed_areas`, fallback `ne_50m_admin_0_breakaway_disputed_areas`), hatched on the map with a cited status note (`geo_disputed.STATUS`). Credit "Disputed areas: Natural Earth (public domain)". The layer is a static snapshot of who administers/claims what, not a front line, and is not current for Ukraine (Donetsk/Luhansk are the dataset's older outlines; Zaporizhzhia/Kherson occupation is absent). |
| **OpenStreetMap** | detailed base (cities, rivers, roads) | free with credit "© OpenStreetMap contributors" + ODbL link ([copyright](https://www.openstreetmap.org/copyright)); OSM tile servers restrict third-party use ([tile policy](https://operations.osmfoundation.org/policies/tiles/)) | **Use**, rendered by us from extracts, never their tiles. Confirm "produced work" status before publishing. |
| **Copernicus Sentinel** | satellite imagery | free/open; notice "Contains modified Copernicus Sentinel data [Year]" ([licence](https://cds.climate.copernicus.eu/licences/ec-sentinel)) | **Use** for imagery context. |
| **NASA FIRMS** | thermal anomalies | NASA data CC0 unless marked ([policy](https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-policy)); needs a free MAP_KEY | **Use** as corroboration only, labelled "thermal anomalies", never as strike or front-line evidence. |
| **UCDP GED / Candidate** | georeferenced conflict events | CC BY 4.0 with citation ([downloads](https://ucdp.uu.se/downloads/)) | **Use** for history and trends; too slow (≈1-month lag) for daily. |
| **GDELT** | machine-coded news events | free incl. commercial, cite + link gdeltproject.org ([about](https://gdeltproject.org/about.html)) | **Signal only**, heavily filtered, never presented as fact. |
| **DeepStateMap** | Russia–Ukraine occupied-territory polygons, daily history | API free for volunteer/charitable/defence-of-Ukraine use; commercial use needs prior approval ([request](https://api.deepstatemap.live/request)); visual materials with credit/logo/link may be used freely ([licence](https://deepstatemap.live/license-en.html)) | **Best front-line source, needs written permission** before we fetch the API and publish derived maps (area gained/lost). Until then: only credited visual materials as their licence allows. |
| **ACLED** | geocoded conflict events | commercial use needs a corporate licence; only transformative, non-reverse-engineerable products; no dashboard-style reuse; no scraping ([EULA](https://acleddata.com/eula), [content use](https://acleddata.com/contentusage)) | **Needs a licence / written confirmation.** If granted: aggregated products only (counts, trends, heatmaps), never raw pins. |
| **ISW / CTP control map** | assessed control polygons | "You may not use this geodata without the written consent of ISW" (ArcGIS item terms) | **Do not use** (nor Wikimedia maps derived from it). |
| **Liveuamap** | event pins | terms unreadable (403) | **Exclude** until terms are read. |
| **Militaryland.net** | deployment/map data | "CC BY-SA 4.0 unless stated otherwise" — unclear for map layers; reportedly stale | **Exclude** until confirmed. |

## Pipeline

- **Base maps:** Natural Earth + OSM extracts rendered by us (+ Sentinel where imagery helps). No
  commercial basemap tiles.
- **Russia–Ukraine front line:** DeepState, once permission is in writing. Daily snapshot ~03:00 UTC
  into our own archive (one polite fetch a day). Diff day N vs N−1 in an equal-area projection
  (EPSG:6933): `gained = N − (N−1)`, `lost = (N−1) − N`, km² per side; drop slivers and topology
  noise; treat tiny changes as unreliable. Caption: "Front line: DeepStateMap.live (open-source
  assessment; accuracy not guaranteed). Changes computed by Ohmega from successive daily DeepState
  snapshots." with link and logo.
- **Disputed and occupied territory (live):** Natural Earth disputed areas, drawn by `geo_disputed.py` as a hatch over
  the internationally recognised base map (Crimea stays Ukraine's, hatched as occupied). Wording per area is factual
  — recognised status, who controls it now, since when — each with a source URL; areas not in the table carry only
  the dataset's own note.
- **Front-line seam (not built — needs DeepState permission):** a licensed control layer plugs in beside
  `Layers.disputed` in `geo_layers.load_layers` as a dated polygon of control per side
  (`{as_of, side, polygons}`) read from our own daily snapshot archive, plus the day-over-day diff above as
  `{gained_km2, lost_km2}` per side. `geo.build_map` would draw it as a distinct layer (a solid control fill, not the
  disputed hatch — one meaning per visual channel) and the caption above would be added to the credit. Until
  permission is in writing, no front-line data is fetched, stored or drawn.
- **Other theaters:** our own report's developments plotted on Natural Earth (fully ours); UCDP for
  history; FIRMS/Sentinel as labelled corroboration; ACLED aggregates only if licensed. Maritime
  incidents (Hormuz, Red Sea: UKMTO, IMO, …) need their own source review.

## Open items
- Is Ohmega "commercial" under DeepState's and ACLED's terms? (Its free tier is for volunteer,
  charitable and defence-of-Ukraine entities, so non-commercial is not automatically free.)
- Written replies from DeepState and ACLED — requests are sent by the operator, not by an agent.
- FIRMS MAP_KEY (operator registers), rate limits; UCDP API token requirement.
