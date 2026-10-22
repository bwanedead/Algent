# Satellite watch — fresh imagery of the places that matter, with change flagged

> Code: `backend/algent_backend/satellite/` (`watchlist`, `sources`, `png`, `change`, `observe`, `document`, `run`, `store`, `flags`),
> `cli/newsroom/satellite.py`, the `ohmega-satellite` timer (`infra/server/`), doctor check `satellite`. Site: `/intel/satellite`
> (`app/intel/satellite/`, `components/satellite/`), `lib/satellite*.ts`, the HUD panel `components/hud/panels/SatellitePanel.tsx`,
> `/api/v1/satellite` (`lib/api/ops-satellite.ts`). Tests: `backend/tests/test_satellite.py`.

A pass looks at a dozen places, keeps a before and an after picture of each, and says whether the two differ. **The score is a machine signal that
pixels differ. It never says what changed or why.** It is Ohmega's own computation (`ohmega_derived`) and every number carries its provenance.

## The watch list: nothing hand-listed

`watchlist.build` ranks, from what the desk already tracks:

| Source | Why a place is on the list | Priority |
|---|---|---|
| geoledger assets with a damage statement (`claimed_struck`, `reported_damaged`, `confirmed_damaged`, `destroyed`) in the last 30 days | the strike | sum of weight (1 / 2 / 3: a claim, a report, a confirmation) divided by `1 + age/7 days` |
| assets named by the daily in the last 2 days (ledger events with `via: daily:<date>:<theater>`) | "in the daily's developments", with the theater | `+1.5` |
| maritime chokepoint zones (`maritime/sites.ZONES`, cable proxies excluded: a seabed cable is not visible) | floor of the list | `0.5` |

Only assets placed `exact` or `approximate` count: a city-level centroid is not a place a picture can be taken of. The list keeps the top 60.
**Rotation**: a pass takes at most `MAX_SITES_PER_PASS` (12) sites not looked at within `REVISIT_HOURS` (36), ordered by `priority x (1 + days overdue)`,
so busy places come round every other day and the tail still gets its turn. Sentinel-2 revisits a place every 2 to 5 days; looking more often would repeat the scene.

## Sources (both keyless, verified October 2026)

- **Sentinel-2 L2A** (Copernicus, ESA) through Microsoft **Planetary Computer**: STAC search (`/api/stac/v1/search`, point-intersects, newest first) and the data API
  (`/api/data/v1/item/bbox/<w>,<s>,<e>,<n>/256x256.png`, `assets=B04&B03&B02`, one **fixed** stretch `rescale=0,2400` so two dates are comparable). No raster is
  downloaded: the service renders a 256 px chip (~150 kB). Earth-search (Element84) was not needed. A chip covers a 5 km square (~20 m a pixel); a chokepoint zone
  covers its box up to a 50 km square.
- The same API renders the **scene classification layer (SCL)** for the same bbox (14 kB). Its classes give the chip's OWN cloud, shadow, snow and no-data share:
  the STAC `eo:cloud_cover` is the whole 100 km tile's and says little about one site. Of the newest 5 scenes, the one with the lowest chip cloud wins (ties go to the newer).
- **NASA GIBS** WMS, layer `VIIRS_NOAA20_GapFilled_BRDF_Corrected_DayNightBand_Radiance` (daily, gap-filled, lunar and BRDF corrected, ~4 days behind), 64 px over about
  22 km around the site. The rendered image's brightness is the signal: a brightness index, not calibrated radiance. (`VIIRS_Black_Marble` and the ENCC layer returned blank for the window tested.)

Everything goes through `polite_http` (`get_bytes`, `post_json`: pacing, retries, browser UA).

## Baseline and the pair

- A site with a dated damage statement gets its **baseline from the clearest scene before that day** (searched 60 days back), so its first look is already a before and
  after. Any other site's baseline is its first clear look. The baseline never moves.
- The **latest** is the clearest of the newest scenes in the last 30 days. A scene already seen is a *repeat* (no picture fetched, no new observation). A latest not newer
  than the baseline is `waiting`.
- Per pass per site one line is appended to `records.jsonl` (append-only; never rewritten). `state.json` per site holds the current view; dated chips are kept for the
  baseline and the newest three scenes.

## The change signal (`change.py`, pure Python: zlib PNG decode, no numpy)

1. **Valid pixels**: clear in both chips (SCL not no-data, saturated, shadow, cloud, cirrus, snow; not transparent). Under `MIN_VALID_SHARE` (60%) of the ground clear: **inconclusive**. Cloud is not change.
2. **Per-band normalisation**: each band's median over valid pixels is removed in each chip (the season's and the sun's overall brightness shift).
3. **Score**: mean absolute difference of the normalised bands over valid pixels, 0..1 (grey level / 255).
4. **Changed-pixel fraction**: share of valid pixels whose own difference is above `median + Z_ENTER x 1.4826 x MAD` of the pair's pixel differences. The cut is the pair's own (and the repo's
   shared `Z_ENTER` 3.5); no brightness constant. It is relative: even an unchanged pair shows a few percent, so read it with the score and the site's history.
5. **The verdict** is the score against **this site's own earlier scores** (modified z, median and MAD; one grey level the floor of sigma, since the data is 8-bit):
   `changed` when z >= `Z_ENTER`, else `steady`. With fewer than `MIN_OBS` (5) earlier looks (distinct scenes against the same baseline) the label is **`learning`** and nothing is flagged.
   A single strike site's first pair is therefore shown, with its score, but not called changed; this is deliberate.
6. **Night lights**: the window's mean brightness against the site's own earlier nights; `dimmer` (z <= -3.5, a possible blackout), `brighter`, `steady` or `learning`. Zones (open sea) get none.

## Provenance on every number

Each judgement (`change`, `night`) is published with `basis: "our_computation"`, `method_note` (how it was made), `baseline_since` (the date our own history for the site starts; null on a first look)
and `n_obs` (earlier looks it rests on). The site turns them into the info hover (`provText`): "Our history for this site starts 2026-10-20; 0 earlier looks. That is too few looks to say what is normal for it."
Chip cloud, no-data and scene dates are source facts about the picture (Copernicus scene ids, dates, the provider's tile cloud) and are labelled as such by the scene block.

## Publish and read

`run.publish` uploads the dated chips (`satellite/<site>/<date>-<hash>.png`, immutable cache; through `publishing/asset_store`, manifest-hashed) **before** the document
(`live/satellite.json` through `live/snapshots.publish`), so a page never names an image that is not there; a failed chip upload holds the document back. No migration, no table: the
same public `published-assets` bucket as every live product (docs/architecture/published-content.md).

- `/intel/satellite`: before / after slider per place (the later picture revealed from the left), score, changed pixels, clear ground, cloud now and before, night light, why it is
  watched, links to the place, country and theater pages, credit (Copernicus Sentinel data, processed by Ohmega; NASA VIIRS). Flagged places first.
- HUD panel "Satellite watch": the most changed places, one line each, off the default board (Panels menu).
- `/api/v1/satellite` (`label`, `kind`, `country` filters): the same sites with chip URLs and the provenance fields.
- Directory door "Satellite" under Data and tools, and the sitemap.
- Timer `ohmega-satellite` daily 03:20 UTC (`newsroom satellite run`), free; `newsroom doctor` warns past 48 h.

## Limits

- 12 sites per pass and a 36 h revisit: a 60-place list comes round in about 5 days. Raise `MAX_SITES_PER_PASS` only after timing a pass on the server (a first pass of 3 sites took ~45 s).
- Sentinel-2 is optical: cloud, smoke and haze hide a site for weeks; the chip cloud share is measured, not guessed, and a hidden site stays `inconclusive`.
- A 20 m pixel resolves a tank farm or a plant, not a transformer; a score cannot tell a strike from a harvest, a crane, a flood or a different sun angle. Use it to look, not to conclude.
- A place's coordinates are as good as the ledger's (`approximate` may be a kilometre off the target).
- Night lights are 4 days behind and a rendered index; a dimmer window can be moonlight, smoke or fewer lit roads. Only assets get night lights.
- No history yet means no flags: a site needs 5 distinct scenes against its baseline (a couple of weeks) before it can be called changed. This is the honest price of not hard-coding a threshold.
- Storage: ~150 kB a chip, about a dozen new scenes a day at most, in the shared bucket.

## Left

- Sentinel-1 radar (cloud-proof, but needs real raster processing), Landsat for a longer record, a real archive search by date for a strike claim made weeks ago.
- A wider window for large sites (a refinery complex over 5 km) and an object-level change map.
- Linking a flagged site into the daily's context automatically (the document already carries the theater id).
