# Published content — the site reads published files from R2

> Code: `backend/algent_backend/publishing/` (`object_store.py`, `object_docs.py`, `asset_store.py`, `site_data.py`, `rebuild.py`, `site_git.py`),
> the domain publishers (`live/publish.py`, `maritime/publish.py`, `sanctions/publish.py`, `lookahead/publish.py`, `geoledger/site_docs.py`, `conflict/publish.py`, `gnss/publish.py`),
> `sites/ohmega-monster/lib/store.ts` + `lib/data-base.ts` + `lib/assets.ts` (readers). **Storage architecture, budgets and the runbook:
> `database-budget.md`.** There is no database on the read path (decision 2026-10-22).

The worker server is the system of record. Publishing is an object upload: every JSON document is a gzipped object in the public R2 bucket, every image
and live snapshot a plain object. The site fetches them with plain `fetch` from one public URL (`NEXT_PUBLIC_DATA_BASE`) and revalidates each product on
its own cadence (ISR), so a new article, brief, radar edition or daily report is live within its window with no commit to `site-live` and no redeploy.

## Products (what the site publishes)

Three products, and nothing else is a publication. Every page wears a type tag (DAILY / THEATER / ARTICLE / HEADLINES / TOOL).

| Product | Route | Source documents |
|---|---|---|
| **The Daily** | `/daily/<desk>`, `/daily/<desk>/<date>` | `daily/<domain>/<date>.json`: one report per day (morning and evening parts merge into it) |
| **Situations** (theaters) | `/situations`, `/situations/<id>` | `theaters/<id>.json` plus every Daily section for that theater |
| **Articles** | `/articles`, `/articles/<slug>` | `articles/index.json` (front matter of all) + `articles/<slug>.json` (the markdown): deep dives |

Not products: **Headlines** (`radar/<slug>.json`) and the **Data & tools** (Pulses, record, calendar, sanctions, maritime, live, actors, forecasts, places).
Retired routes redirect permanently (`next.config.mjs`).

## Objects in the bucket

Key layout (the same keys on any backend; `NEXT_PUBLIC_DATA_BASE` + key is the URL):

| Prefix | Holds | Content type |
|---|---|---|
| `docs/<path>.gz` | every document, canonical JSON, gzipped (`doc_store.pack`) | `application/gzip` |
| `docs/_names/<dir>.json.gz` | the names directly inside `<dir>` (a bucket cannot be listed by the site) | gzip |
| `live/<name>.json[.gz]` | the map's snapshots (`vessels`, `aircraft`, `points`, `summary`, `energy`, `fires`, `coverage`, `tracks/…`, `flows`, `satellite`) | json / gzip |
| `analytics/<slug>/<file>` | article images | image/* |
| `satellite/<site>/…` | Sentinel-2 chips (immutable) | image/png |

Document paths (`kind` = first segment). The table-shaped products are listed in `database-budget.md` ("What each product publishes"):

| Path | Content | Site reader |
|---|---|---|
| `daily/<domain>/<date>.json`, `theaters/<id>.json` + `index.json`, `actors/<ISO2>.json` + `index.json`, `briefs/<slug>.json`, `snapshots/<slug>.json`, `record.json` | the desk's files | `daily.ts`, `dossier.ts`, `actors.ts`, `intel.ts`, `record.ts` |
| `radar/<slug>.json` | one headline-radar edition (kept forever) | `radar.ts` |
| `data/<rel>` | the agent feeds, byte-for-byte what `public/data/<rel>` was | `app/feeds/[...path]/route.ts`, `situation.ts` |
| `live/events|stats|anomalies.json`, `live/world.json` | live products | `live.ts` |
| `maritime/…`, `sanctions/…`, `calendar/next.json`, `geo/…`, `articles/…` | table-shaped products | `maritime.ts`, `sanctions.ts`, `calendar.ts`, `geoledger.ts`, `articles.ts` |
| `conflict/recent.json`, `conflict/country/<ISO>.json`, `gnss/latest.json`, `live/gnss.json` | the attack log and GPS interference (events and derived zones only; `conflict-events-gnss.md`) | `conflict.ts`, `components/gnss/useGnss.ts` |

## Contracts and status files

Every dict document is stamped `"schema": "<id>/<major>"` on publish (declared per product in the registry; `foundation.md` section 6a has the family list, the version rule and what
the site does on an unknown major). `docs/status/<product>.json.gz` (`ohmega.status/1`) says when a product's job last ran fine (`checked_at`) and when it last published something new
(`last_changed_at`); one PUT per successful run, throttled to every 30 minutes for the fast feeds.

## Orphans

`newsroom publish prune-orphans [--prefix views/] [--dry-run] [--list] [--limit N]` (module `publishing/orphans.py`, daily job `orphan-prune`). Orphans = documents the local hash manifest says
were published under a prefix minus what the current build produces; only prefixes with a registered owner (`views/`: the keys of the last complete build) can be pruned, and nothing the
registry has no contract for is touched. No bucket LIST unless `--list` (one bounded pass, Class A about 1 per 1,000 objects, for a lost manifest). DELETEs are Class A through the R2
guard, capped per run (`ORPHAN_PRUNE_MAX_PER_RUN` = 4,000); a refusal stops the run. Each run appends to `<held>/orphan_prune.jsonl`.

## Write path

`publish_run` / `retract` (articles), `write_intel` (desk documents + agent feeds), `publish_menu` (radar), `_write_agent_twin`, and each domain's
`publish()` call `published_db.publish_documents` / `publish_article` — names kept for the callers; with `POSTGRES_PUBLISH` off they go to
`object_docs`. A document is packed (canonical JSON, sha256), compared with the LOCAL manifest, uploaded only if changed, then the name index of any
directory that gained a document is refreshed. Everything goes through `asset_store.upload` → `object_store` (R2 by default; the SigV4 signing is
stdlib), so one place applies the free-tier guard (`object_budget.py`). It never raises into a run and is a no-op until the R2 names are set;
`ALGENT_DB_PUBLISH=0` pauses it. A document over the object cap (10 MiB gzipped) or an article over the row cap is refused and logged.

**Assets.** `publish_run` uploads each article image (SVGs sanitised first) **before** writing the article, so a page never goes live ahead of its
images. Key = the site path without its slash. Idempotent via `backend/publish_held/asset_hashes.json`.

## Publish modes (`flags.SITE_PUBLISH_VIA`, one-shot override `ALGENT_SITE_PUBLISH_VIA`)

| Mode | What a publish does |
|---|---|
| `"git"` | writes files into the `.site-live` worktree and commits + pushes to `site-live`; the object upload is a mirror |
| `"db"` (the name is historical: it means "objects are the publish") | uploads **are** the publish: no commit, no push. `.site-live/` stays a plain staging directory (the writers, the history readers and the backup use it); a failed upload is an **error** (the article is not announced, a retry is clean); with no object store configured the publish is skipped with a clear note |

`ALGENT_SITE_PUBLISH=0` still pauses everything (stage only).

## Read path

`lib/store.ts` reads `<NEXT_PUBLIC_DATA_BASE>/docs/<path>.gz` (`publishedDoc`, `intelDoc`, `tableDoc`, `intelNames` from the `_names` indexes, `articleFronts`,
`articleSource`). With the variable unset (local dev) or a document answering 404, it falls back to the content files (`content/articles`,
`content/intel`, `content/radar`, `public/data`). **Failure rule:** 404 = not published (null); any other failure throws so ISR keeps the last good page
(never regenerate an empty one); during `next build` a failure degrades to the files. Per-product windows: `TTL` in `store.ts` (see `database-budget.md`).
Briefs, theaters and actors render on demand when new, so a new one needs no redeploy.

`next.config.mjs` rewrites `/data/:path*` to `app/feeds/[...path]/route.ts` **before** the filesystem check, so a stale committed `public/data/*` can
never shadow the live document. `public/llms.txt` stays a static file.

**Images.** `lib/assets.ts` `assetUrl()` maps `/analytics/…` to `<NEXT_PUBLIC_DATA_BASE>/analytics/…` when set (else `/public`);
`NEXT_PUBLIC_ASSETS_FROM_STORAGE=0` forces `/public` (use until `rebuild-all` has run). The live map reads `<base>/live/…`, satellite chips `<base>/satellite/…`.

**Environment (site, Vercel):** `NEXT_PUBLIC_DATA_BASE` only. The Supabase variables are no longer read.

## Cut-over

The runbook (R2 keys → `newsroom publish rebuild-all` → `NEXT_PUBLIC_DATA_BASE` in Vercel → redeploy) is in `database-budget.md`.
`rebuild-all` replaces the old backfill modules: it republishes every document, article, image and table-shaped product from the local stores and is
idempotent. Retirement of the file fallback (a week after the cut-over with no fallback hits): delete `fileRoot`/`readFile` and the `fs` branches in
`store.ts`, `content/` + `public/data` + `public/analytics` from the `site-live` branch, and `site_git`'s git functions.

## Left

The history readers on the backend (`recent_headlines`, radar `read_editions`, `_existing_corrections`) read the `.site-live` staging directory, which
is now also part of the nightly backup. Static (event-less) places beyond a country's 2000 largest have no published page data.
