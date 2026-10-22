# Database budget — Postgres holds small, relational, bounded data; everything big or churny lives elsewhere

> Code: `backend/algent_backend/database/` (`flags.py` the knobs, `size.py`, `prune.py`, `diet.py`), `publishing/doc_store.py` +
> `published_db.py` (documents), `cli/newsroom/db.py` (`newsroom db …`), `backend/migrations/014_documents_in_storage.sql`,
> `sites/ohmega-monster/lib/store.ts` (`intelDoc`). Related: `published-content.md`, `docs/guides/worker-server.md`.

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
