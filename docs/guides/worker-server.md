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
| `ohmega-menu` | daily 05:00 | newsroom menu (`run --to menu`) | **paid** |
| `ohmega-daily-1` | daily 05:30 | geopolitics daily, part 1 (Europe/Asia morning) | **paid** |
| `ohmega-daily-2` | daily 17:30 | geopolitics daily, part 2 (Americas), appended to the same report | **paid** |
| `ohmega-watchdog` | every 2 min | kills paid runs over their time/spend limits | free |
| SearXNG (Docker) | always | our own metasearch on 127.0.0.1:8080 | free |

### The three paid timers (operator-authorised, unattended)

Times are in-repo flags: the editions in `intel/flags.py` (`EDITIONS`), the menu in `ops/flags.py` (`MENU_UTC`);
change one and re-run `infra/server/install_schedules.sh`. Each unit runs `jobs.sh <job>` → `newsroom schedule run
<job>` (`ops/schedule.py`), under the same job lock as everything else, so paid jobs never overlap (the menu, then
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
never both write and both publish. The private `algent-data` archive (nightly + after runs) is the recovery copy;
Supabase (next step) becomes the working database.

## Access it holds

- Two GitHub deploy keys, one per repo: `Algent` (write while `SITE_PUBLISH_VIA = "git"`: publish to `site-live`;
  **after the cut-over to `"db"` (`docs/architecture/published-content.md`) it can become read-only**: a publish is
  then database rows plus Storage uploads and never pushes; keep read access for `git pull`) and `algent-data`
  (write: backups). Revoke or downgrade under each repo → Settings → Deploy keys.
- In db mode the worker env also needs `DATABASE_URL`, `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` (see
  `docs/credentials.md`). The `.site-live/` directory stays as a local staging area; no git runs against it.
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

**Transport.** Nothing per-object goes to Postgres. Every 60 s the service writes compact JSON to the public Storage bucket
`published-assets` under `live/` via `publishing/asset_store` (cache header `public, max-age=30` so a CDN can answer repeat fetches, unchanged
files skipped by content hash, uploads in parallel; content types `application/json` and `application/gzip` only, bucket migration `008`).
The vessel and aircraft boards go out as (`live/tiles.py`, constants in `live/flags.py`):

| Object | What | Size (60,000 ships + 15,000 aircraft, synthetic clustered data) |
|---|---|---|
| `density.json.gz` | world grid, 2 degree cells, counts per class, both layers | ~27 KB |
| `tiles/index.json.gz` | non-empty 10 degree tiles per layer, each `[objects, etag]` | ~5 KB |
| `tiles/v/<tile>.json.gz`, `tiles/a/<tile>.json.gz` | the object rows of one tile (same row layout as the old documents); no timestamp inside, so an unchanged tile keeps its etag and is not re-uploaded | median 0.5 KB, densest 118 KB, ~490 files |
| `summary.json` | headlines, per-layer freshness, live chokepoint counts | a few KB |
| `vessels.json.gz`, `aircraft.json.gz` | the OLD full documents | 1.43 MB and 0.29 MB |

Every 5 min `coverage.json.gz` and the trail shards `tracks/v0..v15`, `tracks/a0..a15` (an object lives in shard `id mod n`), fetched only when
a trail is asked for. Tiles are uploaded before the index, so a client never sees an index naming tiles that are not there yet; a tile that
empties is simply dropped from the index (its old object stays in the bucket, unreferenced). The site inflates `.json.gz` in the browser
(`DecompressionStream`; `fetchSnapshot` in `lib/live-shared.ts`). The timer runner publishes `fires.json`, `energy.json` and `summary.json`. With
no Supabase credentials the uploads are a no-op. Code: `live/snapshots.py`, `live/tiles.py`, `live/stream.py`.

**Deploy order and the old documents.** `flags.PUBLISH_FULL_SNAPSHOT = True` keeps writing `vessels` and `aircraft` so the previously deployed
site (which only reads those) keeps working. The new site reads `density` + `tiles/` and falls back to the full documents when `density`
is missing. After the new site is live, set the flag to `False` and delete the two objects from the bucket; the stream service then uploads
only density, tiles, summary (and, every 5 min, coverage and trails).

**Egress math (Supabase free plan: about 5 GB a month).** Per open, visible tab, per minute, bodies only (conditional requests on unchanged
documents are answered 304 without a body; a CDN hit costs the bucket nothing):

| View | Old | New |
|---|---|---|
| world / idle (nothing zoomed) | 1.2-1.7 MB (full vessels + aircraft) | density 27 KB + summary ~5 KB = ~32 KB |
| zoomed to a region (zoom 5+) | the same 1.2-1.7 MB | ~32 KB + index 5 KB + the tiles under the view whose etag changed; 2-4 tiles, typically 5-100 KB, worst case (Rotterdam / Singapore corner of a tile) ~150-250 KB |
| hidden tab or map off screen | 0 (visible tabs only) | 0 |

At 32 KB a minute one tab-hour is ~2 MB, so 5 GB covers ~2,500 tab-hours a month at the world view; the old layout covered ~60. Fires and
coverage add ~1-5 KB a minute averaged. Knobs if the bucket still runs hot: `flags.TILE_DEG` (smaller tiles = fewer wasted rows per view but more
files per cycle), `flags.DENSITY_DEG`, `SNAPSHOT_SECONDS`, and the CDN window `SNAPSHOT_CACHE`.

**What the site does with them.** The map (`sites/ohmega-monster/components/live/`) shows ships and aircraft as density far out, dots at
region zoom (zoom 5, when it first fetches the tiles under the view) and small heading-oriented icons past zoom 6.5, dead-reckoned between
snapshots (paused when the tab is hidden, the map is off screen or the user prefers reduced motion). Far out only class filters apply (the grid
holds counts per class); speed, notable, flag and name search work on the objects loaded for the view (`components/live/useLiveFeed.ts`), with layer/sublayer toggles (persisted in localStorage), filters (underway/stopped,
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
`newsroom live schedule`; the stream service restarts always.

Where it goes: numeric results are `live_*` instrument series (completed UTC days only; the day being counted sits in
`live_store/running_*.json`, so a half-counted today never reads as a collapse), which flow through the numbers, freshness
and moves machinery to the section writers; ship counts carry the `chokepoint` tag so a theater's numbers panel shows them
beside IMF PortWatch. Events are snapshots in `live_store/events/<feed>.json` that sensing turns into a `LIVE EVENTS` block for theaters
whose countries they touch. With `DATABASE_URL` set the collectors also upsert `live_events` / `live_stats` (migration `007_live.sql`,
anon SELECT only). Commands: `newsroom live run|ais|status|schedule|publish`.

Honest limits: ADS-B and AIS only show what volunteer receivers hear and what transmits (terrestrial AIS misses open ocean); counts are floors and comparable
with themselves over time; the civil aircraft picture is a sample of busy airspace. A fire hotspot is heat, not proof of a strike. An internet outage does not say why.
