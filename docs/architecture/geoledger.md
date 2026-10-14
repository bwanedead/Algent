# The geospatial asset ledger: places, and who said what about them

> Code: `backend/algent_backend/geoledger/`, `cli/newsroom/geo.py`, migration `009_geoledger.sql`; site: `lib/geoledger*.ts`,
> `components/map/assetLayers.ts`, `components/AssetStatusLog.tsx`, `lib/api/ops-assets.ts`.

## Why it exists

The desk collapses enumerated, entity-level facts into prose. "Strikes on six power plants" enters a daily as a
paragraph; nothing places the plants on a map, tracks what became of them, or answers "what has been hit, what is left,
what exists". The fix is the theme, not the instance: a persistent, geolocated layer of **named things** (assets), and
**dated statements about their state** (status events), extracted from text we already hold, drawn on the theater maps,
and served to agents.

Two rules shape it (the corpus is the asset; keep claims and confirmed things distinct):

- **A status is always somebody's word.** Every event has a required `claimant` ("Russian MoD", "Ukrenergo", "Ohmega
  analysis"). `claimed_struck` is a party's claim and stays that until someone else reports or confirms damage; the map,
  the log and the API keep the three apart.
- **Nothing is overwritten.** Assets are appended as revisions (last wins on read); events are appended once (a
  deterministic id makes the same claim, found again, a no-op). The latest status is derived.

## Model

`Asset`: stable id (`wri-<id>`, `osm-<n|w|r><id>`, or `og-<iso>-<type>-<slug>` for places we mint), name + aliases, `type`
(`power_plant | substation | refinery | fuel_depot | port | bridge | airbase | military_base | dam | rail_hub | vessel |
entity | other`), country (ISO alpha-2), lat/lon (optional: a vessel or an entity has no place), `precision`
(`exact | approximate | city_level | unplaced`), `attrs` (capacity_mw, fuel, owner, year...), `source`, `licence`,
`provenance` (`aggregated` from open data, `ohmega_derived` for places and positions we found ourselves).

`StatusEvent`: asset id, day (+ optional hour), `status` (`operational | claimed_struck | reported_damaged |
confirmed_damaged | destroyed | restored | unknown`, plus `seized | designated` for vessels and entities), `claimant`,
`confidence` (`low|medium|high`: how sure we are the TEXT says this), `sources[]` (URLs), `provenance`, `observed_at`
(when recorded), a short `note` (the words it rests on), and `via` (how it got here: `daily:<date>:<theater>`,
`profile:<id>`, `cli`...). The latest event (newest day, then the more advanced status) is the asset's current status.

Store: `geoledger_store/` (override `ALGENT_GEOLEDGER_STORE`, gitignored): `assets.jsonl`, `events.jsonl`,
`extracted.jsonl` (fingerprints of texts already read), `published.json` (watermark), `cache/overpass/`.

## Seeding from open data (`newsroom geo seed`)

| Source | Licence | What | How |
|---|---|---|---|
| WRI Global Power Plant Database v1.3 | CC BY 4.0 | ~35,000 power plants worldwide: name, country, capacity (MW), fuel, owner, year, coordinates | one zip from the WRI data portal, or `--file` (csv or zip); positions kept `approximate` |
| OpenStreetMap via Overpass | ODbL 1.0 (© OpenStreetMap contributors) | named power plants, substations of 200 kV and up, refineries, fuel depots, ports, military airfields and bases, dams | per theater box (`--theater ukraine|russia-west|middle-east` or `--bbox W,S,E,N`), one query per (box, kind), cached 7 days, 6 s apart, identifying User-Agent, one retry on a busy server |

An OSM power plant that is already a WRI plant (same name, within 4 km) enriches that asset (alias, OSM id) instead of
duplicating it. Attribution is carried on every asset (`source`, `licence`) and printed under the map.

## Extraction: enumerated events out of stored text (`extract.py`, `ingest.py`)

A `Material` is a label plus citable `Item`s (a daily development, a research claim, a statement, a slice of a library
article), each with its own source URLs and date (`materials.py` reshapes stored texts; no new research, no fetching).

- **One structured call per material batch** (about 9,000 characters; a daily section is one call). House model, low
  effort (`ask.extraction_spec`). The wire schema is flat (no `oneOf`/`anyOf`: the house provider rejects them).
- **The model reads and judges; the harness checks.** A candidate survives only if it cites items of the material, its
  `name_as_written` appears in them, they carry a source URL (sources are the items' URLs, never the model's), its date is
  plausible (else the item's own day), its claimant is traceable to the text or the carrying outlet (else it is recorded as
  "reported via <outlet>"), and any coordinates agree with the country named (checked against the Natural Earth basemap).
- **Doctrine** (the prompt) teaches claim versus confirmation by speaker, not tone: a party saying it struck is
  `claimed_struck`; owners, authorities, media report damage; operators, neutral authorities or imagery confirm. Two sources
  that differ are two events.
- **Matching** (`match.py`): names fold to content words (Cyrillic transliterated; y/i, kh/h, doubled letters, adjectival
  -ska endings; generic words like "power plant", "TPP", "CHP" carry the type, not the identity) and compare by similarity.
  Guards: a unit number must agree (CHP-5 is not CHP-6), type and country must be compatible, and two equally good assets
  resolve to nothing. No match mints an asset (`ohmega_derived`, position `approximate` only if the model placed it and the
  country agrees, else `unplaced`, which still lists in the log).
- **Never fails the day.** The daily step (`ingest.attach`, after the visuals, in `produce_daily` and the later editions)
  catches everything; a failed call is reported in `geoledger_run` on the record and retried by the next run (a text is
  marked read only after a successful call). Output on the section: `asset_events[]`. Switch: `geoledger/flags.py ENABLED`.
- **Backfill** (`newsroom geo extract --days 30 [--kinds daily profiles statements library] [--dry-run]`): the same ingest
  over saved dailies, research profiles, the statements ledger and library articles. Library articles pass a free gate
  first (a facility word AND an act word) that only decides whether to spend. Each text is read at most once ever.

**Cost.** A daily is one call per section: roughly 1.1k tokens of instructions plus 1-3k of section text in, a few hundred
out; with 3-6 sections that is about 10-20k input and 1-3k output tokens a day at low effort, fractions of a cent to a few
cents depending on the house model. The 30-day backfill is the same per daily section plus the gated library and profile
texts; `--dry-run` prints the exact number of materials and calls before any spend.

## Display

- **Infrastructure layer** (`GeoMap.tsx`, `assetLayers.ts`, `mapLayers.ts` kind `assets`): places in the map frame as small
  discs wearing their type's letter (P power plant, S substation, R refinery, F fuel depot, H port, B bridge, A airbase, M base,
  D dam, T rail hub), coloured by the latest status: light orange claimed struck, red damage reported, deep red confirmed or
  destroyed, green restored, blue seized or designated, grey nothing on record. A dynamic status fades over 30 days
  (`FADE_DAYS`, floor 35%); a place that merely exists never fades. A chip with a key toggles it (remembered per browser);
  tapping a place opens its card (type, capacity, latest status and claimant, the week's history with sources, licence).
  The server sends the places with a status on record (up to 400) plus the largest of the rest (up to 500); `/live` is unchanged.
- **Strike & status log** (`AssetStatusLog.tsx`): an expander under each theater with the week's events (ending on the
  report's day) at the places on its map, newest first, each line saying who said it. Without a database it falls back to
  the section's own `asset_events`. An archived report shows today's status colours (the ledger holds current state).

## Publishing and agents

Migration `009_geoledger.sql`: `geo_assets` (with the latest status denormalised: `status`, `status_on`, `status_by`,
`events`) and `geo_asset_events` (append-only; inserted once), RLS on, anon SELECT only (insert/update/delete revoked).
`newsroom geo publish` (and the daily step) send only what is new since a watermark; a no-op without `DATABASE_URL`.

- REST: `GET /api/v1/assets?bbox=&type=&country=&status=&has_events=` (at least one filter) and `GET /api/v1/assets/{id}`
  (full history). MCP tool `get_assets` (same filters; `id` for history).
- Write path for agents: `newsroom geo add-event ASSET_ID --status S --claimant WHO --date D --source URL [--confidence C]
  [--note T]`, or `geoledger.ingest.add_event(ledger, ...)`: refused without a valid asset, status, claimant, day and an
  http(s) source. `newsroom geo find NAME` shows what a name would match; `newsroom geo show ASSET_ID` its history.

## Known limits

- WRI coordinates are the database's; OSM coordinates can be a polygon's centre. Both stay `approximate`.
- A model-placed asset's position is memory, checked only against the country it names; it is labelled
  `ohmega_derived` and the card says so.
- Matching refuses ties instead of guessing, so an ambiguous plant becomes a new unplaced asset (a duplicate is cheaper than a
  wrong merge); `newsroom geo find` is the way to inspect and `add-event` the way to attach by hand.
- The ledger holds a status from the day it was said; nothing infers that a place is repaired.
