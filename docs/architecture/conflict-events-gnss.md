# Attack log and GPS interference

Two forward-captured intelligence pipes for the geopolitics desk (migration `014_conflict_gnss.sql`). Code: `backend/algent_backend/conflict/` and `backend/algent_backend/gnss/`; CLI: `newsroom conflict ...`, `newsroom gnss ...`; timers in `infra/server/install_schedules.sh`; doctor checks `conflict` and `gnss`; site: `/intel/attacks`, `/intel/gnss`, `/api/v1/attacks`, `/api/v1/gnss`, MCP `get_attack_events` and `get_gnss_interference`, HUD panels "Attack log" and "GPS interference", and an "Interference" layer on the globe.

Pattern (same as sanctions): contracts -> append-only store -> publish -> timer -> CLI -> doctor freshness. Nothing here is back-filled: both pipes count from the day they were switched on.

## Provenance is data

Every published row carries `basis`, `coverage_note`, and where a baseline exists `baseline_since`; the API repeats them in `data.provenance`, and the site shows them in an info hover next to any figure (`components/conflict/Provenance.tsx`, `lib/conflict-shared.ts: provenanceText`).

| `basis` | Meaning | Example |
|---|---|---|
| `official` | a publishing organisation's own report | ReliefWeb (UN OCHA) reports |
| `third_party` | another project's coding or map | GDELT, ACLED, UCDP, GPSJam |
| `our_count` | something Ohmega counted itself | the attack-log totals (a minimum: no source sees every attack) |
| `our_estimate` | something Ohmega derived | GNSS interference zones from ADS-B (a minimum: volunteer receivers, our sample points) |

`baseline_since` is the first day collection began; a count or a learned normal is meaningless without it, so it is always shown.

## Attack / conflict event log (`conflict/`)

One normalised event (`contracts.ConflictEvent`): date, lat/lon (null for country-level reports), place, ISO2 country, the two parties, kind (`bombing`, `airstrike`, `armed_clash`, `assault`, `mass_violence`, `report`), fatalities (null unless the source states them), reports behind it, source urls, `coding` (`machine`, `curated`, `report`), `confidence`, `basis`, `coverage_note`, and `assets` (geoledger assets within 5 km).

| Source | Access | Notes |
|---|---|---|
| GDELT 2.0 events | keyless, every 15 min (`gdeltv2/<stamp>.export.CSV.zip`, ~60 KB) | CAMEO root codes 18, 19, 20 only; geocode must be city or ADM1; at least 2 articles; rows of one file describing the same thing merge; at most 250 per file; FIPS country codes mapped to ISO2 (`fips.py`). Machine-coded: duplicates, misplaces and misreads; never has casualties. Cursor-based catch-up (up to 12 files). |
| ReliefWeb API v2 | **keyed in practice**: `appname` must be approved (HTTP 403 otherwise). Env `ALGENT_RELIEFWEB_APPNAME`, request at https://apidoc.reliefweb.int/parameters#appname | Reports, not events: one `report` row each, country level. Hourly. |
| ACLED | **keyed**: `ALGENT_ACLED_EMAIL`, `ALGENT_ACLED_PASSWORD` (register at https://acleddata.com/register/) | OAuth password grant, then `/api/acled/read`. Best source: curated, fatalities. Daily. Built from the published schema, not yet exercised against the live service. |
| UCDP GED candidate events | **keyed**: `ALGENT_UCDP_TOKEN` (request at https://ucdp.uu.se/apidocs/) | Latest `YY.0.M` candidate version that answers. Daily. Same caveat as ACLED. |

A keyed source with no key reports `needs-key` (status file, collector report) and is not an error: the doctor does not warn about it. Add the key to the server's `~/algent.env` and the next run picks it up.

Dedupe: an event is the same one if it has the same key (kind, parties, place) within `DEDUPE_DAYS` (2) of its date. Store: `conflict_store/events/<date>.jsonl` shards (a 15-minute run reads only nearby shards), `cursor.json`, `status.json`, `since.json`, `published.json` (per shard lines consumed and rows sent). The site database receives at most `PUBLISH_PER_DAY` (400) most-reported events a day; the local record keeps all. About 1 MB a day locally.

Joined to the geoledger by a plain spatial join (`assets.py`, latitude-banded index, loaded once per process). A GDELT dot is not evidence that an asset was struck, so the join never writes a ledger status event; the event row says "near".

Feeds the daily: `sensing._conflict_blocks` adds an `OHMEGA CONFLICT LOG` block per theater (countries the theater stands behind) and the world sweep's strongest events (`conflict/desk.py`), cited as "Ohmega analysis of reported events", with the minimum/machine-coded caveats in the block header. Feeds retrieval as document kind `conflict:<id>` (single-source machine-coded rows are left out) and `gnss:<id>`.

## GPS jamming / GNSS interference (`gnss/`)

Signal: ADS-B position messages carry NACp (and NIC). Under jamming the aircraft's receiver degrades and reports poor accuracy. adsb.lol (keyless) already feeds the live map; `collect.py` queries its `/v2/point/{lat}/{lon}/250` for 23 interference regions and 4 control areas (`flags.PROBES`) each hour, keeps only airborne, ADS-B-positioned, version-2 aircraft (MLAT positions always have NIC 0), counts an aircraft once where circles overlap, and tallies per one-degree cell: observations and those with NACp below 7.

Zones (`zones.py`): a day-cell needs 12 observations, at least 3 degraded and a degraded share of 2% or more. Severity by share: low under 10%, medium to 30%, high above. **Flag against the cell's own history** using live memory's robust statistics (`live/memory/robust.py`, `Z_ENTER`): `new` when the cell was observed on at least 3 earlier days, none elevated, and now reaches 5%; `intensifying` when it was already elevated and today is a robust outlier of its own history. No flags until 7 closed days of history exist; every zone says `baseline_since`.

GPSJam cross-check (`gpsjam.py`): `https://gpsjam.org/data/<date>-h3_4.csv` (keyless, ~190 KB, H3 resolution 4), streamed, the day after. Cell centres are decoded by `h3.py`, a pure-Python port of the H3 library's cell-to-lat/lng path with constant tables extracted mechanically from the C source (`h3_tables.py`); pentagon cells are refused rather than guessed; verified against H3's documented example cells and against the real file (the hot cells land on Kaliningrad, the Gulf of Finland, the Caucasus). Our zones get `cross_check`: `agrees` if GPSJam shows 10% or more in the same cell, else `not_in_gpsjam`.

Store: `gnss_store/hours/<date>.jsonl` (counts only, append-only), `days/` (cache of closed days), `zones/<date>.json` (our zones plus GPSJam's cells), `status.json`, `since.json`. Published to `gnss_zones` (upsert; GPSJam rows only from 10%) and as the small `live/gnss.json` document the globe layer reads. The /live map never shows cells; the globe draws zones as soft glows (colour = severity only).

Desk: `OHMEGA GNSS INTERFERENCE` block (`gnss/desk.py`) over a theater's countries or, in the world sweep, the strongest anywhere; our own derivation, cited "Ohmega analysis", states that a zone is a sign and not an attribution.

## Operations

| Timer | Cadence | Job |
|---|---|---|
| `ohmega-conflict` | every 15 min (`*:4/15`) | `newsroom conflict fetch --source gdelt` |
| `ohmega-reliefweb` | hourly | `newsroom conflict fetch --source reliefweb` (needs-key until the appname is set) |
| `ohmega-conflict-daily` | 05:20 UTC | ACLED + UCDP (needs-key until set) |
| `ohmega-gnss` | hourly (`*:12`) | `newsroom gnss run` (ADS-B pass, GPSJam once a day, publish) |

These skip the shared job lock (seconds to ~90 s, own state), so a long daily never delays them. Server load: a GDELT file is ~60 KB; the GNSS pass is 27 adsb.lol requests (~1.5 min, a few MB), streamed into small tallies. Apply migration 014 before deploying the site build. Stores (`conflict_store/`, `gnss_store/`) are gitignored.

Known limits: GDELT geocoding is coarse and its coding is noisy; the ADS-B estimate sees only aircraft that broadcast ADS-B and are heard, so a heavily jammed area with few flights may show nothing and a cell's share swings with traffic mix; neither source says who is responsible. Unsolved on purpose: cross-source dedupe (a GDELT row and an ACLED row for the same strike stay two rows, each labelled with its source).
