# Published content — the site reads Supabase live

> Code: `backend/algent_backend/publishing/published_db.py` (writer), `backend/migrations/004_published_content.sql`
> (tables + RLS), `sites/ohmega-monster/lib/store.ts` (reader). Access classes follow `pulse-system.md` Storage.

Publishing is a database write. The site fetches published rows over Supabase's REST API (PostgREST, plain
`fetch`, no client library) and revalidates every 300 s (ISR), so a new article or daily report is live within
minutes with no commit to `site-live` and no redeploy.

## Tables (migration 004)

| Table | Holds | Public (`anon`) |
|---|---|---|
| `published_articles` | one row per slug: title, status, `published_at`, the full site markdown (frontmatter + body + receipts) | `select` where `visible` |
| `published_intel_documents` | the desk's JSON files keyed by path under the intel dir (`daily/geopolitics/<date>.json`, `theaters/<id>.json`, `actors/XX.json`, `briefs/…`, `snapshots/…`, `record.json`) | `select` where `visible` |
| `published_article_revisions` | append-only: every changed article write | nothing (no grant, no policy) |

Every other table (corpus, ledgers, Pulse) has RLS on, **no policy, no grant**: unreadable through the anon key.
The migration test (`tests/test_published_db.py`) pins this: only the two published tables are granted.

## Write path

`publish_run` / `retract` (articles) and `write_intel` (desk documents) call `published_db` after writing their
files. It upserts only changed rows (idempotent), never raises into a run, and is a no-op without `DATABASE_URL`
(env only; `.env` is not loaded, so tests cannot reach the live database). `ALGENT_DB_PUBLISH=0` pauses it. One-off
fill of an existing checkout: `python -m algent_backend.publishing.published_db <site dir>`.

## Read path

`lib/store.ts`: when `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` are set, pages read Supabase;
an error or an empty answer falls back to the content files. **Transitional:** the file path (and the `site-live`
commit) stays until the site has run on Supabase in production for a week *and* assets move to object storage;
then delete the file readers in `store.ts` and the file writes in the publishers.

Revalidation is 300 s: a handful of publishes a day makes minutes of staleness invisible, and each page
regenerates at most once per window.

## Migrated vs left

Done: `/geopolitics` + `/geopolitics/<date>` + home daily card, `/intel/record`, articles (`/articles/<slug>`, home
feed, `feed.xml`, `sitemap`). Still file-only (already written to the table, readers not yet moved):
`lib/intel.ts` (briefs, snapshots: `/intel`), `lib/dossier.ts` (`/intel/theaters/*`), `lib/actors.ts`
(`/intel/actors/*`), `lib/radar.ts` and the `public/data` agent feed. Each is the same change as `daily.ts`: replace
its `readJson`/`readdirSync` with `intelDoc`/`intelNames` and make callers `await`. Not in the database at all:
article hero/analytic images (`public/`) and radar menus; until they are, an article's images still ship by commit.
