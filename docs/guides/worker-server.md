# The worker server — what runs where, and how to drive it

The laptop is for development; the worker server runs things around the clock. Code flows laptop → GitHub →
server (the server pulls; deploy-on-push every 5 minutes). Everything about the server is in `infra/server/`,
so it can be rebuilt from scratch instead of repaired by hand.

## The machine

- DigitalOcean droplet `ohmega-server`, Toronto (TOR1), Ubuntu 24.04, 2 vCPU / 4 GB / 80 GB, $24/month.
- Address `146.190.243.152`. Log in as `ohmega` with the automation key: `ssh -i ~/.ssh/ohmega_ops ohmega@146.190.243.152`
  (root login and passwords are off; the operator's personal key also works).
- Firewall: SSH only (22). SearXNG and everything else listen on 127.0.0.1. (Cloud Claude sandboxes cannot SSH in:
  their proxy only passes HTTPS, even on 443, which was tested and reverted on 2026-10-10.)

## What it runs

| Unit | When (UTC) | What | Cost |
|---|---|---|---|
| `ohmega-update` | every 5 min | pull `organic-dev`, reinstall deps if `requirements.txt` changed | free |
| `ohmega-library` | every 4 h | source-library crawl (150 pages) | free |
| `ohmega-instruments` | every 6 h | public data series | free |
| `ohmega-statements` | every 6 h | official statement transcripts (collection only) | free |
| `ohmega-backup` | daily 06:15 | stores → private `algent-data` archive | free |
| `ohmega-db-prune` | daily 03:40 | retention windows on the growing Postgres tables + `VACUUM` (`newsroom db prune --apply`; a no-op while the Postgres flag is off) | free |
| `ohmega-maritime-rollup` | daily 04:05 | daily per-zone ship summaries + retention of the raw maritime event log (`newsroom maritime rollup --apply`) | free |
| `ohmega-backup-snapshot` | daily 06:40 | tar.gz of every irreplaceable store -> the private R2 bucket, 14 daily / 8 weekly / 12 monthly (`newsroom backup snapshot`) | free |
| `ohmega-backup-drill` | monthly, day 1, 07:30 | restore the latest snapshot to a temp dir and verify counts + hashes; ok/FAIL to `~/ops-log.md` (`newsroom backup restore-drill`) | free |
| `ohmega-envelope` | daily 07:10 | one-line operating-envelope summary to `~/ops-log.md` (`newsroom envelope --log`) | free |
| `ohmega-housekeeping` | daily 03:55 | expire the page-fetch cache and per-job run logs older than 30 days (`newsroom products housekeeping --apply`) | free |
| `ohmega-menu` | daily 05:00 | newsroom menu (`run --to menu`) | **paid** |
| `ohmega-daily-1` | daily 05:30 | geopolitics daily, part 1 (Europe/Asia morning) | **paid** |
| `ohmega-daily-2` | daily 17:30 | geopolitics daily, part 2 (Americas), appended to the same report | **paid** |
| `ohmega-watchdog` | every 2 min | kills paid runs over their time/spend limits | free |
| SearXNG (Docker) | always | our own metasearch on 127.0.0.1:8080 | free |

### Timers come from the product registry (do not edit units by hand)

Every timer, its command, its calendar and its lock behaviour is an entry in `backend/algent_backend/ops/products/registry.py` (docs/architecture/foundation.md §3);
`install_schedules.sh` writes one service+timer per line of `newsroom products timers`, and `jobs.sh <job>` is a one-line router to `newsroom products run <job>`
(which takes the shared job lock unless the job opts out: watchdog, live feeds, flows, satellite). To add a job: add it to its product's `jobs`, push, then run
`install_schedules.sh` once. After a deploy: `newsroom products check --text` (registry rules, stores present, every registered timer installed and enabled, orphan
timers, snapshot coverage, freshness, budgets). `ohmega-housekeeping` (daily 03:55, free) expires the page-fetch cache and per-job run logs older than 30 days
(`newsroom products housekeeping [--apply]`).

### After-hooks, the smoke test and staging (`Job.then`)

A job may name `then` jobs in the registry; once it exits 0 they run as jobs of their own (own lock and gates, after the parent's lock is released), and a failing hook
never changes the parent's result. The dailies and `markets-daily` end with `views-fast` (Home, the globe HUD and the daily hub reflect the new report within minutes) and
`site-smoke`; `views` ends with `site-smoke`. `site-smoke` (hourly at :17, free, no lock) runs `newsroom site smoke --log` against production: about 60 paced requests (registry pages,
sampled dynamic pages, `/api/v1`, redirects, freshness). It writes `~/ops-log.md` only when a run fails and when it recovers, keeps the last report for the `site` row of `newsroom envelope`
(fail while failing, warn after 3 h without a run), and needs no Node (stdlib Python, so it also runs here). `staging-prune` (daily 05:05) deletes preview data older than 14 days. Deploy routine: `deploy.md`.

```
newsroom site smoke [--base https://<preview>] [--json]       newsroom site deploy-check [--url URL | --ref organic-dev]
newsroom publish stage-from-prod [--dry-run]                  newsroom publish staging-prune [--dry-run]     newsroom publish staging-status
newsroom views build --target staging                         newsroom publish rebuild-all --target staging
```

### The paid timers (operator-authorised, unattended): menu, daily 1, daily 2, markets-daily

Times are in-repo flags: the editions in `intel/flags.py` (`EDITIONS`), the menu in `ops/flags.py` (`MENU_UTC`);
`markets-daily` (the Polymarket paper trader: forecasts, trades, marks; `markets/flags.py` `DAILY_UTC`, 07:30) is the fourth; change one and re-run `infra/server/install_schedules.sh`. Each unit runs `jobs.sh <job>` → `newsroom products run <job>` → `ops/schedule.py` (the kill switch, runner claim and spend halt), under the same job lock as everything else, so paid jobs never overlap (the menu, then
daily 1, simply queue). Before it spends, a job checks, and on any "no" exits 0 having spent nothing and says why:

1. the kill switch (`SCHEDULED_PAID_RUNS` in `ops/flags.py`, or `ALGENT_SCHEDULED_PAID_RUNS=0`);
2. THIS machine holds the runner claim (`newsroom runner status`); an unreachable archive counts as no, unlike the
   interactive guard, which fails open;
3. no spend halt stands for today (`spend_halt.json`; lift with `newsroom watchdog --clear-halt` only when you mean it).

The job then runs the real command as a child, so the watchdog bounds it on its own command line ($15/run, $40/day,
3 h; the limits fit a ~70 min daily and are commented in `ops/flags.py`). A failure is retried ONCE after 30 min, only
when the output shows a transient network/provider fault, never for a code error, an unrecognised failure or a
watchdog kill; research is saved and reused, so nothing is bought twice. Every job ends with one line in
`~/ops-log.md` (who `scheduler`: published/skipped/FAILED, settled spend, link), a record in
`runs_data/scheduler.jsonl`, and its output in the journal and `~/runlogs/<job>-<date>.log`. `newsroom doctor` has a
`schedule` check per paid timer (installed? last outcome?); `newsroom schedule status` prints the same detail.

Part 2 of the daily is an append to the day's one report: it re-reads what is new since part 1, adds sections for
new theaters and nested updates for theaters the morning covered, and never rewrites part 1 (see
`agents/intel/daily_editions.py`). Part 1 also refreshes instruments/statements first; part 2 relies on the
collectors already on timers.

**Pause the paid schedule:** set `SCHEDULED_PAID_RUNS = False` in `backend/algent_backend/ops/flags.py` and push
(deploy-on-push applies it in 5 min; jobs then log "paused" and spend nothing), or stop the timers at once:
`sudo systemctl disable --now ohmega-menu.timer ohmega-daily-1.timer ohmega-daily-2.timer` (`install_schedules.sh`
re-enables them). A missed run is not made up by hand: run `newsroom intel daily --edition 1|2 --research`.

Everything else that spends (articles, ad-hoc research) still runs only when the operator asks, over SSH, e.g.:

```bash
ssh -i ~/.ssh/ohmega_ops ohmega@146.190.243.152 'cd ~/Algent/backend && .venv/bin/python -m algent_backend.cli newsroom intel daily --research'
```

Logs: `journalctl -u ohmega-<job> -n 50`; timers: `systemctl list-timers 'ohmega-*'`.

## Readiness and who runs

- `newsroom doctor` (run on the server over SSH) checks keys by name, database, SearXNG, the free engines, page
  reads, chart harnesses, the publish path, disk/memory and paid quota; it spends nothing. Run it after any
  rebuild or key change.
- The server is not a dependency: `newsroom runner status|claim|release` records which machine runs paid work
  and publishes, and the laptop can take over. Procedure: `docs/guides/runner-handover.md`.
- **The server is the system of record; the site reads published files from Cloudflare R2** (decision 2026-10-22, `docs/architecture/database-budget.md`).
  `newsroom storage status` (and the `object store` line of `newsroom doctor`) is the R2 free-tier guard: month-to-date Class A/B operations and
  stored bytes, projections, warn at 70%, **writes refused at 90%**. `newsroom publish rebuild-all [--dry-run]` republishes everything from the local
  stores; `newsroom maritime store|rollup` shows and compacts the ship data. The Postgres tools (`newsroom db size|prune|diet|vacuum-full`) apply
  only if `database/flags.POSTGRES_PUBLISH` is switched back on. Never let a writer rewrite a big document on a timer without a content-hash skip.
- `newsroom envelope` measures every register row of `docs/architecture/foundation.md` (disk, RAM, journal, each store, R2, backup age, restore drill, feeds, search, spend) as ok/warn/fail against `ops/envelope_flags.py`; `newsroom doctor` embeds the rows it lacks. Accounts and where recovery lives: `accounts.md`.
- `newsroom search-usage` shows how search is doing (who answers, free vs paid, failures).

## Watchdog

`ohmega-watchdog` (timer, every 2 min; `newsroom watchdog`) is the floor against runaway API bills. It needs no agent awake and spends nothing. Each pass finds running paid algent CLI processes (free jobs are ignored) and SIGTERMs, then after 20 s SIGKILLs, any that:

- ran past its wall-clock limit (3 h for `intel daily`, `newsroom run`/`resume` and everything else; the scheduler's own wrapper is a free command and is not timed, its child is),
- spent over $15 on its own, or
- push today's (UTC) total over $40, in which case it kills every paid run and writes `runs_data/spend_halt.json`; the budget gate (`cost.try_reserve`) then refuses all billable work until the UTC day rolls over or you run `newsroom watchdog --clear-halt`.

Limits are commented constants in `backend/algent_backend/ops/flags.py`. Spend comes from per-process heartbeat files (`runs_data/live_spend/`, written by the cost ledger): settled charges only, so it misses the call in flight and anything billed outside the ledger (external harness CLIs); the wall-clock limit covers a process that never reports spend.

See what it did: `tail runs_data/watchdog.jsonl` (one JSON line per pass/kill/halt) or `journalctl -u ohmega-watchdog -n 50`. Rehearse: `newsroom watchdog --dry-run`. `newsroom doctor` warns if no pass was logged in the last 10 min. Disable: `sudo systemctl disable --now ohmega-watchdog.timer` (`install_schedules.sh` re-enables it).

## Source of truth for data

Once runs happen on the server, **its stores are the live ones**; the laptop stops running jobs so the two
never both write and both publish. The recovery copy is the nightly **R2 snapshot** (`newsroom backup snapshot`, private bucket `R2_BACKUP_BUCKET`, restore with
`newsroom backup restore --to DIR`, proven monthly by `restore-drill`); the private `algent-data` mirror (nightly + after runs) is a second path for files
under 10 MB. Both read the one coverage list, `data_backup/sync.py` (pinned by `tests/test_backup_coverage.py`). There is no working database: R2 holds only the
publication, rebuilt at any time with `newsroom publish rebuild-all`.

## Access it holds

- Two GitHub deploy keys, one per repo: `Algent` (write while `SITE_PUBLISH_VIA = "git"`: publish to `site-live`;
  **after the cut-over to `"db"` (`docs/architecture/published-content.md`) it can become read-only**: a publish is
  then database rows plus Storage uploads and never pushes; keep read access for `git pull`) and `algent-data`
  (write: backups). Revoke or downgrade under each repo → Settings → Deploy keys.
- In db mode (objects are the publish) the worker env needs the five `R2_*` names (see `docs/credentials.md`; `DATABASE_URL` / `SUPABASE_*` are
  optional legacy). The `.site-live/` directory stays as a local staging area (and is backed up); no git runs against it.
- Secrets: `~/algent.env` (chmod 600), copied from the laptop by `scp`, linked as `backend/.env`. Key names and
  purposes: `docs/credentials.md` (manifest).
- Still to log in on the server (operator, interactive): the chart harnesses `grok-build` and `codex`.

## Rebuild from nothing

1. Create a droplet (Ubuntu 24.04, ≥4 GB) with the operator's SSH key; add `~/.ssh/ohmega_ops.pub` to it.
2. `infra/server/bootstrap.sh` as root (users, SSH hardening, firewall, swap, Docker, auto-updates).
3. Deploy keys + `~/.ssh/config` host aliases `github-algent` / `github-data` (see this doc's history).
4. `scp` the `.env` to `~/algent.env`; `infra/server/app_setup.sh`; `infra/server/searxng/deploy.sh ohmega@HOST`.
5. Restore the stores: `python -c "from algent_backend.data_backup import sync; print(sync.restore())"`.
6. Basemap data (untracked, so a fresh clone lacks it; without it every daily map silently vanishes): copy
   `analytics_workspace/data/natural_earth/` from a machine that has it, or download from naturalearthdata.com
   `ne_50m_admin_0_countries` (or `ne_110m_`) plus `ne_10m_populated_places_simple`, `ne_50m_rivers_lake_centerlines`,
   `ne_50m_lakes`, `ne_10m_admin_0_disputed_areas` (or `ne_50m_admin_0_breakaway_disputed_areas`) as `.geojson` into that folder.
   `newsroom doctor` warns (`basemap`) when it cannot load.
7. `infra/server/install_schedules.sh`.
8. `newsroom runner claim`, then `newsroom doctor`.

## Live feeds

The server listens continuously to free live data and turns it into our own stats and into the site's /live map (package
`backend/algent_backend/live/`, cadences, budgets and bounds in `live/flags.py`). No model, no spend, so the watchdog ignores `newsroom live`.

| Feed | Source | Key | Runs | Produces |
|---|---|---|---|---|
| `ioda` | IODA (Georgia Tech) country internet outages | none | timer, 15 min | outage events per country |
| `usgs` | USGS earthquakes M4.5+ past day | none | timer, 10 min | quake events |
| `adsb` | adsb.lol military aircraft | none | timer, 15 min | per-region cluster events + `live_mil_*` day-maximum series |
| `firms` | NASA FIRMS VIIRS, WHOLE WORLD, last 24 h | `ALGENT_FIRMS_KEY` (free: https://firms.modaps.eosdis.nasa.gov/api/map_key/) | timer, 3 h | `fires` heat document (0.25 degree cells), NOTABLE-fire events, watched-box events + `live_fire_*` series |
| `ais` / stream | aisstream.io (world box) + adsb.lol sweep | `ALGENT_AISSTREAM_KEY` (free: https://aisstream.io/authenticate) | service `ohmega-ais`, always on | daily gate counts `live_ais_<gate>_transits`; the live vessel and aircraft boards and their snapshots |

**Fires.** The planet is fetched as 8 tiles of 90 degrees, streamed line by line (memory holds only cells). Every detection folds into a
0.25 degree cell (count, strongest MW); a cell is notable when its intensity or count is in the top 0.1% of that day's cells (relative,
not a fixed number), one event per blaze, at most 12. Watched boxes (front lines, refinery belts) keep their `live_fire_*` series. FIRMS
key limit: 5000 transactions per 10 minutes; a run is 8 area requests plus one status check every 3 hours (72 a day), and the run is
skipped if the status endpoint says the key is near its limit.

**Ships and aircraft (the stream service).** `newsroom live ais` runs these sources together, all merged into two bounded boards:

| Source | What | Notes |
|---|---|---|
| aisstream.io | world websocket (`flags.AIS_BOXES`), position + static + long-range (type 27) messages | connects with permessage-deflate (`compress=15`): since September 2026 aisstream drops messages of UNCOMPRESSED connections beyond a per-user bandwidth limit. Terrestrial, volunteer receivers only: the open ocean is genuinely unseen |
| Digitraffic (Fintraffic) | Finnish waters, REST, polled every 60 s (metadata every 15 min) | keyless, CC 4.0 BY |
| Kystverket | Norwegian economic zone + Svalbard, NMEA over TCP `153.44.253.27:5631` | keyless, NLOD licence; decoded by `live/ingest/nmea.py`; excludes small craft. Not reachable from every network: the service records failures in `status.json` and keeps retrying |
| OpenSky Network | the whole world's aircraft, one `/states/all` call | anonymous 900 s cadence, account 120 s (credit math in `flags.py`); keys `ALGENT_OPENSKY_CLIENT_ID/_SECRET` |
| adsb.lol | all military (`/v2/mil`) + 6 civil area queries per minute over `regions.CIVIL_HUBS` (41 hubs, ~7 min sweep) | fills OpenSky's gaps; the only source of military flags |

Boards are bounded: a vessel expires after 30 min and at most `AIS_MAX_VESSELS` (60,000, freshest kept; ~1 KB each, measured) are held;
aircraft expire after their source's ttl and at most `AIRCRAFT_MAX` (25,000) are held. Merges are by MMSI / ICAO address, freshest
position wins, and a military class is never downgraded by a civil sighting. Ships are classed from the AIS ship type (tanker, cargo,
passenger, fishing, military/law enforcement, other); static data arrives only every ~6 min per ship, so the MMSI -> type/name/destination
memory is saved to `live_store/ais_static.json` every 5 min and reloaded at start (14-day keep, 150,000 cap): without it a restart reads
every ship as "other". A short trail (ships up to 24 points one per 5 min; aircraft 16 points one per 3 min) is kept per live object and
dropped when it leaves the board. The ICAO address and registration are never published; callsign and ship name only if broadcast.

**Receiver coverage.** The board also keeps `live_store/ais_coverage.json`: 1-degree cells where any AIS position was heard in the last 24 h,
published as `coverage.json.gz` and drawn as a faint layer, so empty ocean reads as "no receiver" and not "no ships". Honest limits:
aisstream is volunteer terrestrial AIS (about 40 nautical miles from a coast receiver); open ocean needs satellite AIS, which is paid.

**R2 profile (current).** The text below describes the Supabase profile (60 s cycle, tiles, 16+16 trail shards: ~440 000 PUTs a day, 13x R2's free
Class A tier). On R2 (`live/flags.py` `cost_capped()`) the service publishes only `vessels`, `aircraft`, `points`, `summary` every **180 s** and
`coverage` + 4 ship + 4 aircraft trail shards every **900 s** (no tiles, no `density`): ~2 800 objects a day, 8% of the free tier; the site polls
every 180 s and falls back to the full snapshots where tiles are missing. The write budget is in `docs/architecture/database-budget.md`.

**Transport.** Nothing per-object goes to Postgres. Every 60 s (Supabase profile) the service writes compact JSON to the public bucket
under `live/` via `publishing/asset_store` (cache header `public, max-age=30` so a CDN can answer repeat fetches, unchanged
files skipped by content hash, uploads in parallel; content types `application/json` and `application/gzip` only, bucket migration `008`).
The vessel and aircraft boards go out as (`live/points.py`, `live/tiles.py`, constants in `live/flags.py`):

| Object | What | Size (measured on the live 26,700 ships + 7,400 aircraft) |
|---|---|---|
| `points.json.gz` | every ship and aircraft's REAL position rounded to 0.05 degree + class (+ a notable bit), delta-coded; no ids, names or headings; top flags. Feeds the far-out heat glow exactly as the full rows did. Not thinned | 33 KB |
| `density.json.gz` | world grid, 2 degree cells (still written, no longer read: grids are not the far-zoom picture) | 6 KB |
| `tiles/index.json.gz` | non-empty 10 degree tiles per layer, each `[objects, etag]` | 3 KB |
| `tiles/v/<tile>.json.gz`, `tiles/a/<tile>.json.gz` | the object rows of one tile (same row layout as the old documents); no timestamp inside, so an unchanged tile keeps its etag and is not re-uploaded | 252 files, 0.9 MB in all; densest (North Sea / Baltic corner) 215 KB |
| `summary.json` | headlines, per-layer freshness, live chokepoint counts | a few KB |
| `vessels.json.gz`, `aircraft.json.gz` | the OLD full documents | 0.75 MB and 0.19 MB |

Every 5 min `coverage.json.gz` and the trail shards `tracks/v0..v15`, `tracks/a0..a15` (an object lives in shard `id mod n`), fetched only when
a trail is asked for. Tiles are uploaded before the index, so a client never sees an index naming tiles that are not there yet; a tile that
empties is simply dropped from the index (its old object stays in the bucket, unreferenced). The site inflates `.json.gz` in the browser
(`DecompressionStream`; `fetchSnapshot` in `lib/live-shared.ts`). The timer runner publishes `fires.json`, `energy.json` and `summary.json`. With
no Supabase credentials the uploads are a no-op. Code: `live/snapshots.py`, `live/tiles.py`, `live/stream.py`.

**Deploy order and the old documents.** `flags.PUBLISH_FULL_SNAPSHOT = True` keeps writing `vessels` and `aircraft` so the previously deployed
site (which only reads those) keeps working. Deploy the backend first (it adds `points`), then the site: the new site reads `points` far out
and `tiles/` zoomed in, and falls back to the full documents when either is missing or when a filter needs fields the compact forms lack (flag,
name search, speed, notable). After the new site is live and the far-out glow checked against the old, set the flag to `False` and delete the
two objects from the bucket.

**Egress math (Supabase free plan: about 5 GB a month).** Per open, visible tab, per minute, bodies only:

| View | Old | New |
|---|---|---|
| world / idle (below zoom 4) | 0.94 MB (full vessels + aircraft) | points 33 KB + summary ~5 KB = ~38 KB |
| zoomed in (zoom 4+) | the same 0.94 MB | summary + index 3 KB + the tiles under the padded view whose etag changed: sparse regions tens of KB, one dense tile 215 KB, a Europe-wide view at zoom 4 up to ~0.6 MB |
| filter on flag / search / speed / notable | 0.94 MB | 0.94 MB (full snapshots, only while the filter is set) |
| hidden tab or map off screen | 0 | 0 |

Zoomed-in tiles refetch every minute where objects moved (positions and timestamps are in the rows), so the win there is the area, not the
unchanged-tile skip. Knobs if the bucket still runs hot: `flags.TILE_DEG` (smaller tiles = fewer wasted rows per view, more files per cycle),
`SNAPSHOT_SECONDS`, and the CDN window `SNAPSHOT_CACHE`.

### Maritime behaviour (`maritime/`)

The stream service also keeps a bounded per-vessel memory (`maritime_store/`, `ALGENT_MARITIME_STORE`) and runs the behaviour detectors every 5 min; the timer runner publishes `maritime_events` (migration 013, apply before the site build) and links events into the geoledger. Seed OSM ports on the server (`newsroom geo seed --source osm`) so the port exclusion has data. `newsroom maritime status|events|vessel|publish`, doctor check `maritime`. Design and thresholds: `docs/architecture/maritime-behaviour.md`.

### Flows: ship lanes, grain and money (`flows/`)

The stream service also runs the lane tracker every 5 min (aggregates only, in `live_store/flows/`: `tracker.json.gz` per-vessel last place, `days.json` the daily lane and visit counts); the `ohmega-flows` timer (every 15 min, free, outside the job lock) refreshes the weekly UN Comtrade grain and money picture when due, builds the `flows` document and uploads it as `live/flows.json`. After the first deploy run `newsroom flows backfill` once on the server to seed the lanes from the maritime profile book's last 4 days. `newsroom flows status|lanes|trade|backfill|publish`. Design, sources and caveats: `docs/architecture/flows.md`.

### Satellite watch (`satellite/`)

The `ohmega-satellite` timer (daily 03:20 UTC, free, keyless, outside the job lock) runs `newsroom satellite run`: it ranks the watch list from the geoledger, today's developments and the maritime chokepoints, takes the twelve most overdue (`MAX_SITES_PER_PASS`, `REVISIT_HOURS` in `satellite/flags.py`; ~15 s a site, a few minutes a pass), fetches Sentinel-2 chips (Planetary Computer STAC and data API) and VIIRS night lights (NASA GIBS), appends one record per site to `live_store/satellite/records.jsonl` (never rewritten), uploads the dated chips to `published-assets/satellite/` and then the `satellite` document as `live/satellite.json`. Chips are ~150 kB each and only new scenes are uploaded. `newsroom satellite watch|run|status`; `newsroom doctor` warns when the last pass is over 48 h old. Design, sources and limits: `docs/architecture/satellite.md`. After the first deploy: `sudo bash infra/server/install_schedules.sh` to add the timer.

### Markets track record (`markets/`)

The `ohmega-markets` timer (every 4 h) mirrors relevant Polymarket markets read-only, runs the paper pass and publishes `data/track-record.json`; `markets_store/` (`ALGENT_MARKETS_STORE`) holds the append-only record (back it up with the other stores). `newsroom markets forecast` is the paid, day-capped blind-forecast pass and is **run by hand** (no paid timer without the operator's say-so). Doctor check `markets`. Design, scoring math and flags: `docs/architecture/markets-track-record.md`.

### Live memory: baselines and anomalies (`live/memory/`)

What the sensors normally show, and when they do not: Ohmega's own derivation (provenance `ohmega_derived`) from the same feeds, forward-only
(nothing before the service started is invented). Raw detail lives briefly on the server; condensed insight is what leaves it. Every threshold
is in `live/memory/flags.py` with its reason.

| Step | What | Where |
|---|---|---|
| Sample | the stream service reads the vessel and aircraft snapshot documents every 5 min and counts objects per 1-degree cell (the coverage grid's ids), per named area (the chokepoint, aircraft-region and fire-watch boxes of `live/regions.py`) and for the world, by class: ships tanker / cargo / passenger / fishing / military / other, aircraft civil / military / support (tankers and surveillance, inside military), plus where AIS was heard in the last 10 min. FIRMS runs fold the heat document into the same places (`fire.count`, `fire.frp` = the cells' strongest readings summed: an intensity index, since the document keeps one peak per cell), IODA / USGS runs count ongoing outages and the past day's quakes. An hour's value is the MEAN of its samples. Counts only: no id, name or track | `memory/sampler.py`, hooked in `stream.build_docs` and `runner.run` |
| Hours on disk | `live_store/memory/hours/<YYYY-MM-DDTHH>.<source>.json.gz`, one file per hour and source, kept 60 days then deleted | `memory/hours.py` |
| Baselines | per place and class, per hour of the week (168 slots): the last 6 weeks of that slot as 16-bit counts; the normal is the MEDIAN of the slot and its two neighbouring hours, spread = MAD (`1.4826 * MAD`, floored at `0.5 * sqrt(median)` and at 1 object). Fires: one slot, the last 56 observations. A slot with fewer than 3 weeks falls back to trailing days (same hour, any weekday) and is marked LEARNING; with fewer than 9 pooled values the place is not scored. A place never seen in a layer old enough to know has the zero normal. Persisted per layer as `baseline_<layer>.bin.gz` (about 4 MB for 17,000 ship places measured on synthetic data; 34 MB in memory), places idle for 21 days are forgotten | `memory/baseline.py`, `memory/robust.py` |
| Detect | robust z >= 3.5 (6 while learning) opens a run, it goes on while z >= 2 in the same direction, and is PUBLISHED once it has lasted 3 hourly observations (fires: 2 runs). An incident's values do not enter the baseline for the first 72 h | `memory/detect.py` |
| Screen | a "below normal" is dropped when the rest of the place's traffic fell too (a receiver or feed gap, not ships vanishing), the place's AIS coverage (share of its 24 h-covered cells heard) is under half, the normal was under 3 objects, or the whole world layer dipped. Fires are reported only above normal (cloud and satellite passes make fires "fall" for no reason on the ground). Counts of what was screened: `newsroom live memory status` | `memory/detect.py` |
| Publish | `live_anomalies` (migration 011, anon select only; active rows plus 14 days of closed ones), neighbouring flagged cells merged into one event and cells inside a flagged area folded into it, strongest 40. The append-only record is `memory/anomalies/log.jsonl`; the current picture `memory/anomalies/current.json` | `memory/anomalies.py` |
| Daily rollups | a completed UTC day with at least 18 observed hours becomes `live_mem_<gate or region>_<slug>_<ships, tankers, navy, mil_air>` instrument series (the mean number present), published to `live_stats` as kind `presence` | `memory/daily.py`, `instruments/live_series.py` |
| Brain | `OHMEGA LIVE ANOMALIES` evidence block per theater (countries it stands behind, like the grid block) and across the world sweep; each daily section stores a `live_rollup` (what was normal and abnormal in the places we watch there) and appends it to `memory/anomalies/theater_days.jsonl` | `memory/desk.py`, `intel/sensing.py`, `intel/daily.py` |

The tick (`newsroom live memory tick`; also run at the end of every timer run, a no-op until an hour has settled) is the only writer of baselines
and state, serialised by a lock file and resumable from its cursor. Space, measured on a synthetic world hour of 17,550 place-class entries: about
30 KB per hour file, so about 44 MB for the 60 days. The site shows rings on /live (layer "Anomalies", subtle, on by default), an "Unusual right now"
list, "Unusual in this theater" on dailies and dossiers, and serves `/api/v1/anomalies` and the MCP tool `get_live_anomalies`.
Honest limits: the first weeks everything is learning; ship and aircraft counts are what volunteer receivers hear, and the screening is a statistical
proxy for a coverage gap, not a proof of one; thresholds were set from first principles, not tuned on real data yet.

**What the site does with them.** The map (`sites/ohmega-monster/components/live/`) shows ships and aircraft as a soft heat glow far out (fed by
`points`), dots from zoom 4 (when it starts fetching the tiles under the view) and small heading-oriented icons past zoom 6.5, dead-reckoned between
snapshots (paused when the tab is hidden, the map is off screen or the user prefers reduced motion). Class filters work from the points; speed, notable, flag and name
search switch the map to the full snapshots while set (`components/live/useLiveEntities.ts` picks points / tiles / full), with layer/sublayer toggles (persisted in localStorage), filters (underway/stopped,
notable, flag state, search by name/MMSI/callsign), tap-for-trail, "trails for visible" (capped at 160) and a per-chokepoint focus mode.
"Notable" ships: military/law enforcement, gone dark (moving, then silent 15 min while still on the board), tanker stopped inside a
chokepoint lane. Not built: unusual-route and loitering-near-infrastructure detection.

**Energy.** `live/energy.py` builds `energy.json`: EU gas storage (GIE AGSI+, `gas_eu_storage`; first fetch backfills 5 years in pages of
300 days) against the same date in earlier years with the earlier years' range behind it, LNG send-out and fill (GIE ALSI, same key
`ALGENT_AGSI_KEY`, series `lng_eu_sendout` / `lng_eu_full`), and Brent / WTI / TTF / Henry Hub tiles (`flags.ENERGY_TILES`; Yahoo-backed,
delayed, terms unreviewed, shown on the operator's say-so). GIE requires a visible "GIE AGSI" / "GIE ALSI" source credit: the page prints it.

**Headlines.** `live/headlines.py` computes the "What's happening now" strip (3-6 items) from events, daily series and live gate counts:
a count is flagged only when it beats every day in its recent window and sits outside Tukey's fence; no model calls.

A keyed feed without its key reports `needs <KEY> (free registration at <url>)` in `newsroom live status` and `newsroom doctor`
(check `live:<feed>`) and nothing else breaks. Timers are installed by `infra/server/install_schedules.sh` from
`newsroom products timers` (the live cadences come from `live/flags.py` through the registry); the stream service restarts always.

Where it goes: numeric results are `live_*` instrument series (completed UTC days only; the day being counted sits in
`live_store/running_*.json`, so a half-counted today never reads as a collapse), which flow through the numbers, freshness
and moves machinery to the section writers; ship counts carry the `chokepoint` tag so a theater's numbers panel shows them
beside IMF PortWatch. Events are snapshots in `live_store/events/<feed>.json` that sensing turns into a `LIVE EVENTS` block for theaters
whose countries they touch. With `DATABASE_URL` set the collectors also upsert `live_events` / `live_stats` (migration `007_live.sql`,
anon SELECT only). Commands: `newsroom live run|ais|status|schedule|publish`.

Honest limits: ADS-B and AIS only show what volunteer receivers hear and what transmits (terrestrial AIS misses open ocean); counts are floors and comparable
with themselves over time; the civil aircraft picture is a sample of busy airspace. A fire hotspot is heat, not proof of a strike. An internet outage does not say why.

The `ohmega-ai-bench` timer (every 12 h) collects AI benchmark scores (Epoch hub, SWE-bench, LMArena) and publishes `data/ai-benchmarks.json`; `ohmega-ai-discovery` (daily 06:50, needs the local SearXNG) records lab-claimed scores with one capped model call (under $0.10/day; `ALGENT_AI_DISCOVERY=0` stops it). `ai_benchmarks_store/` is in the nightly backup. Doctor check `ai_benchmarks`. The AI daily is a paid job that stays off until `AI_DAILY_SCHEDULED = True` in `intel/flags.py`. See `docs/architecture/ai-desk.md`.
