# Attack log and GPS interference

Two forward-captured intelligence pipes for the geopolitics desk, built on the current architecture (`foundation.md`): the server is the record, R2 is the publication, the product registry owns the stores, jobs, budgets and routes. Code: `backend/algent_backend/conflict/` and `backend/algent_backend/gnss/`; CLI: `newsroom conflict ...`, `newsroom gnss ...`; registry products `conflict` and `gnss` (`ops/products/registry.py`); doctor checks `conflict` and `gnss`; site: `/intel/attacks`, `/intel/gnss` (doors in the Explore hub, Measured), `/api/v1/attacks`, `/api/v1/gnss`, MCP `get_attack_events` and `get_gnss_interference`, HUD panels "Attack log" and "GPS interference", an "Interference" layer on the globe, and blocks in the country and situation views.

Pattern (same as sanctions and satellite): contracts -> store -> documents -> registry timer -> CLI -> doctor freshness. Nothing is back-filled: both pipes count from the day they were switched on. There is no database on any path: the site reads documents.

## Storage discipline

Operator rule: keep only events and derived interference zones. Never raw ADS-B, never a full GDELT dump, never GPSJam's whole file. Everything is stream-parsed and reduced on the way in.

| Store | What is kept | Bound |
|---|---|---|
| `conflict_store` (`ALGENT_CONFLICT_STORE`) | `events/<date>.jsonl`, one normalised event per line (a GDELT file is streamed from a temp zip and reduced to its few violence events); `status.json`, `cursor.json`, `since.json` | machine-coded (GDELT-only) shards are dropped after `KEEP_DAYS_MACHINE` (45) days, other shards after `KEEP_DAYS_OTHER` (365); the folder is capped at `MAX_STORE_MB` (150) by dropping the oldest shard first. `store.prune` runs after every collection pass. A line does not repeat the per-source coverage note (put back on read). |
| `gnss_store` (`ALGENT_GNSS_STORE`) | `hours/<date>.jsonl`: per-cell COUNT tallies of an hourly sample, no aircraft record; `days/<date>.json`: a closed day's summed tally (the baseline reads these); `zones/<date>.json`: our derived zones plus GPSJam's top band only; `status.json`, `since.json` | hour lines are dropped after `HOURS_KEEP_DAYS` (7), once their day sum is saved; GPSJam's cells leave a zone file after `ZONES_FULL_DAYS` (30) (ours stay); everything goes after `KEEP_DAYS` (400). `store.prune` runs after every pass. |

Budgets (registry): `conflict_store` steady 85 MB, warn 120, fail 200 (measured from a live pull on 2026-10-24: 11 GDELT files gave 391 events, 0.22 MB, so about 1.8 MB a day over the 45-day window); `gnss_store` steady 9 MB, warn 40, fail 150 (an hour line is 5 KB; GPSJam's top band is 129 KB a day for the 30 days it is kept); both are estimates until `newsroom envelope --text` has run on the server for a week. `conflict_store` is not backed up (every source is re-fetchable and the machine-coded part is a rolling window by design); `gnss_store` is (its baseline cannot be re-derived: past ADS-B is gone). GPSJam's file is streamed (about 190 KB, 48k rows) and only cells at 10% and above are kept.

## Documents (the contract with the site)

| Document | Contract | Content |
|---|---|---|
| `conflict/recent.json` | `ohmega.conflict.recent/1` | the strongest `RECENT_MAX` (1,200) events of the last 14 days (curated and fatal first, then most reported), `total` / `shown` / `capped` (the count is over everything stored, never the rows carried), `by_day` counts (events, machine, curated) for 30 days, `since`, which sources are live (`sources`), each source's `coverage` note |
| `conflict/country/<ISO>.json` | `ohmega.conflict.country/1` | one country's strongest `COUNTRY_MAX` (120) events of 30 days and its total |
| `gnss/latest.json` | `ohmega.gnss.latest/1` | the newest day: our zones, GPSJam's top band, `baseline_since` / `baseline_days`, the per-source coverage notes, a 28-day history of our zone counts |
| `live/gnss.json` | `ohmega.gnss.overlay/1` | the globe layer: the newest day, one compact dot per zone |

Built from the local store in one streaming pass (`conflict/publish.py`, `gnss/publish.py`), deterministic (an unchanged record hashes the same and costs no request), sent through `publishing/site_data.publish_built` (the local store is the record; a failed upload loses nothing). The registry's `publishes`, `contracts` (`foundation.md` section 6a), `site_routes` and `heartbeat` (`status.json`) say the rest; per-product status files are written by the job runner.

Views (`views/signals.py`): the country view carries `attacks` (the country's strongest events, the 30-day total, which sources are live) and `gnss` (our zones over it, newest day) and two panel counts; the situation view carries `signals` (events and zones over its twelve heaviest-tied states); the HUD view carries the last three days' strongest events and the strongest zones. Each block is `null` when the product has published nothing (never an empty block that reads as "no attacks"). Pages render them in `components/conflict/SignalsSection.tsx` (actor page, situation page).

Corpus (`corpus/sources/conflict.py`, `gnss.py`): per event date one unit; each indexed event becomes an `events` row (kind `conflict_<type>`, place, coordinates, status = how it was coded) plus a document (`conflict_event`) whose body states the source, who coded it, the confidence, the basis and the coverage limit; the country and nearby ledger assets are mentioned (proximity, never a claim of damage); parties are mentioned by name. Machine-coded events of low confidence (a single source barely supports them) stay out of the index. GNSS: per day `gnss.zones` and `gnss.zones.high` (basis `our_derived`) and an event per flagged zone. A shard the store has pruned leaves the index on the next full build (the index mirrors the rolling record).

## Numbers on the site

Every figure is a registered stat (`sites/ohmega-monster/lib/stats/registry.ts`): `attacks_events` (`our_count`), `attacks_machine` (`machine_coded`, GDELT), `attacks_curated` (`official`, ACLED / UCDP), `attacks_countries`, `gnss_zones`, `gnss_high`, `gnss_flagged` (`our_derived`, withheld until a week of history), `gnss_gpsjam` (`official`). Counts of what we only partly see are minimums and render as "≥ n" with the basis, scope and limit in an info hover. Row values (a fatality figure, a report count) are data, not statistics.

## Attack / conflict event log (`conflict/`)

One normalised event (`contracts.ConflictEvent`): date, lat/lon (null for country-level reports), place, ISO2 country, the two parties, kind (`bombing`, `airstrike`, `armed_clash`, `assault`, `mass_violence`, `report`), fatalities (null unless the source states them), reports behind it, source urls, `coding` (`machine`, `curated`, `report`), `confidence`, `basis`, `coverage_note`, and `assets` (geoledger assets within 5 km).

| Source | Access | Notes |
|---|---|---|
| GDELT 2.0 events | keyless, every 15 min (`gdeltv2/<stamp>.export.CSV.zip`, ~60 KB) | CAMEO root codes 18, 19, 20 only; geocode must be city or ADM1; at least 2 articles; rows of one file describing the same thing merge; at most 250 per file; FIPS country codes mapped to ISO2 (`fips.py`). Machine-coded: duplicates, misplaces and misreads; never has casualties. Cursor-based catch-up (up to 12 files). |
| ReliefWeb API v2 | **keyed in practice**: `appname` must be approved (HTTP 403 otherwise). Env `ALGENT_RELIEFWEB_APPNAME`, request at https://apidoc.reliefweb.int/parameters#appname | Reports, not events: one `report` row each, country level. Hourly. |
| ACLED | **keyed**: `ALGENT_ACLED_EMAIL`, `ALGENT_ACLED_PASSWORD` (register at https://acleddata.com/register/) | OAuth password grant, then `/api/acled/read`. Best source: curated, fatalities. Daily. Built from the published schema, not yet exercised against the live service. |
| UCDP GED candidate events | **keyed**: `ALGENT_UCDP_TOKEN` (request at https://ucdp.uu.se/apidocs/) | Latest `YY.0.M` candidate version that answers. Daily. Same caveat as ACLED. |

A keyed source with no key reports `needs-key` (status file, collector report) and is not an error: the doctor does not warn about it; the page lists it as "not collecting yet". Add the key to the server's `~/algent.env` and the next run picks it up.

Dedupe: an event is the same one if it has the same key (kind, parties, place) within `DEDUPE_DAYS` (2) of its date (ids are deterministic, so a re-run or a restored shard repeats nothing). A GDELT row and an ACLED row for the same strike stay two rows, each labelled with its source (cross-source dedupe is unsolved on purpose).

Joined to the geoledger by a plain spatial join (`assets.py`). A GDELT dot is not evidence that an asset was struck, so the join never writes a ledger status event; the event row says "near".

Feeds the daily: `sensing._conflict_blocks` adds an `OHMEGA CONFLICT LOG` block per theater and the world sweep's strongest events (`conflict/desk.py`), cited as "Ohmega analysis of reported events", with the minimum / machine-coded caveats in the block header. Feeds retrieval as document kind `conflict:<id>` (single-source machine-coded rows are left out) and `gnss:<id>`.

## GPS jamming / GNSS interference (`gnss/`)

Signal: ADS-B position messages carry NACp (and NIC). Under jamming the aircraft's receiver degrades and reports poor accuracy. adsb.lol (keyless) already feeds the live map; `collect.py` queries its `/v2/point/{lat}/{lon}/250` for the interference regions and control areas (`flags.PROBES`) each hour, keeps only airborne, ADS-B-positioned, version-2 aircraft (MLAT positions always have NIC 0), counts an aircraft once where circles overlap, and tallies per one-degree cell: observations and those with NACp below 7. Only the tally is stored.

Zones (`zones.py`): a day-cell needs 12 observations, at least 3 degraded and a degraded share of 2% or more. Severity by share: low under 10%, medium to 30%, high above. **Flag against the cell's own history** using live memory's robust statistics (`live/memory/robust.py`, `Z_ENTER`): `new` when the cell was observed on at least 3 earlier days, none elevated, and now reaches 5%; `intensifying` when it was already elevated and today is a robust outlier of its own history. No flags until 7 closed days of history exist; every zone says `baseline_since`.

GPSJam cross-check (`gpsjam.py`): `https://gpsjam.org/data/<date>-h3_4.csv` (keyless, ~190 KB, H3 resolution 4), streamed, the day after. Cell centres are decoded by `h3.py`, a pure-Python port of H3's cell-to-lat/lng path with constant tables extracted mechanically from the C source (`h3_tables.py`); pentagon cells are refused rather than guessed. Our zones get `cross_check`: `agrees` if GPSJam shows 10% or more in the same cell, else `not_in_gpsjam`. Only cells at 10% and above are kept.

Desk: `OHMEGA GNSS INTERFERENCE` block (`gnss/desk.py`) over a theater's countries or, in the world sweep, the strongest anywhere; our own derivation, cited "Ohmega analysis", states that a zone is a sign and not an attribution.

## Operations

| Timer (generated from the registry) | Cadence | Job |
|---|---|---|
| `conflict` | every 15 min (`*:4/15`) | `newsroom conflict fetch --source gdelt` |
| `reliefweb` | hourly (`*:41`) | `newsroom conflict fetch --source reliefweb` (needs-key until the appname is set) |
| `conflict-daily` | 05:20 UTC | ACLED + UCDP (needs-key until set) |
| `gnss` | hourly (`*:12`) | `newsroom gnss run` (ADS-B pass, GPSJam once a day, prune, publish) |

All four skip the shared job lock (seconds to ~90 s, own state), so a long daily never delays them. Server load: a GDELT file is ~60 KB; the GNSS pass is about 27 adsb.lol requests (~1.5 min, a few MB), streamed into small tallies. Install: `git pull` then `sudo bash infra/server/install_schedules.sh` (the timers come from `newsroom products timers`). Useful commands: `newsroom conflict status` / `prune`, `newsroom gnss status`, `newsroom products check`, `newsroom envelope --text` (replace the estimated budgets with the measured sizes).

Known limits: GDELT geocoding is coarse and its coding is noisy; the ADS-B estimate sees only aircraft that broadcast ADS-B and are heard, so a heavily jammed area with few flights may show nothing and a cell's share swings with traffic mix; neither source says who is responsible.
