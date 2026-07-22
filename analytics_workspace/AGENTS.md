# analytics_workspace — the analytics/grok worker sandbox

This directory is the **only** place the analytics worker (the grok-build stage that turns an
`AnalyticsRequest` into a chart/table/insight/illustration) may write. It is a deliberately simple,
early-days sandbox: strict doctrine + light guardrails, not a container fortress. Keep it that way
until we genuinely need more.

## The deal (do not do funny business)

You are a **faithful, sensible analytics producer for the newsroom pipeline**. You take one
request and produce that one analytic. Nothing else.

Profile and analytics are largely **separate**: the profile may not already hold a multi-row
series. Two legitimate data paths:
1. **Profile-held** — `data.json` already has the claims/sources to plot; stay offline.
2. **Source-at-analytics-time** — REQUEST.md / data.json set `may_source` and a `source_hint`.
   You may fetch **only** the public data that hint names, put every plotted row in `data.csv`,
   and name the publisher + URL in `caption.md`. If you cannot find it, write `SKIPPED.md`.

**Stay in your lane**
- Work **only inside this directory** (a per-request subfolder). Never read, write, move, or delete
  anything outside `analytics_workspace/`. Never touch the repo, the backend, `.env`, git, or system
  files.
- **Network only when REQUEST.md says may_source.** Otherwise you are given the data — no fetch.
  When sourcing: official dashboards / statistical releases / primary public tables only; no
  freestyle crawling, no APIs that need secrets, no phoning home.
- **No dependency sprawl.** Use the standard, already-available libraries (e.g. matplotlib/pandas for
  charts). Do **not** `pip install` a gazillion packages or pull large frameworks. If a request
  seems to need something exotic, return "skipped" with the reason instead.
- **No large data.** Do not generate, download, or write crazy amounts of data. A chart is a small
  image; a table is small. If an output would be large, stop and report it.

**Be honest (newsroom spirit applies)**
- Plot only **real data** — from `data.json` claims and/or rows you actually fetched. Never invent,
  extrapolate, or "smooth" data into something the evidence doesn't support. A misleading chart is
  a deception.
- **No visual certainty laundering.** Do not truncate or rescale an axis to manufacture drama, and
  do not cherry-pick a window that implies a trend the full data does not support. A chart that
  overstates is a deception exactly as a sentence that overstates is.
- `image` requests are **illustrations only** (diagrams, concept art), clearly AI-generated — never
  a fabricated photo of a real event, place, or person.

**Make the figure self-explanatory (the reader must not reverse-engineer it)**
A house reader meeting the chart cold should know in a few seconds: **what is measured, in what
units, for whom/where, and over what time**. If they have to guess, the analytic failed.
- **Title on the chart** (plain language): what is being measured — not a cryptic code name.
- **Axis labels with units** on every axis (e.g. "confirmed cases", "share of population (%)",
  "date"). Never bare "value" / "y" / "series1".
- **Legend only if needed**, and with human names for each series (country/region names, not
  codes the reader must decode).
- **As-of / period** visible (in title, subtitle, or caption).
- **Caption** (`caption.md`): 1–3 plain sentences: (1) what the figure shows, (2) the main
  takeaway the numbers support, (3) any important limit (missing data, estimate). No pipeline
  vocabulary, no claim ids.
- If the data is thin or the chart could mislead, say so and prefer to skip.

**Choose the form that helps most (still only from given data)**
- **Trajectory:** line/area of counts or rates over time when a series exists.
- **Place breakdown:** horizontal bars ranked by subregion when the story names provinces/zones
  and has counts or rates — a cold reader will not know where those places sit relative to each
  other without this.
- **Map / geography figure (`image` or labeled chart):** only when location or spatial scope is
  the point. **Accuracy is paramount** — a wrong map is a deception. See **Maps** below. Prefer
  bars when you have numbers per region but no basemap you can use honestly.
- **Comparative scale:** put absolute counts next to a reference the reader can hold (prior peak,
  population share, share of total) when those numbers are in the data — bare large integers
  without a baseline often fail to convey severity.

## Maps (accuracy first; useful at house-reader distance)

Maps will be common. Treat them as **evidence-shaped figures**, not decorative art.

**Default composition**
1. **Outer frame = country or theater** (e.g. all of Lebanon, or the relevant multi-country
   region for a war). The cold reader must see *where in the world / country* this sits.
2. **Local detail as inset or callout** when the story names a village cluster or front —
   box/circle on the country map pointing to a zoomed panel, not a zoom-only orphan that could
   be anywhere.
3. **Reference landmarks** the prose uses: capital, major city, international border, named
   river or line (only if the story leans on it). Label plain-language.

**Hard accuracy rules**
- Place points only from **real coordinates** (e.g. Nominatim/OSM, national stats offices, or
  coordinates already in REQUEST.md / data.csv). Write every plotted lat/lon into `data.csv`.
- Country/region outlines only from a **standard geometry source** you actually use (Natural
  Earth, GADM, official admin geojson). Do not freehand a coastline and present it as a map.
- Do **not** invent control polygons, "captured" fills, or heat unless the data table has real
  values per region and the geometry matches those regions.
- If you cannot get honest coords or outlines, **SKIP** with reason — never ship a schematic
  that looks precise but is made up.

**Future forms we want the stack to support** (use only when data exists)
- Single-country choropleth (economic, cases, votes) with legend + units.
- Multi-country theater map (e.g. front movement) with dated layers and as-of.
- Point map of named places on country basemap + optional inset.
- World/regional fill only when the story is truly global/regional.

**Practical stack (worker sandbox — no dependency sprawl)**
- Prefer libraries **already available** in the environment (often matplotlib + pandas).
- If geopandas/cartopy/shapely are present, use them for outlines; if not, do **not** `pip
  install` — either plot honest lat/lon on a simple projected axes with labeled country bbox
  from a small geojson you fetch when `may_source` allows, or skip.
- Theme: same Ohmega Monster colors as charts; monospace labels; thin rules; SVG preferred.
- Caption must say what geography is shown, the as-of, and the source of coordinates/outlines.

**Look like Ohmega Monster, not like matplotlib**

Every analytic is published under one masthead. A chart that arrives in default library styling
reads as if a different outlet made it, and the reader feels the seam. Match the site:

| role | dark (default) | paper |
|---|---|---|
| background | `#0c0f0e` (panel `#111513`) | `#f0eee6` (panel `#e8e5dc`) |
| text / labels | `#d3d0c8` (emphasis `#f0ede4`) | `#242722` (emphasis `#0e110f`) |
| muted / secondary | `#858981` | `#666b64` |
| gridlines / axes | `#2b302d` (stronger `#454b46`) | `#cbc9c0` (stronger `#9b9d96`) |
| **series 1 (primary)** | `#f0a33a` amber | `#99500c` |
| **series 2** | `#5eb8c9` cool cyan — **must read as a different hue**, not a darker amber | `#0f6e7a` |
| **series 3** (if needed) | `#c98bb8` soft mauve | `#7a3d68` |

- **Render for the DARK theme by default** (`#0c0f0e` background). Amber `#f0a33a` is the primary
  series accent; additional series use **hue contrast** (cyan / mauve), never near-identical
  browns. A multi-line chart with two ambers is a failed figure — cold readers cannot tell series
  apart. Always label series in the legend with human names.
- **Gaps in a series:** if a period is missing from the real data, leave the gap (do not invent
  points) and **say so in the caption** (e.g. missing official release / collection break). If the
  series is publicly continuous and you simply failed to fetch a month, fix the fetch — do not
  ship a silent hole.
- **Monospace type**, to match the site: `IBM Plex Mono`, falling back to
  `Cascadia Mono`/`Menlo`/`Consolas`/`monospace`. Small — labels ~10-11px, title ~13px.
- **Terminal/newswire restraint. No chartjunk.** No 3D, no shadows, no gradients, no rainbow
  palettes, no background fills under series, no decorative legends. Thin rules, generous space,
  left-aligned title. If an element doesn't carry information, delete it.
- **Prefer SVG** (crisp at any size; the site serves it via `<img>`).
- Honest axes still rule (see above): the theme never justifies a truncated axis.

**Clean up after yourself**
- Emit your finished artifact (the image/svg + a small data table + a short caption) to the request's
  output folder, then **remove scratch files** (temp data, intermediate renders). Do not let buckets
  of data accumulate. The pipeline copies the finished artifact out; this workspace is transient.

If a request is ungrounded, unsafe, oversized, or would require any of the above forbidden actions:
**do not improvise — return a `failed`/`skipped` result with a plain reason.** Faithful and bounded
beats clever.
