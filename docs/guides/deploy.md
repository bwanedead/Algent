# Deploying the site: merge, preview, smoke, promote

Written for whoever deploys. Until October 2026 production was the test environment: preview deployments read the live R2 data, nothing checked the
site after a deploy, and every break was found by a reader. This is the routine that replaces that. Companions: `site-branch-protocol.md` (the branches),
`../architecture/database-budget.md` (R2 and its guard), `../architecture/foundation.md` (the registry), `worker-server.md` (the machine).

## The picture

```
 organic-dev ──push──► Vercel PREVIEW  ── reads ──►  <R2 base>/staging/…   (NEXT_PUBLIC_DATA_BASE, Preview target)
      │                      │                              ▲
      │                      │                              │  newsroom publish stage-from-prod   (a sample of production, from local stores)
      │                      │                              │  newsroom publish rebuild-all --target staging   /   newsroom views build --target staging
      │                      ▼
      │             newsroom site deploy-check   (waits for the preview, runs the smoke test against it)
      │                      │ healthy
      ▼                      ▼
 merge into site-live ──► Vercel PRODUCTION ── reads ──►  <R2 base>/…      (NEXT_PUBLIC_DATA_BASE, Production target)
                             │
                             ▼
                  hourly `site-smoke` job (and after every publish job) ─► ~/ops-log.md + the `site` row of `newsroom envelope` / `newsroom doctor`
```

## One-time setup (operator)

1. **Vercel env, two values, same variable** (Project > Settings > Environment Variables). The site has one setting for where its data lives
   (`lib/data-base.ts`), a URL *including any prefix*:

   | Variable | Target | Value |
   |---|---|---|
   | `NEXT_PUBLIC_DATA_BASE` | Production | the R2 public URL, as today (`https://data.ohmega.monster`, or the `pub-….r2.dev` URL) |
   | `NEXT_PUBLIC_DATA_BASE` | **Preview** | the same URL **plus `/staging`** (`https://data.ohmega.monster/staging`) |

   Redeploy after changing them (the value is inlined at build time). `NEXT_PUBLIC_SITE_URL` may stay unset on Preview; the smoke test reads only paths from the
   preview's sitemap, never its canonical host.
2. **Vercel deployment protection.** A preview behind "Vercel Authentication" answers 401 to the smoke test. Either set the preview to public, or create a
   *Protection Bypass for Automation* secret (Settings > Deployment Protection) and export it where you run the check as `VERCEL_AUTOMATION_BYPASS_SECRET`
   (the checker sends it as `x-vercel-protection-bypass`). The server's hourly check hits production, which is not protected.
3. **R2 lifecycle rule** (Cloudflare > R2 > the bucket > Settings > Object lifecycle rules): prefix `staging/`, delete objects 14 days after upload. It is the
   second line behind `newsroom publish staging-prune` (same 14 days, `STAGING_KEEP_DAYS`), so the prefix cleans itself even if the job stops.
4. **Server** (once, after the deploy that contains this): `~/Algent/infra/server/install_schedules.sh` to install the new timers (`site-smoke`, `staging-prune`),
   then `newsroom products check --text`.
5. **GitHub token (only if the repository is private):** `GITHUB_TOKEN` with read access in the environment of whoever runs `deploy-check`. A public repository needs none.

## The routine

All commands run from `backend/` (server: `cd ~/Algent/backend && .venv/bin/python -m algent_backend.cli newsroom …`; laptop: `.venv\Scripts\python.exe -m …`).

1. **Merge to `organic-dev` and push.** Vercel builds a preview of the branch (the build is the type-check: there is no local `node_modules`).
2. **Stage the data the preview needs.**
   - Normal case, no data change: `newsroom publish stage-from-prod`. A *sample* of what production serves (newest dailies per desk, a handful of
     countries, situations and entities, every index, the live and table documents) is published to `staging/`, from the server's local stores. It reads nothing
     back from R2, skips what is already staged (hash manifest of its own), and costs a few hundred operations the first time and almost none after.
     `--dry-run` first prints how many; `--only site-documents,views` narrows it.
   - **A schema or view change** (the reason staging exists): build the new shape into staging only, *then* look at the preview, *then* promote.
     `newsroom views build --target staging` (or `newsroom publish rebuild-all --target staging --only …`) runs the new code and writes under `staging/`, using its own
     local views store (`views_store_staging`) so production's store and change-stamps are untouched. Any other publisher can be pointed the same way with the
     environment variable `ALGENT_PUBLISH_TARGET=staging` for one command.
   - Staging has its own allowance inside the same R2 guard (`database/flags.py`): `STAGING_CLASS_A_PER_DAY` (3 000 operations), `STAGING_MAX_BYTES` (200 MB).
     Past either, a put is refused and retried on the next run; `newsroom publish staging-status` and `newsroom storage status` show where it stands.
3. **Check the preview.** `newsroom site deploy-check` (defaults: branch `organic-dev`, waits up to 15 min). It finds the Vercel deployment recorded on the
   branch's newest commit over GitHub's REST API, waits until it is ready, then runs the smoke test against its URL. Exit 0 healthy, 1 a check failed,
   3 no ready preview in time, 2 usage. With the URL already in hand: `newsroom site deploy-check --url https://<preview>.vercel.app` or
   `newsroom site smoke --base https://<preview>.vercel.app` (from the site folder: `node scripts/smoke.mjs <url>`, the same code). Look at two or three pages too:
   the smoke test proves the pages render and the data is there, not that they look right.
4. **Promote.** Only when step 3 is green: merge `organic-dev` into `site-live` exactly as `site-branch-protocol.md` says (one direction, the `.site-live` worktree).
   If the change needs a new document shape, publish it to production now: `newsroom views build` / `newsroom publish rebuild-all` (or wait for the timer).
5. **Verify production.** `newsroom site smoke` (a minute after Vercel finishes). From here the hourly job watches it.
6. **If production breaks:** `newsroom site smoke` names the failing routes; roll back by merging the previous `site-live` commit back (or Vercel > Deployments > Promote
   the previous deployment), then fix on `organic-dev`.

## What the smoke test checks (`newsroom site smoke`)

One implementation, Python stdlib only (`backend/algent_backend/ops/smoke/`), so it runs on the server (no Node needed), from the deploy routine and in tests.
About 60 paced requests (the agent API allows a burst of 40 and 120 a minute per client).

| Group | Asked for | Fails when |
|---|---|---|
| Registry pages | every static `site_routes` of every product (a new page is checked the day it is registered) | status is not 200; not a complete HTML document; the page shows "not published / could not be found / application error" copy where data must exist; Next rendered its error page |
| Samples | from `/sitemap.xml`, per dynamic route: the newest date per desk (`/daily/<desk>/<date>`), one situation, country (actor page), place, brief, article; `/daily/<desk>/archive`; the globe's country panel | same; a template the sitemap cannot sample is listed as a note |
| Agent API | `/api/v1` index, `openapi.json`, `search`, `entity`, `about`, `series`, `theaters`, the newest daily of each desk, track record, sanctions, calendar, AI benchmarks | not JSON; an `{error}` envelope; `meta` lacks `as_of`/`source`/`version`/`cite_as`/`license`; `data` empty |
| Machine files | `sitemap.xml`, `feed.xml` parse as XML; `robots.txt` names the sitemap; `llms-full.txt` non-empty | |
| Redirects | the retired routes (`/geopolitics`, `/ai`, `/headlines`, `/radar`, `/intel`, `/intel/theaters`) | not a 3xx to exactly the new place |
| Freshness | the API `meta.as_of` of the dailies (**fail**) and track record, sanctions, calendar, benchmarks (**warn**) | older than 3 x the product's cadence from the registry (a bare-day stamp is aged from the start of today, as the site does); a visible `is-stale` marker on the hubs warns |
| Time | every request | slower than 6 s warns; no answer at all fails |

Output: `smoke <base> - OK|FAILED - N checks: …; p95 … ms, slowest …` then one line per warning or failure; `--json` gives everything. Exit 1 on any failure.
Thresholds and the fallback phrases are in `ops/smoke/flags.py` (each with its reason). `MAY_BE_EMPTY` there is where a route that is legitimately empty gets exempted,
with the reason.

## On the server

| Job (registry, product `site`) | When | Does |
|---|---|---|
| `site-smoke` | hourly at :17, and as the last after-hook of `daily-1`, `daily-2`, `ai-daily` (if scheduled), `markets-daily` and `views` | `newsroom site smoke --log` against production |
| `views-fast` | every 30 min, and as an after-hook of `daily-1`, `daily-2`, `ai-daily`, `markets-daily` | rebuilds Home, the globe HUD and the daily hub so a new daily shows within minutes |
| `staging-prune` (product `staging`) | daily 05:05 | deletes staged objects not rewritten for 14 days |

After-hooks are the registry's `Job.then`: a job that exits 0 starts its hooks as jobs of their own, after releasing its lock. A failing hook is reported on stderr and never
changes the parent's result. `--log` keeps the last report for the doctor and writes `~/ops-log.md` **only** on a failure (each failing run) and on recovery; a green run is silent.
The result appears as the `site` row of `newsroom envelope` and as `envelope:site` in `newsroom doctor`: **fail** while any check fails, **warn** if no run happened for 3 hours.

```
newsroom site smoke --log                      # what the timer runs; add --json for the full report
newsroom site smoke --base https://<preview>   # any other base: printed, never recorded as the site's state
newsroom envelope --text | grep site
newsroom products run site-smoke               # the same as the timer
newsroom publish staging-status
```

## Known limits

- The smoke test cannot see layout or visual regressions, and it cannot tell a *wrong* number from a present one. It is a floor: the page renders and the data it needs is there and fresh.
- Staged article and daily images are not copied (the bulk of the bytes), so a preview shows those images missing; `--only images` stages them if you need to look.
- Live map snapshots (`live/…`, republished every few minutes) are staged once by `stage-from-prod`; a preview's live layers are as old as the last staging.
- The preview's ISR windows (5-30 min) apply: after re-staging, a preview page can take up to its window to change.
