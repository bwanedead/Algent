# Published content — the site reads Supabase live

> Code: `backend/algent_backend/publishing/published_db.py` (rows), `asset_store.py` (images), `site_git.py` (publish
> mode), `backend/migrations/004_published_content.sql` + `006_published_assets.sql` (tables, bucket, RLS),
> `sites/ohmega-monster/lib/store.ts` + `lib/assets.ts` (readers). Access classes follow `pulse-system.md` Storage.

Publishing is a database write plus an object upload. The site fetches published rows over Supabase's REST API
(PostgREST, plain `fetch`, no client library) and images from a public Storage bucket, and revalidates every 300 s
(ISR), so a new article, brief, radar edition or daily report is live within minutes with no commit to `site-live`
and no redeploy.

## Tables and bucket

| Object | Holds | Public (`anon`) |
|---|---|---|
| `published_articles` (004) | one row per slug: title, status, `published_at`, the full site markdown (frontmatter + body + receipts) | `select` where `visible` |
| `published_intel_documents` (004) | JSON documents keyed by `path` (below) | `select` where `visible` |
| `published_article_revisions` (004) | append-only: every changed article write | nothing (no grant, no policy) |
| bucket `published-assets` (006) | article hero / figure / chart images | public read of this bucket's objects only; no write policy |

Document paths in `published_intel_documents` (the first segment is the `kind`):

| Path | Content | Site reader |
|---|---|---|
| `daily/<domain>/<date>.json`, `theaters/<id>.json` + `index.json`, `actors/<ISO2>.json` + `index.json`, `briefs/<slug>.json`, `snapshots/<slug>.json`, `record.json` | the desk's files | `daily.ts`, `dossier.ts`, `actors.ts`, `intel.ts`, `record.ts` |
| `radar/<slug>.json` | one headline-radar edition (kept forever) | `radar.ts` |
| `data/<rel>` | the agent feeds, byte-for-byte what `public/data/<rel>` was: `data/index.json`, `data/articles/<slug>.json`, `data/intel.json`, `data/pulses.json`, `data/changes.json`, `data/forecasts.json`, `data/daily/…`, `data/briefs/…`, `data/pulses/…`, `data/theaters/…`, `data/actors/…`, `data/record.json` | `app/feeds/[...path]/route.ts` (served at `/data/*`), `situation.ts` |

Every other table (corpus, ledgers, Pulse) has RLS on, **no policy, no grant**: unreadable through the anon key.
`tests/test_published_db.py` pins 004 (only the two published tables are granted); `tests/test_published_assets.py`
pins 006 (one `select` policy for `anon`, on `storage.objects` for this bucket, nothing else).

## Write path

`publish_run` / `retract` (articles), `write_intel` (desk documents + agent feeds), `publish_menu` (radar) and
`_write_agent_twin` (article twin + `/data/index.json`) call `published_db` after writing their files. It upserts
only changed rows (idempotent), never raises into a run, and is a no-op without `DATABASE_URL` (env only; `.env` is
not loaded, so tests cannot reach the live database). `ALGENT_DB_PUBLISH=0` pauses rows and uploads.

**Assets.** `publish_run` uploads each article image (SVGs sanitised first) to the bucket **before** writing the row,
so a page never goes live ahead of its images. Key = the site path without its slash (`/analytics/<slug>/hero.webp`
-> `analytics/<slug>/hero.webp`), via the Storage REST API (`POST /storage/v1/object/published-assets/<key>`,
`x-upsert`) with the **server-only** `SUPABASE_SERVICE_ROLE_KEY` + `SUPABASE_URL`. Idempotent: a SHA-256 manifest
(`backend/publish_held/asset_hashes.json`, gitignored) skips unchanged objects; losing it only costs re-uploads.
Radar has no image assets (editions are text documents).

## Publish modes (`flags.SITE_PUBLISH_VIA`, one-shot override `ALGENT_SITE_PUBLISH_VIA`)

| Mode | What a publish does |
|---|---|
| `"git"` (default) | writes files into the `.site-live` worktree and commits + pushes to `site-live`; rows and uploads are a mirror (a failure there is ignored) |
| `"db"` | rows + uploads **are** the publish: no commit, no push, no deploy-key write. `ensure_worktree` only makes sure `.site-live/` exists as a plain staging directory (the writers and the history readers keep using it) and `commit_and_push` is a no-op. A failed row/upload write is an **error** (nothing written locally, the article is not announced, a retry is clean); with no `DATABASE_URL` the publish is skipped with a clear note rather than silently not shipping |

`ALGENT_SITE_PUBLISH=0` still pauses everything (stage only) in both modes.

## Read path

`lib/store.ts`: when `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` are set, pages read Supabase; an
error or an empty answer falls back to the content files (`content/articles`, `content/intel`, `content/radar`,
`public/data`). Every reader (`daily`, `intel`, `dossier`, `actors`, `radar`, `situation`, `record`, articles,
sitemap, `/data/*`) goes through `intelDoc` / `intelNames` / `intelSlugs` / `articleSource(s)`. Pages that read it
carry `revalidate = 300`; briefs, theaters and actors render on demand when new (no `dynamicParams = false`), so a
new one needs no redeploy.

`next.config.mjs` rewrites `/data/:path*` to `app/feeds/[...path]/route.ts` **before** the filesystem check, so a
stale committed `public/data/*` can never shadow the live document; the public URLs are unchanged. `public/llms.txt`
stays a static file (hand-written documentation of the feeds, not publish output).

**Images.** `lib/assets.ts` `assetUrl()` maps `/analytics/…` to
`<NEXT_PUBLIC_SUPABASE_URL>/storage/v1/object/public/published-assets/analytics/…` when the env is set (else the
`/public` path). `NEXT_PUBLIC_ASSETS_FROM_STORAGE=0` forces `/public` (use until the asset backfill has run). Used by
the article page (hero, Open Graph), the feed thumbnails, and `ArticleImage` (markdown figures). The site uses plain
`<img>`, so no `next/image` remote pattern is needed.

## Cut-over (operator + lead)

1. Apply migration 006 (`python -m algent_backend.database migrate`) — creates the bucket and its `select` policy.
2. Put `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in the worker's `~/algent.env` (never in Vercel).
3. Backfill, from a checkout whose site dir has the existing files (the `.site-live` worktree):
   `python -m algent_backend.publishing.published_db .site-live/sites/ohmega-monster` (articles, desk files, radar
   editions, `data/*`) and `python -m algent_backend.publishing.asset_store .site-live/sites/ohmega-monster`
   (every `public/analytics/**` image). Both are idempotent and safe to re-run.
4. Deploy the site (Vercel env already has the two `NEXT_PUBLIC_SUPABASE_*`). Check an article hero loads from the
   `…/storage/v1/object/public/published-assets/…` URL, `/data/index.json` and `/radar` render.
5. Flip `SITE_PUBLISH_VIA = "db"` in `agents/newsroom/flags.py`. Publish one article; confirm it appears with no
   `site-live` commit.
6. The `Algent` deploy key can become read-only (`docs/guides/worker-server.md`).

**Retirement of the file path** (a week after step 5 with no fallback hits): delete the file readers in `store.ts`
(`fileRoot`, `readFile`, the `fs` branches), `content/` + `public/data` + `public/analytics` from the `site-live`
branch, the file writes and `.site-live` staging in the publishers, and `site_git`'s git functions. Until then the
fallback is what keeps the site up if Supabase is unreachable.

## Left

Lists longer than PostgREST's 1000-row page cap (`intelNames`) need pagination once a directory (e.g. a domain's
daily reports) nears it. The history readers on the backend (`recent_headlines`, radar `read_editions`,
`_existing_corrections`) still read the `.site-live` staging directory, not the database.
