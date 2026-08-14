# analytics_workspace — the analytics/grok worker sandbox

This directory is the **only** place the analytics worker (the grok-build stage that turns an
`AnalyticsRequest` into a chart/table/insight/illustration) may write. It is a deliberately simple,
early-days sandbox: strict doctrine + light guardrails, not a container fortress. Keep it that way
until we genuinely need more.

## Weight-bearing stack (do not delete)

These tracked paths are **runtime dependencies** of every visual article, not optional samples:

| Path | Role |
|---|---|
| `lib/__init__.py`, `lib/theme.py`, `lib/charts.py`, `lib/maps.py`, `lib/animate.py`, `lib/insight.py` | Canonical helpers the worker (and the insight lane) import |
| `scripts/setup_venv.ps1`, `scripts/download_basemap.py`, `scripts/smoke_test.py`, `scripts/draw_insight.py` | Reproducible stack setup + canary + insight draw |
| `data/README.md` | Documents the Natural Earth basemap location |
| `requirements.txt`, this `AGENTS.md`, `README.md` | Pins + doctrine |

Scratch folders (`<request_id>/`, `_canary/`), `.venv/`, and downloaded `data/natural_earth/` are
local/gitignored. Deleting or “cleaning up” `lib/` or `scripts/` breaks map/chart production even
when the editorial pipeline is healthy — the worker will refuse the stack rather than freehand
geography. If a helper must change, edit it in place or replace it with an equivalent import path
and update `analytics_worker` briefs in the same change.

**Pipeline invariant:** `sweep_stale_scratch` may only remove scratch-shaped dirs (`anx_*`,
`req_*`, `_canary`). It must never age-delete `lib/`, `scripts/`, or `data/` — that bug
previously wiped the stack after ~2h idle and shipped articles with zero visuals.

## Python environment (use this — do not pip install mid-run)

A **dedicated venv** lives at `analytics_workspace/.venv` with a pinned stack
(`requirements.txt`: numpy, pandas, matplotlib, shapely, pyproj, Pillow, imageio).

From a per-request scratch folder (cwd is `analytics_workspace/<request_id>/`):

```text
Windows:  ..\.venv\Scripts\python.exe
Unix:     ../.venv/bin/python
```

- Prefer that interpreter for every chart/map/GIF script.
- Import helpers: `sys.path.insert(0, str(Path("..").resolve()))` then `from lib.charts import …`
  / `from lib.maps import …` / `from lib.animate import …`.
- **Never** `pip install` during a request. If a library is missing, write `SKIPPED.md` and stop.
- Basemap file: `../data/natural_earth/ne_110m_admin_0_countries.geojson` (setup script downloads
  it once). If missing, skip map figures with that reason.

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
  files. Reading `../lib/`, `../data/`, and `../AGENTS.md` is allowed (stack + basemap).
- **Network only when REQUEST.md says may_source.** Otherwise you are given the data — no fetch.
  When sourcing: official dashboards / statistical releases / primary public tables only; no
  freestyle crawling, no APIs that need secrets, no phoning home.
- **No dependency sprawl.** Use the workspace venv libraries only. Do **not** `pip install`.
- **No large data.** Charts/maps/short GIFs are small. If an output would be large, stop and report.

**Be honest (newsroom spirit applies)**
- Plot only **real data** — from `data.json` claims and/or rows you actually fetched. Never invent,
  extrapolate, or "smooth" data into something the evidence doesn't support. A misleading chart is
  a deception.
- **No visual certainty laundering.** Do not truncate or rescale an axis to manufacture drama, and
  do not cherry-pick a window that implies a trend the full data does not support.
- `image` requests for **maps** must use real geocodes + the Natural Earth basemap. Pure concept
  diagrams may be schematic and must not look like fake cartography of real places. Never fabricate
  a photo of a real event, place, or person.

**Make the figure self-explanatory (the reader must not reverse-engineer it)**
A house reader meeting the chart cold should know in a few seconds: **what is measured, in what
units, for whom/where, and over what time**. If they have to guess, the analytic failed.
- **Title on the chart** (plain language): what is being measured — not a cryptic code name.
- **Axis labels with units** on every axis. Never bare "value" / "y" / "series1".
- **Legend only if needed**, human names for each series.
- **As-of / period** visible (title, subtitle, or caption).
- **Caption** (`caption.md`): 1–3 plain sentences: (1) what the figure shows, (2) the main
  takeaway, (3) any important limit. No pipeline vocabulary, no claim ids.
- If the data is thin or the chart could mislead, say so and prefer to skip.

**Choose the form that helps most (still only from given data)**
- **Trajectory:** `lib.charts.line_chart` when a series exists.
- **Place breakdown:** `lib.charts.bar_chart` (horizontal) when ranked regions have counts/rates.
- **Map:** `lib.maps.country_points_map` / `world_highlight_map` when location/scope is the point.
  **Accuracy is paramount** — see Maps below.
- **Short motion:** `lib.animate` for a few-frame GIF that explains a sequence — keep under ~2MB.
- **Comparative scale:** put absolute counts next to a holdable reference when numbers exist.

## Maps (accuracy first; useful at house-reader distance)

1. **Outer frame = country or theater** (e.g. all of Lebanon + neighbors), not a zoom-only
   cluster of three towns with no national context.
2. **Local detail as inset box** on that frame when the story names a village cluster.
3. **Points only from real lat/lon** — write every plotted coordinate into `data.csv`.
4. **Outlines only from** `data/natural_earth/ne_110m_admin_0_countries.geojson`.
5. Never invent control polygons, heat, or freehand coastlines presented as truth. Skip if you
   cannot get honest coords/outlines.

## Look like Ohmega Monster, not like default matplotlib

Use `lib.theme.apply_theme()` (dark default). Tokens:

| role | dark (default) | paper |
|---|---|---|
| background | `#0c0f0e` (panel `#111513`) | `#f0eee6` (panel `#e8e5dc`) |
| text / labels | `#d3d0c8` (emphasis `#f0ede4`) | `#242722` (emphasis `#0e110f`) |
| muted / secondary | `#858981` | `#666b64` |
| gridlines / axes | `#2b302d` (stronger `#454b46`) | `#cbc9c0` (stronger `#9b9d96`) |
| **series 1 (primary)** | `#f0a33a` amber | `#99500c` |
| **series 2** | `#5eb8c9` cool cyan | `#0f6e7a` |
| **series 3** (if needed) | `#c98bb8` soft mauve | `#7a3d68` |

- Hue contrast across series; never two near-identical ambers.
- Gaps in series: leave gaps; say so in the caption.
- Monospace labels; no chartjunk; prefer SVG; honest axes.

## Clean up after yourself

Emit the finished artifact (image/svg/gif + data.csv + caption.md), then remove scratch frames
and temp files. The pipeline copies the finished artifact out; this workspace is transient.

If a request is ungrounded, unsafe, oversized, or would require forbidden actions:
**do not improvise — return a `failed`/`skipped` result with a plain reason.** Faithful and bounded
beats clever.
