# Visuals in articles — maps, charts, theme images

## What ships today
- **Maps & charts** come from the analytics router + worker (`ALGENT_ANALYTICS_WORKER`, default **on**).
- **Maps** are preferred when place/chokepoint/theater orientation would help a cold reader
  (Bab el-Mandeb, multi-city strike patterns, etc.). Worker uses Natural Earth basemap + real
  lat/lon points (`analytics_workspace/lib/maps.py`). Never freehand geography.
- Maps are **interleaved early** in the published body (after the opening landscape), not only
  dumped after the wall of text.
- **X posts**: a sole-line markdown link `[Post on X · @handle](https://x.com/…/status/…)` embeds
  on the site (`XPostEmbed`). Naming a handle without the URL does not embed; publish will inject
  the sole-line link when the prose names X/@handle and a status is in the source ledger.
- Site-live must include `XPostEmbed` / `Prose` embed wiring (merge `organic-dev` site code if
  drift_warning says components are behind).

## Theme / stock illustrations (planned — not a wire yet)
Goal: optional **honest atmosphere** art (Grok Imagine or similar) so pieces are not only text +
data visuals — a topic mood image, not evidence.

Constraints (do not violate):
- Never a fabricated photograph of a **real event** or real person as if documentary.
- Always labeled as AI-generated atmosphere / illustration in caption or frontmatter.
- Never a substitute for a **map** when geography is the aid.
- Optional, cheap, one per piece max; skip when map/chart already carries the visual load.

Likely path: router or a tiny post-draft stage emits a `theme_prompt` + `theme_image` asset;
publish puts it under `public/illustrations/<slug>/` with frontmatter `hero:` for the site.

## Operator toggles
| Env | Default | Meaning |
|-----|---------|---------|
| `ALGENT_ANALYTICS_WORKER` | on (`1`) | Fulfill map/chart requests |
| `ALGENT_ANALYTICS_MAX` | `2` | Cap requests per piece (map + trajectory OK) |
