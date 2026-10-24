# Storage architecture — the server is the record, R2 is the publication, no database on the read path

> Code: `backend/algent_backend/publishing/` (`object_store.py` R2 + SigV4, `object_budget.py` the free-tier guard, `object_docs.py` documents,
> `asset_store.py` the uploader, `site_data.py`, `rebuild.py`), `database/flags.py` (every knob), each domain's `publish.py`
> (`live/`, `maritime/`, `sanctions/`, `lookahead/`, `geoledger/site_docs.py`), `maritime/rollup.py`, `data_backup/sync.py`,
> `sites/ohmega-monster/lib/store.ts` + `lib/data-base.ts`. Related: `published-content.md`, `docs/guides/worker-server.md`, `docs/credentials.md`.
> The sections below "Legacy" are the Postgres mode (database budget, diet, recovery); they apply only if the Postgres flag is switched back on.

## The decision (operator, 2026-10-22)

The free Supabase database (500 MB) filled and went down; the operator will not pay for Pro. So:

```
 worker server (system of record)            Cloudflare R2 (publication)              Vercel (the site)
 ─────────────────────────────────           ─────────────────────────────           ───────────────────────
 file stores: pulse_store, profile_store,    docs/<path>.gz       JSON documents      reads NEXT_PUBLIC_DATA_BASE only:
   geoledger_store, sanctions_store,         docs/_names/<dir>.json.gz  dir indexes     ISR pages fetch docs/…;
   calendar_store, markets_store,            live/…               map snapshots        the browser polls live/…
   maritime_store, intel_store, …            analytics/…, satellite/…  images/chips    and loads images
 publishers build documents from the stores ─► hash-skip ─► PUT (SigV4, stdlib)  ─►  no database, no service key
 nightly mirror ► private algent-data repo     public, free egress
```

* **No live database on the read path.** Everything the site used to read from PostgREST tables is now a published JSON document built from
  the server's local store by the domain that owns it (below). Supabase is not needed; `database/flags.POSTGRES_PUBLISH = False`.
* **The Pulse ledger's primary store is the file store** (`database/flags.PULSE_BACKEND = "files"`). Postgres code stays, off by a flag.
* **Backend switch, one line each:** `database/flags.OBJECT_BACKEND` (`"r2"` default, `"supabase"`), `POSTGRES_PUBLISH`, `PULSE_BACKEND`.
  One-shot env overrides: `ALGENT_OBJECT_BACKEND`, `ALGENT_POSTGRES_PUBLISH=1`, `ALGENT_PULSE_BACKEND=postgres`. Publishing is a no-op until the
  R2 names are set; `ALGENT_DB_PUBLISH=0` still pauses everything.

### What each product publishes (the former tables)

| Was (table) | Published documents (key = `docs/<path>.gz`) | Built from | Size / bound |
|---|---|---|---|
| `live_events` | `live/events.json` (current events of every feed, newest 400) | `live_store/events/*.json` | ~20 KB gz |
| `live_stats` | `live/stats.json` (45 days of chokepoint series + the running day; `presence` means stay server-side) | instruments store + `live_store` | ~60 KB gz |
| `live_anomalies` | `live/anomalies.json` (strongest 200, active first) | `live_store/memory/anomalies/current.json` | ~10 KB gz |
| `maritime_events` | `maritime/live.json` (going + last 48 h, evidence last 4 points, max 400), `maritime/recent.json` (30 days, max 1500, evidence last 12), `maritime/counts.json`, `maritime/vessel/<imo>.json` | `maritime_store/events.json` | live ~100 KB, recent ~1 MB gz |
| `sanctions_events` | `sanctions/recent.json` (180 d, max 3000), `sanctions/country/<ISO>.json` (180 d, max 200) | `sanctions_store` | ~100 KB / ~5 KB |
| `calendar_items` | `calendar/next.json` (active, 14 d back to 180 d ahead) + `calendar/country/<ISO>.json` | `calendar_store` | ~250 KB + ~80 small files, hash-skipped |
| `geo_assets`, `geo_asset_events` | `geo/c/<ISO>.json` (places with a status + the 2000 largest without), `geo/countries.json` (index with bbox), `geo/events-assets.json`, `geo/a/<id>.json` (one place + history; only places with events), `geo/events/<YYYY-MM>.json` | `geoledger_store` | ≤ ~150 KB gz each |
| `geo_grid` | `geo/grid/<ISO>.json` | ledger rollups | ~3 KB each |
| `published_articles` | `articles/index.json` (front matter of all, no bodies), `articles/<slug>.json` | `content/articles/*.md` staging + `publish_held/articles_index.json` | index ~50 KB |
| `published_intel_documents` | unchanged paths: `daily/…`, `theaters/…`, `actors/…`, `briefs/…`, `snapshots/…`, `record.json`, `radar/…`, `data/…` + `_names/<dir>.json` indexes (the site cannot list a bucket) | the desk's staged files | as before |

Not published any more: places with no event outside a country's 2000 largest (the ledger keeps them; the map never drew more than 500 per frame) and
`mmsi`-keyed vessel lookups (the place page asks by IMO). Nothing else is Postgres-only: **no feature needs a database now.**

### Rules the code keeps

1. **Hash-skip every write.** `object_docs` compares a document's canonical-JSON sha256 with a LOCAL manifest (`backend/publish_held/doc_hashes.json`);
   `asset_store` does the same per object (`asset_hashes.json`). An unchanged document costs no request. Moving parts are kept out of the hash:
   maritime rows are replaced only when their signature changes or after `PUBLISH_REFRESH_H`; `updated_at` is "last changed" (`site_data.stamped`).
2. **The server never reads back from the bucket what it holds locally.** Nothing in the publish path calls `get`, `head` or `list` (they exist for
   tooling). Name indexes are rebuilt from the local manifest, never from a bucket listing.
3. **Never LIST in a hot path.** The site reads small published index files (`_names/…`, `articles/index.json`, `geo/countries.json`), not a listing.
4. **Switching backend re-sends everything once** (manifest keys carry the backend id), so `rebuild-all` after a switch is complete by construction.
5. **A server-side GET of a public URL needs a real `User-Agent`** (Cloudflare answers 403 to urllib's default); `object_store.default_call` sets one.

## R2 budget — a hard guard (the account has a card on file)

R2 free tier per month: **10 GB-month storage, 1 M Class A (PUT/COPY/LIST), 10 M Class B (GET/HEAD)**; egress is free. Overage bills.

* **Counter** (`publishing/object_budget.py`): a persistent per-month count of OUR Class A (PUT/LIST/DELETE, DELETE counted although free) and Class B
  calls and of stored bytes, in `backend/publish_held/r2_usage.json` (several processes add their deltas; month rolls over, stored bytes persist).
* **Budgets** (`database/flags.py`): daily allowance = free tier ÷ days in the month; **warn at 70%**, **HARD STOP at 90%** of the monthly free tier;
  a single UTC day may use at most `R2_DAILY_STOP_MULT` (3x) its allowance. Past a limit `R2Store` refuses the call (HTTP 429 to the uploader, a logged
  `REFUSED …` once a minute): the object is reported failed, its hash is not recorded, so it is retried when the budget allows. Parallel workers cannot
  overshoot (check and count are one locked step). Publishers never raise; the live cycle simply skips.
* **`newsroom storage status`** prints month-to-date Class A/B ops, stored bytes, today vs the daily allowance, the projection to month end, and the
  level (exit 1 at the hard stop). **`newsroom doctor`** has an `object store` line: WARN at 70%, **FAIL at the stop**.

### Estimated write volume (Class A) — fits at ~11% of the free tier

| Writer | Objects per cycle | Cycle | Per day |
|---|---|---|---|
| live snapshots: `vessels`, `aircraft`, `points`, `summary` | 4 | 180 s (`live/flags.R2_SNAPSHOT_SECONDS`) | 1 920 |
| trail shards + coverage: 4 ship + 4 aircraft + 1 | 9 | 900 s (`R2_TRACKS_SECONDS`, `R2_TRACK_SHARDS = 4`) | 864 |
| `live/events`, `live/stats` | 2 | each live run (~15 min) | ~190 |
| anomalies / maritime documents / sanctions / calendar | changes only | hourly / 5 min (hash-skip) | ~200 |
| energy (15 min), fires (3 h), flows (15 min), satellite chips + doc | | | ~250 |
| desk documents (2 dailies + dossiers, actors, feeds, name indexes), articles + images | changed only | twice a day | ~200 |
| **Total** | | | **~3.6 k/day = ~110 k/month = 11% of 1 M** (ceiling 40%) |

What was cut to get there: the Supabase profile sent a vessel/aircraft **tile** set (~300 objects) + `density` + `tiles/index` every **60 s** and 16+16 trail
shards every 5 min: ~430 000 PUTs a day, 13 million a month = 13x the free tier. On R2 the tiles are not published (`live/flags.tiles_enabled()`), the
site falls back to the `points` + full snapshots it already supports (R2's free egress affords the larger files), the cycle is 180 s and the site polls
every 180 s. `rebuild-all` costs one PUT per changed document (a few thousand once); `--dry-run` prints the number first.

### Class B (reads) and `r2.dev`

`R2_PUBLIC_BASE` as `https://pub-….r2.dev` is **rate-limited and meant for development**; it also has no cache, so every browser poll and every ISR
fetch is a Class B read. **Production path: a custom domain (e.g. `data.ohmega.monster`, needs the domain's DNS on Cloudflare) on the bucket with a
cache rule**: repeat GETs are then served from Cloudflare's edge and are not billed R2 operations. Both the server (`R2_PUBLIC_BASE`) and the site
(`NEXT_PUBLIC_DATA_BASE`) keep the base URL as a single setting, so the switch is one line in each.

Without the cache, the budget is: ISR reads (worst case, every product requested every window): `live/*` 4 docs × 720 windows + maritime 144 + tables 48 ×
~6 + daily docs ≈ 6-10 k/day; each open `/live` tab polls ~3 objects per 180 s = 1 440/day. 10 M a month = 333 k/day ≈ 230 always-open tabs. The counter
sees only the server's calls; the public reads are in the Cloudflare dashboard (R2 > Metrics).

## Egress — keep Vercel reads lean (the 2026-10 Supabase bill was 15.2 GB against a 5 GB quota)

The cause was ISR pages re-downloading multi-MB documents every 300 s, plus the server reading back. Now:

* **Per-product revalidate**, from each product's real cadence (`lib/store.ts` `TTL`, repeated as literals on each page): live layers 120 s, the live map's
  first paint 180 s, maritime analysis 600 s, articles 900 s, dailies/dossiers/actors/tables 1800 s, track record/benchmarks/sitemap 3600 s.
  A fetched object is cached by Next's data cache for its window, so it is downloaded once per window per region however many pages use it.
* **Split documents so a page fetches only what it renders**: maritime `live` (small) vs `recent` (30 days) vs `counts`; sanctions `recent` vs
  `country/<ISO>`; geo per country / per place / per month; articles `index` vs `<slug>`; live events / stats / anomalies separate; directory `_names`.
* **Compressed at rest and in the cache**: objects are `application/gzip` (no `Content-Encoding`), so Next caches the compressed bytes (its cache
  refuses items over 2 MB; the compressed ones fit) and the site gunzips.
* **The server reads nothing back** from R2.
* Expected read volume per day, upper bound if every product is requested every window: live 4 docs (~250 KB gz) × 720 = ~180 MB; maritime `recent`
  (~1 MB) × 144 = ~145 MB; tables ~200 KB × 48 × 3 = ~30 MB; daily + dossier documents ~300 KB × 48 × ~10 = ~145 MB; articles ~50 KB × 96 = ~5 MB.
  **≈ 0.5 GB/day (≈ 15 GB/month) worst case, a third of that typical**, all from R2 where egress is free. The remaining Vercel-side cost is the
  Fast Origin Transfer of those fetches; if it matters, lengthen `TTL.live` or `TTL.maritime` first.

### ISR "keep the last good page" (Next 14.2)

`lib/store.ts` distinguishes two outcomes. A 404 is "not published" (null: the page says so). Anything else (network error, 5xx, 403, an unparseable
body) **throws** `DataUnavailable`. In Next 14 an ISR regeneration that throws leaves the previously generated page in place and retries on the next
request, whereas a render that returns an empty list would be written as the new page for a whole window; a non-200 `fetch` is also never stored in the data
cache. During `next build` (no previous page exists) a failure degrades to the content files so a bucket blip cannot fail the deploy.

## Ship data: the transition log, daily summaries and retention (`maritime/eventlog.py`, `maritime/rollup.py`)

Only one file in `maritime_store` is unbounded: **`log.jsonl`**, the long record. It used to hold a full event with evidence on every open and state
touch (**measured 1.7 GB in ~6 days: ~250 k lines a day at ~1.9 KB**, 44% `open`, 29% `ended`, 24% `ongoing`, 4% `unresolved`). It now holds **one compact
line per transition and nothing else** (`{id, kind, state, mmsi, imo, name, ship_class, at, lat, lon, area, confidence}`, ~0.2 KB; state `open`, `ended` or
`unresolved`; "ongoing" and full objects are never written). The picture (`events.json`) still carries the full event while it is current.

Why it was ~100 k opens a day (found in code, not guessed): the picture is a bounded cache (`EVENTS_MAX`), and an event that fell out of it was re-found by its
detector on the next 5-minute pass and logged `open` again; the sanctioned detector flips an event between ongoing and ended around a freshness threshold
and logged every flip. Now `maritime/eventlog.Ledger` (`log_ledger.json`) remembers per event id which transitions are written (one `open`, one terminal), and
per vessel + kind when it last opened (`flags.LOG_COOLDOWN_S`: each kind's cooldown is the least time in which a genuinely new event of that kind can appear,
`GAP_MIN_S`, `STS_MIN_S`, `LOITER_MIN_S`; derived from the detectors' own thresholds, not a constant). `store.upsert` also stops re-adding an event whose end is
already on record and no longer cuts going events when the cap bites. Run `newsroom maritime compact-log` (dry run) on the server for the exact before / after
count of opens per kind from the real log.

`LOG_KEEP_DAYS = 7` (`maritime/flags.py`): nothing reads the log back, a week serves "what happened lately", and the day summaries carry the long view.
`profiles.json.gz` (<= 50 000 vessels, 4 days) and `events.json` (30 days, <= 3000 events) are bounded already.

`newsroom maritime rollup [--apply]` (timer `ohmega-maritime-rollup`, 04:05) writes `maritime_store/daily/<YYYY-MM-DD>.json.gz` (a few KB each):

| Block | Content | From |
|---|---|---|
| `zones` | per chokepoint / region: unique ships, by vessel class, ships underway, median speed, samples | profile book (4 days) |
| `events` | opened that day: total, by kind, by area, AIS gaps per area, outcomes; `through` = the last log line it counts | the log |
| `notable` | up to 30 sanctioned / confidence >= 0.8 events, compact | the log |
| `tracks` | up to 12 flagged vessels' evidence points: only from legacy full-event lines; compact lines carry one position each (in `notable`) | the log |

The compaction streams the log (never loads it whole), renames it aside so the stream service keeps appending, rewrites what is kept as compact deduplicated
transitions and appends the recent lines back; it resumes from `log.jsonl.work` after a crash. A day is summarised the night after it ends (complete days), and
`events.through` stops any line being counted twice. **One-shot for the old 1.7 GB file:** `newsroom maritime compact-log` (report), then `--apply`: it converts
the legacy lines (dropping "ongoing" and repeats) and cuts to 7 days; expected result a few MB.

## Backups (the server was the only copy; now R2 snapshots + a small mirror repo)

**Primary: the nightly R2 snapshot** (`data_backup/snapshot.py`, `newsroom backup snapshot`, timer 06:40). One `backups/daily/<date>.tar.gz` of every store in
`data_backup/sync._sources()` (the single coverage list: `profile_store`, `pulse_store`, `geoledger_store`, `sanctions_store`, `calendar_store`, `markets_store`,
`maritime_daily`, `intel_store` (now including `visuals/`), `instruments_store`, `ai_benchmarks_store`, `statements_store`, `actors_store`, `draft_store`,
`treatment_store`, `lead_store`, and what was published: `site_articles`, `site_intel`, `site_radar`, `site_data`) plus `<date>.manifest.json.gz` (file count, bytes and
sha256 of every file, and of the archive). It goes to a **private** bucket (`R2_BACKUP_BUCKET`; never the public one, which r2.dev serves to anyone) through the same
`R2Store` and budget meter. Retention thins the prefix to the newest 14, the newest of each of the last 8 ISO weeks and 12 months (<= 34 objects). Expected size:
the stores are ~135 MB raw (foundation.md section 3) and JSON gzips 5-8x, so **~20-35 MB a snapshot, ~0.7-1.2 GB at the 34-object ceiling (7-12% of the 10 GB free
storage)**; Class A per night ~2 PUT + 1 LIST + up to 4 DELETE = ~7, i.e. ~210 a month (0.02% of 1 M). `newsroom backup snapshot --dry-run` builds one locally and prints the
true size. `newsroom backup restore-drill` (monthly) downloads the latest, unpacks to a temp dir, checks counts and hashes, and logs ok/FAIL to `~/ops-log.md` and
`backup_state.json` (what `newsroom envelope` reads); `newsroom backup restore --to DIR` unpacks into a new directory for a real recovery.

**Second path: the `algent-data` mirror repo** (`data_backup/sync.py`, nightly 06:15 and after runs) is kept because it is a different vendor and human-diffable, but
only for files under `flags.MIRROR_MAX_FILE_BYTES` (a tenth of GitHub's 100 MB hard limit, so a file must grow tenfold before it can break a push); larger files
(for example a big `assets.jsonl`) are reported as `too_big_for_git` and are covered by the snapshot only. It never deletes. Deliberately not backed up (reasons in
`tests/test_backup_coverage.py`): run logs, `live_store` (re-collected; baselines relearn in ~3 weeks), the library crawl cache, embeddings and fetch caches.
`test_backup_coverage.py` fails when the code gains a store that is in neither table, so this cannot silently regress.

## Recovery of the lost Pulse stretch

`newsroom db export-pulses` pulls the Pulse ledger from Postgres into the file store **if the database answers** (safe no-op otherwise).
`newsroom pulse rebuild --from-rescue ~/pulse_rescue [--dailies DIR] [--dry-run]` merges the readings the live site still served
(`provenance: rescued_from_site_cache`, original timestamps) and, for days after the last of them, one position reading per Pulse per day from the
dailies (`provenance: reconstructed_from_daily`, no rationale, low confidence, and the text says so). Idempotent; never overwrites; the published reading
carries its `provenance`.

## The staging channel (previews do not read production)

Same bucket, `staging/` prefix. `ALGENT_PUBLISH_TARGET=staging` (set by `--target staging` on `publish rebuild-all` and `views build`, or exported for any other publisher) makes
`object_store.select()` return a `StagingStore` (`publishing/staging.py`) that prefixes every key, so documents, views, live snapshots and images all land under `staging/` with no change
in the publishers. Its `ident` differs, so the local hash manifests keep staging and production apart (staging is hash-skipped by itself; production's "already sent" never hides a document staging lacks).
Staging goes through the same R2 meter (the hard stop sees it) plus its own allowance (`database/flags.py`): `STAGING_CLASS_A_PER_DAY = 3000`, `STAGING_MAX_BYTES = 200 MB`;
past either, a put is refused (429) and retried next run. Retention: the ledger (`publish_held/staging_ledger.json`) records when each key was last written; `newsroom publish staging-prune`
(daily job `staging-prune`) deletes keys older than `STAGING_KEEP_DAYS = 14` and forgets their hashes, and an R2 lifecycle rule on `staging/` is the second line. `newsroom publish stage-from-prod`
publishes a sample of production (`STAGING_DIR_CAPS`, `STAGING_VIEW_CAPS`) built from the local stores; nothing is read back. A staging views build uses its own sibling store `views_store_staging`.
The preview site reads it with `NEXT_PUBLIC_DATA_BASE = <R2 base>/staging` (Vercel, Preview target); production keeps the bare base. Flow and settings: `../guides/deploy.md`.

## Operator runbook: R2 keys → rebuild-all → site env → deploy

1. **Server** (`~/algent.env`, chmod 600): `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET` (=`ohmega`), `R2_PUBLIC_BASE`
   (the r2.dev URL, later `https://data.ohmega.monster`). `newsroom doctor` should show `object store` ok; `newsroom storage status` the budget.
2. `newsroom publish rebuild-all --dry-run` — how many documents/bytes (≈ Class A operations); then `newsroom publish rebuild-all`. Re-run it freely:
   it sends only what is missing. Add `--only live,maritime` etc. to redo one product.
3. Restart the stream service so it picks up the R2 cadence: `sudo systemctl restart ohmega-ais` (the timers pick it up on their next run).
4. **Vercel** (Production + Preview): set `NEXT_PUBLIC_DATA_BASE` to the same URL as `R2_PUBLIC_BASE`; **remove** `NEXT_PUBLIC_SUPABASE_URL` and
   `NEXT_PUBLIC_SUPABASE_ANON_KEY` (nothing reads them). Redeploy (a redeploy is required: `NEXT_PUBLIC_*` is inlined at build time).
5. Check: an article hero loads from the data base, `/data/index.json`, `/live`, `/intel/maritime`, `/daily/geopolitics` render; `newsroom storage status`.
6. Optional production hardening: put the bucket on `data.ohmega.monster` (Cloudflare DNS) with a cache rule; change both URLs; run `rebuild-all` once
   more only if the R2 bucket changed (the object keys do not depend on the domain).
7. If the Supabase database comes back: `newsroom db export-pulses`, then `newsroom pulse rebuild --from-rescue … --dry-run`; to use it again set
   `POSTGRES_PUBLISH`/`PULSE_BACKEND` in `database/flags.py` (the legacy sections below).

Note: article images are served from R2 and so no longer get the `/analytics/*` Content-Security-Policy header from `next.config.mjs`; they render in
`<img>` (scripts never run there) and the converter still sanitises SVGs before upload. Add a Cloudflare response header rule on the data domain
(`Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox` for `/analytics/*`) to restore the floor.

---

# Legacy (Postgres mode, only if `POSTGRES_PUBLISH` is switched back on)

## Why this exists (the 2026-10-22 incident)

The Supabase project is on the **free plan: a 500 MB database-size quota on a 1 GB disk that also holds WAL**. It filled the disk and
crash-looped (`could not write to file pg_wal/...: No space left on device`). Every paid daily since 2026-10-21 failed on the write, and
Vercel builds timed out because pages read the database. The operator wants to stay on the free plan, so the rule from now on is:

> **Postgres holds only small, relational, bounded data. Big documents live in Storage. Churny rows are written only when they changed.
> Every growing table has a retention window. A guard reports the size and refuses a runaway write.**

## Where the space went (estimates from the code; the database was unreachable, so nothing here is measured)

Assumptions: JSONB in TOAST compresses about 3x (pglz on JSON); an update writes a whole new row version (plus new index entries) and leaves
the old one dead until vacuum; WAL is roughly 1-2x the bytes written (full-page images after each checkpoint). Cadences come from
`infra/server/install_schedules.sh`, `live/flags.py` and the writers.

| Writer -> table | Size per row/doc | Cadence | Resident growth / day (stored) | Churn / day (dead tuples + WAL) |
|---|---|---|---|---|
| **Dailies** `daily/<domain>/<date>.json` **and** the `data/daily/…` twin, plus `latest.json` | 1-3 MB each (2 MB used), ~0.7 MB stored | 2 editions rewrite the same day's doc; `publish_intel` resends the whole tree every time | ~1.4 MB (a new day x 2 copies) = **~510 MB/yr: the quota by itself** | 2 edits x 2 copies x 0.7 = **~3 MB** |
| **Dossiers** `theaters/<id>.json` + `data/theaters/…` | ~0.8 MB each x 26 x 2 copies, ~0.27 MB stored | rewritten whenever a daily changes the theater (8 of 26 typical, 26 worst) x 2 editions | ~14 MB resident, flat | **9-28 MB** |
| **Actors** `actors/<ISO2>.json` + twin (104 + index) | ~30 KB x 2 copies, ~10 KB stored | on change (slow) | ~2 MB resident, flat | <1 MB |
| **Track record** `data/track-record.json`, **AI benchmarks** `data/ai-benchmarks.json` | ~0.5 MB each, ~0.17 MB stored | markets every 4 h (changes up to 6x/day), AI every 12 h | flat | **~1 MB** |
| Feeds `data/intel.json`, `pulses`, `changes`, `forecasts`, `record.json`, `snapshots/`, `briefs/` | 0.1-0.5 MB | each publish | ~0.15 MB (snapshots, briefs) | ~1 MB |
| Radar editions `radar/<slug>.json` (kept forever) | ~100 KB, ~35 KB stored | 1/day | ~0.04 MB (**~13 MB/yr**) | none |
| `published_articles` | 20-100 KB markdown | a handful a day | ~0.2 MB (~65 MB/yr) | rewrites rare |
| `published_article_revisions` (append-only, every changed write) | one full markdown each | 2-4 per article | ~0.5 MB (**unbounded**, ~180 MB/yr) | none |
| `live_events` | ~0.6 KB + 2 indexes, ~150 live rows | ioda 15 min, usgs 10, adsb 15, firms 180: **every live event upserted every cycle** | ~0.1 MB (**unbounded**: retired rows kept forever) | ~11.8k row versions/day = **~8 MB + ~12 MB WAL** |
| `live_stats` | ~150 B x ~100 series, one row per day | upsert guarded (`where ... is distinct`) | ~15 KB (~5 MB/yr) | ~0.4 MB (the running day) |
| `live_anomalies` | ~0.4 KB, <=40 rows | hourly | tiny (pruned at 14 d) | ~0.4 MB |
| **`maritime_events`** | **~3 KB (2 JSONB columns, 24 evidence points)**, up to 3000 rows | the timer runner publishes after every live run (~350 a day); an ongoing STS/loiter/gap event changes its summary text on every 5-minute detector pass | capped ~9 MB | **up to ~1000 ongoing x 350 = ~350k versions = ~1 GB/day of heap + WAL + 5 index entries each** (the reported "1000+ rows every cycle"; the **disk filler**) |
| `radar_sightings` | ~150 B | a few hundred a day | ~0.05 MB (unbounded) | none |
| Pulse, corpus (`research_profiles` + revisions), `geo_assets`/`geo_asset_events`/`geo_grid`, `sanctions_events`, `calendar_items` | small relational rows | daily-ish | ~0.2-0.5 MB (corpus is the largest) | `geo_grid` ~200 rows replaced on rollups: small |

Reading the table: **the documents were the slow death** (a quota's worth of dailies per year, a rewrite of tens of MB per publish) and
**`maritime_events` was the sudden one** (a thousand-row, JSONB-heavy upsert every cycle: vacuum on a free instance cannot keep up and
the WAL alone can fill a 1 GB disk in a day). `live_events` was the steady third. Everything else is small.

### After this change

| Table / store | Stays in Postgres? | Steady state (year 1) | Churn |
|---|---|---|---|
| `published_intel_documents` | an **index row** per document (~200 B x ~600 docs, growing ~3/day) | **<1 MB** | an index row changes only when the document's sha256 does |
| documents (`docs/<path>.gz`) | **Storage** | ~0.35 MB/day gzipped (dailies + twin + latest dominate) = **~125 MB/yr**, see Storage budget | none on the database |
| `published_articles` | yes (small, relational, capped per row) | ~65 MB/yr, the largest remaining table | rare |
| `published_article_revisions` | yes, **last 5 per slug** | bounded (<= 5 x article size) | trimmed on write + daily |
| `live_events` | yes, ended rows pruned at 30 d, **upsert only when changed** | ~3 MB | ~2.5k versions/day (aircraft clusters only) = ~1.8 MB |
| `live_stats` | yes, 400 d | ~6 MB | as before |
| `live_anomalies` / `maritime_events` | yes, 14 d / 30 d; **maritime resent only on a real change or every 6 h** | <1 MB / <=9 MB | maritime ~500 versions/day instead of ~350k |
| `radar_sightings` | yes, 90 d | ~4 MB | none |
| corpus, geo, sanctions, calendar, Pulse | yes, never pruned | ~100-150 MB total in year 1, ~60-80 MB/yr after | small |

Net: the database sits at roughly **100-150 MB in year 1** against 500 MB, growing ~60-80 MB a year (articles + corpus, which are the
real assets), and nothing writes more than a few MB a day of dead tuples. `newsroom db size` shows the real numbers once it can reach the
database; **replace the estimates above with them after the recovery.**

## Documents in Storage (`doc_store.py`)

A published document is a **gzipped canonical-JSON object** in the public `published-assets` bucket at `docs/<path>.gz` (migration 006's
bucket and its one `select` policy; 008 added the gzip mime, nothing new to grant). Postgres keeps an index row:

| Column | Meaning |
|---|---|
| `path` (pk), `kind`, `visible`, `updated_at` | as before (`kind` = first path segment) |
| `storage_key` | `docs/<path>.gz`; null while a legacy row still holds its body inline |
| `size_bytes`, `sha256` | canonical JSON length and hash: **an unchanged document is not uploaded and its row is not written** |
| `body` | now nullable; null once the document is in Storage |

The **document paths do not change** (`daily/…`, `theaters/…`, `actors/…`, `data/…`, `radar/…`, `record.json`, `live/world.json`), so every
reader of `intelDoc`/`intelNames` is untouched; only `lib/store.ts` changed (`intelDoc` reads the index row, then the Storage object with
`gunzipSync`; a legacy inline body is still honoured; the content files remain the last fallback). Listing (`intelNames`) reads the index
rows' paths: tiny, ordered, `visible` enforced by RLS. To pull a document off the site entirely, set `visible = false` **and** delete its
object (the bucket is public, so the object URL works until it is deleted).

Everything goes to Storage, not just "the big ones": the index row costs ~200 B regardless, so one path for all documents is simpler and
removes the question of a size threshold. Two caps are **derived, not guessed** (`database/flags.py`):

- **Object cap** = the bucket's own `file_size_limit` (10 MiB, migration 006): a larger upload would be rejected by Storage anyway, so
  it is refused earlier with a log line (`REFUSED …`).
- **Row cap** `ROW_CAP_BYTES = QUOTA / 1000` (~0.5 MB): any single Postgres row (an article's markdown) above a thousandth of the quota is
  refused and logged; a thousand such rows would still fit, and real articles are tens of KB, so only a runaway trips it.

Write order: **Storage first, index row second**, so a listing never names a missing object; a failed upload leaves the old row and the
call reports `db: False` (db-mode publishes do not read as success), the documents that did land keep their rows. `publish_documents`
needs `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` as well as `DATABASE_URL` (documents no longer fit in "just a database write").
The CDN `max-age` of a document object is 60 s; the site's ISR window (300 s) is the real cache.

## Retention (`newsroom db prune`, `database/flags.py`)

A free daily timer (`ohmega-db-prune`, 03:40 UTC, `jobs.sh db-prune`) deletes in batches of `PRUNE_BATCH` rows (one commit each) and runs
`VACUUM (ANALYZE)` on the tables that lost rows. Each window is what the site actually reads:

| Table | Window | Why |
|---|---|---|
| `live_events` | ended rows 30 d | the site's RLS shows **active** rows only and nothing else reads the table; a month is enough to debug a flapping feed |
| `live_stats` | 400 d (never the running day) | the site and API show 45 d (`lib/live.ts`); the long baselines (live memory `MIN_WEEKS`/`BASELINE_WEEKS`, instruments' `percentile_1y`) are computed from the **server's** stores (`live_store/memory`, `instruments` store), not from this table. A year plus a margin keeps a year-ago comparison one query away at ~6 MB. Rows are already daily, so there is no separate rollup |
| `live_anomalies` | closed rows 14 d | equals `live/memory/flags.RETAIN_DAYS` (a test pins it) |
| `maritime_events` | ended rows 30 d | equals `maritime/flags.RETAIN_DAYS` (pinned); the long record is the server's append-only `log.jsonl` |
| `published_article_revisions` | last 5 per slug | enough to undo a bad rewrite or correction; backend-only table nothing reads |
| `radar_sightings` | 90 d | they only mean "new since this situation's Pulses were last assessed" (`pulse/freshness`); assessments happen within days |

**Never pruned** (corpus that cannot be rebuilt, and small): `published_articles`, the Pulse ledgers (`pulses`, `pulse_influences`,
`pulse_proposals`, `events`, `watches`), `research_profiles` (+ revisions), `geo_assets`/`geo_asset_events`/`geo_grid`, `sanctions_events`,
`calendar_items`. If a table is in doubt it is left out. `research_profiles`/revisions is the one corpus table with real growth (it is
the asset); watch it in `newsroom db size`.

## Churn guards on the writers

- **`live_events`**: the upsert has `where (columns) is distinct from (excluded columns)`; an unchanged event is not rewritten. (Side
  effect: `updated_at` now means "last changed", not "last seen".)
- **`maritime_events`**: `publish.pending` sends an event only when its **signature** (kind, state, area, confidence, words, times; not
  the moving last-heard time, evidence points or detail numbers) changed, or when the row is older than `maritime/flags.PUBLISH_REFRESH_H`
  (6 h) so `last_seen` and the evidence never go stale. The record of what was sent lives in the server's `published.json`.
- **`published_intel_documents`**: hash compare before any write (above). `live_stats`, `sanctions_events` (`do nothing`), `geo_*`,
  `calendar_items` already skipped unchanged rows.
- **`published_article_revisions`** is trimmed on every append.

## Size guard (`newsroom db size`, `newsroom doctor`)

`newsroom db size` prints database size vs the quota, the top tables by total relation size with their **dead-row ratio** (the churn
signal), the WAL directory when the role may list it (`wal_bytes: null` on Supabase free usually), and the Storage bucket by prefix
(`docs/`, `live/`, `analytics/`) against the 1 GB Storage quota. `newsroom doctor` has two lines, **`database budget`** and **`storage budget`**:
**warn at 70%, fail at 85%** (`WARN_SHARE`/`FAIL_SHARE`). 70% of 500 MB leaves 150 MB to react; 85% is where a `VACUUM FULL`, which
needs room to write a compact copy, can no longer be trusted to fit. The quota and the shares are plan facts in `database/flags.py`.

## Recovery runbook (the database is up but read-only)

Supabase support will likely bring it back with the read-only flag set. In this order; stop at any step that errors and read it.

0. **Writers stay off.** Pause the paid dailies and the live timers (`sudo systemctl disable --now ohmega-daily-1.timer ohmega-daily-2.timer
   ohmega-menu.timer ohmega-markets-daily.timer`, and the `ohmega-live-*` timers; `ohmega-ais` can keep running, its publish is a no-op
   without the database or fails harmlessly). Or `ALGENT_DB_PUBLISH=0`.
1. **(a) Allow writes** in a SQL session on the project: `set session characteristics as transaction read write;` (this is per-session;
   if Supabase flipped `default_transaction_read_only` at the database level, ask them or run
   `alter database postgres set default_transaction_read_only = off;`).
2. **Apply migration 014** (tiny, catalog only): `python -m algent_backend.database migrate`. It makes `body` nullable and adds the index
   columns; the site and the writers need it before the diet.
3. **(b)+(c) The diet, one idempotent command**, from the worker (it needs `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`):
   `newsroom db diet --dry-run` (prints the inline documents and bytes it would move and the rows each retention rule would delete),
   then `newsroom db diet --apply`. It uploads each inline document to Storage **before** nulling its body (one commit per document, so a
   crash loses nothing), then runs the retention prune in batches, then `VACUUM (ANALYZE)` on every table that shrank. Re-run it freely.
   If an upload fails the body stays and is listed under `left`.
4. **(d) Return the space to the disk:** `newsroom db vacuum-full --dry-run`, then `--apply`. It picks the bloated tables (over 5 MB with a
   tenth of rows dead, plus `published_intel_documents`), **smallest first**, and refuses a table that, added to the current database size,
   would not fit in the quota (its compact copy is written beside it). After step 3 the document table holds only index rows, so its
   rewrite is nearly free; `maritime_events`/`live_events` are the other candidates. Plain `VACUUM` already makes the freed pages reusable;
   FULL is what shrinks the file and the reported size.
5. **Check:** `newsroom db size` should be well under 70%; `newsroom doctor` shows the budget lines.
6. **(e) Re-enable writers:** the live timers first (`sudo systemctl enable --now ohmega-live-<feed>.timer`, or rerun
   `infra/server/install_schedules.sh`, which also installs `ohmega-db-prune`), then deploy the site (it already reads either an inline
   or a Storage document), then the paid timers. Re-send anything the failed dailies missed with the normal publish path; a
   `python -m algent_backend.publishing.published_db <site dir>` backfill resends every document (it forces past the hash compare).
7. Replace the estimates above with the measured sizes from step 5.

If support restores a **pre-incident snapshot** instead, the same steps apply (the old rows still hold inline bodies; the diet moves them).

## Storage budget

Free Storage is **1 GB for the project**, shared by `docs/` (this), `live/` (map snapshots, overwritten in place), and `analytics/` (article
images). Documents are overwritten in place by path (no versions), so they grow only with new paths: ~0.35 MB/day gzipped, ~125 MB/yr,
dominated by dailies (their `data/daily/…` twin and `latest.json` double and triple them). Expect Storage to reach 70% in roughly 4-5 years
from documents alone; `newsroom doctor` will say so first. Levers when it does (not built, nothing needs them yet): serve `/data/daily/…`
from the same object as `/…`, drop twins older than N days, move old dailies to a cold prefix.

## Left

- `intelNames` is capped by PostgREST's 1000-row page; with index rows this small, paginate (`Range`) once a directory nears it.
- `live_anomalies` still upserts all ~40 rows hourly (0.4 MB/day): a changed-only guard is possible but not worth a branch yet.
- The history readers on the backend (`recent_headlines`, `read_editions`, `_existing_corrections`) still read the `.site-live` staging
  directory, not the database or Storage.
- `research_profiles` revisions are append-only and unbounded; they are the corpus, so left. Revisit if `newsroom db size` shows them near 30%.
