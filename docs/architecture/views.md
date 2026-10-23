# Views: the server publishes ready answers, the site and agents read one small file

> Code: `backend/algent_backend/views/` (builders, publisher, CLI `newsroom views`), the site's reader `sites/ohmega-monster/lib/views.ts` (+ `views-types.ts`),
> the agent ops `lib/api/ops-corpus.ts`, the rate-limit seam `middleware.ts` + `lib/api/ratelimit.ts`. Registry product `views`
> (`backend/algent_backend/ops/products/registry.py`). Contract check: `sites/ohmega-monster/scripts/view-check.mjs`, run by `backend/tests/test_site_views_contract.py`.

## Why

The site used to aggregate raw documents **at render time**: the globe's country panel read up to 30 dailies and every actor page; a situation page read
every daily of both desks that covered it and all actor pages; Home, the HUD and the Daily hub each stitched many documents (some 800 KB each); the `/api/v1`
routes and the MCP tools filtered big documents per request. That caused build timeouts and the Supabase egress overage, and it only gets slower as history
grows. The corpus index (SQLite, rebuilt every 4 h on the server) can answer those questions, but Vercel cannot open SQLite.

So the **server publishes ready answers**. A *view* is one small, versioned JSON document built from the stores and the corpus; a page reads the one it needs; an
agent endpoint reads the one that answers its question. Nothing on the read path aggregates.

```
 stores (the record) ──► staged documents + table products ──┐
                                                             ├──► views/ builders ──► views_store/ (server, first) ──► R2 docs/views/<key>.json.gz ──► site / API / MCP
 corpus index (SQLite) ──────────────────────────────────────┘                          derived, rebuildable           hash-skip: only changed views upload
```

## The views

Every view opens with the same envelope: `schema` (`ohmega.view.<family>/1`), `built_at` (when this *content* was first built: an unchanged view keeps it, so it is
byte-identical and costs no upload), `as_of` (date of the newest input), `provenance` (`{builder, sources:[{product, from}]}`). Records inside keep their own
`product`, `origin` and source URLs; series keep their `basis` (the stats-registry vocabulary: official, our_count, our_derived, model, reported ...).

| Key | Holds | Built from | Budget | Measured on dev data | Read by |
|---|---|---|---|---|---|
| `country/<ISO2>` | the globe panel exactly (`CountryPanel`: stats vs the profiled median, counts, grid line, leaders, 120 newest briefs with their map theme); the actor page's context (theaters, what its officials said, developments, related states); sanctions, calendar, grid rows; a snapshot of its Pulses; relations, series, record counts from the corpus | actor pages, 30 dailies, sanctions/calendar/grid documents, the record ledger, corpus | 160 KB | 45 views, avg 18 KB, max 37 KB | `/api/globe/country`, `/intel/actors/[iso]`, agent tools |
| `situation/<id>` | the stream: the newest 3 days as full Daily sections, every other day as an index row (date, headline, direction, visuals, link into the Daily); a snapshot of the page's Pulses; the actors it involves with their headline figures; states tied to it; related situations; pulses, actors, map points, briefs | every daily, dossier, actor pages, snapshot, theater-state graph | 600 KB (sheds full days until it fits) | 10 views, max 231 KB | `/situations/[id]`, agent tools |
| `situations` | one slim row (+ last 21 days of escalation and coverage) per situation, grouped by desk: active / quiet / merged | dossier index + dossiers | 150 KB | 10 KB | `/situations`, Home, doors |
| `entity/<kind>/<id>` | who or what it is; aliases (and the ids merged into it); counts; typed relations; related with the parts of the score; 15 documents, 10 claims (with grounding, confidence, source URLs), 15 events; up to 12 series with unit and basis; for a geoledger place the asset, its whole status history and the theaters that put it there | corpus (+ `geo/a/<id>`) | 60 KB | 834 views, avg 10 KB, max 37 KB | `/intel/places/[id]`, agent tools |
| `series/<metric>`, `series-index` | one metric across the 60 most recently updated entities (24 points each) with unit and basis; the list of every metric | corpus observations | 120 KB / 300 KB | 82 views (max 28 KB) / 18 KB | agent `series` |
| `event/<date>/<theater>` | the developments of one theater's section on one day (raw) and the state each named actor resolves to | the daily | 60 KB | 24 views, avg 6 KB | `/intel/events/...` |
| `home` | each desk's newest report as a digest (headline, sections, pulses, trackers, visual stills; no maps or developments), the coverage series and top-moving Pulse, situations escalating, calendar rows, the counts behind the doors | dailies, dossiers, snapshot, calendar, sanctions, record | 200 KB | 18 KB | `/` and the doors on `/data` |
| `hud` | `globe` = `GlobeData` (per-country channel rows, theater dots) and `hud` = `HudData` without its live block (today's lines, theaters with Pulses, movers, calendar and sanction rows, the paper trader) | dailies, actors, snapshot, sanctions, calendar, anomalies, track record | 300 KB | 39 KB | `/globe` |
| `daily-hub` | per desk: the newest report as a digest and the list of days | dailies | 60 KB | 14 KB | `/daily` |
| `graph` | which theaters and states have a page and how strongly the sources tie them (the old per-request entity index) | dossier index, actor pages, 3 dailies | 80 KB | 3.5 KB | every entity link, `/intel/graph`, `LinkedText` |
| `search-index` | entity names and aliases with the view key that answers for each (top 6,000 by use) and the newest 4,000 document titles | corpus | 2 MB | 108 KB | `search`, `entity` name resolution |
| `manifest` | per family: schema, count, bytes, the largest view | this build | 200 KB | 1.7 KB | operators |

A **digest** is the daily's own document shape with only what an overview needs left in it, so the site parses it with the parser it already has
(`parseDaily`); a **full section** inside a situation view is parsed with `parseTheater`; the snapshots inside views are parsed with `parseSnapshot`. A view never
needs a second reader. Raw text fields (a section's headline, a brief line) stay raw: the site cuts them to a line with `claimOf`, as it always did.

Caps are in `views/flags.py`, each with its reason; a list that was cut carries its `total` (`briefsTotal`, `sanctionsTotal`, `days_total`, `entities_total`).
A view over its family's byte budget is **not uploaded** (the last good one stays) and the build says so; `situation` sheds full days first.

## What the pages read now

| Page | Before (per request / per build) | Now |
|---|---|---|
| Globe country panel `/api/globe/country/[iso]` | all ~80 actor docs for the medians + 30 dailies + sanctions/calendar/grid + the entity index | `country/<ISO>` + the live anomalies document (the one live count) |
| `/globe` | 21 dailies + actor pages + dossiers + sanctions + calendar + track record, then the live block | `hud` + the live block (still live) |
| `/situations/[id]` | the dossier + every daily of both desks + every actor page + the entity index + the snapshot | the dossier + `situation/<id>` (+ live anomalies) |
| `/situations`, Home "moving", doors | every dossier | `situations` / `home` |
| `/` | two dailies in full + snapshot + every dossier + ~15 documents for the doors (the 1 MB record ledger among them) | `home` + the live strip + articles index + a handful of small documents for the other doors |
| `/daily` | each desk's newest report in full + name lists | `daily-hub` |
| `/intel/actors/[iso]` | the actor doc + entity index + record ledger + snapshot + sanctions/calendar/grid documents | the actor doc + `country/<ISO>` |
| `/intel/actors` | ~80 actor documents | the published `actors/index.json` (one document, already carries the headline figures) |
| `/intel/events/[date]/[theater]/[n]` | the day's report (up to 800 KB) + entity index | `event/<date>/<theater>` |
| `/intel/places/[id]` | `geo/a/<id>` + entity index | `entity/place/<id>` (a merged spelling still reads the ledger's stub, to redirect) |
| `LinkedText`, `/intel/graph` | entity index | `graph` |

Removed as dead (convergence, no parallel path): `lib/globe-briefs.ts`, `lib/globe-mentions.ts`, the daily/actor/dossier walks in `lib/entities.ts`
(`relatedTheaters`, `theaterStates`, `theaterRef`, the per-request index), `situationStream` over every daily, `allActors` / `actorsForTheater`, `sanctionsForCountry`,
`calendarForCountry`, `themeOf`/`decay` in `lib/globe/themes.ts` (the theme rule now has one home, `views/themes.py`, with a parity test against `lib/visual.ts`).
Rendering components are unchanged except where their input changed shape: `SituationStream` (full days + index rows), `Today` (precomputed `moving`),
`ActorStrip`/`ActorScales` (take the slim `ActorLite`), `TheaterRows` (slim dossier).

ISR: each page keeps its literal `revalidate`; views are fetched with `TTL.fast` (300 s; `home`, `hud`, `daily-hub`: the server refreshes them every 30 min) or
`TTL.daily` (1800 s; everything else) or `TTL.static` (search and series indexes). A view that is not published reads as `null` and the page shows its empty state;
there is deliberately **no file fallback** (the old content files cannot build these answers, and a fallback would be the parallel path views replace).

## Jobs and order

* `views` (`2/4:50` UTC, free, takes the heavy-job lock): everything. It runs after `corpus-build` (`2/4:25`): the lock makes it wait if the corpus build is still running. A full
  build reads the whole daily archive twice (situation streams, event pages), one file in memory at a time; entity views read the corpus through a one-pass
  pair table (`corpus/query/graph.RelatedIndex`), which is what makes 8,000 entities minutes, not hours.
* `views-fast` (`*:10/30`, free, no lock): `home`, `hud`, `daily-hub` only, no corpus. A daily that finishes shows on Home within half an hour, not four.

`newsroom views build [--only a,b] [--dry-run] [--target staging]`; a partial build never prunes the local store. `--target staging` publishes under `staging/` for a preview deployment and keeps its own local store (`views_store_staging`), so a changed view shape can be checked before production gets it (`../guides/deploy.md`).

## Publishing and the R2 budget

Local first: each view is written to `views_store/` (registry store, derived, not backed up) before it is sent; only views whose content changed are written/sent
(`publish.stamp` keeps `built_at` while content is unchanged, so the bytes equal what is already published and `object_docs.publish` skips them by hash: no request at all;
no name-index objects are written for views). The upload goes through `R2Store` and its free-tier guard (`object_budget.py`): past 90% of the month or 3x the daily
allowance a call is refused, the view is not recorded as sent and the next run retries it.

**Class A cost** (PUT): the number of *changed* views per run.
* First full upload: about 9,900 PUT (8,000 entity views at the cap, ~250 countries, ~150 situations, ~1,200 event views for ~100 days, ~300 series, 8 singles) = **~1.0%** of the
  1 M monthly free tier, once.
* Steady state: `hud` and `home` change a few times a day (each daily, each new anomaly), ~60 countries x 3 dailies, ~15 situations x 3, 12 new event views, ~400 entities
  touched by a day's new documents, plus the series that gained a point (instruments daily): **~600-1,500 PUT a day = 18-45 k a month = 1.8-4.5%** of the tier.
* Storage: ~100-150 MB raw, ~30-40 MB gzipped, of 10 GB. Egress is free; reads are Class B (GET), cached by Next's data cache per window.
* The meter's daily cap (3x the even daily share = ~100 k) and the 90% hard stop make a mistake here bounded. Measure with `newsroom views build --dry-run` (would_upload, bytes_gz)
  and `newsroom storage status` after the first real run; replace the estimates in the registry budget and here.

## Agent endpoints: precomputed views, not a server (decision)

Two ways to serve `entity`, `about`, `timeline`, `search`, `related`, `series` from the corpus: (a) precompute per-entity agent views into R2 and have the API read them, or (b) a tiny
read-only HTTP service on the droplet behind the site's API. **We chose (a)**: no public server exposure, no always-on process to keep alive or secure, no new failure mode for the API
(the droplet down must not take `/api/v1` down), nothing to rate-limit on the box, and R2's free egress. What it costs is stated, not hidden:

* an entity view holds the **newest** material (15 documents, 10 claims, 15 events, 12 series); `about` with an older `since` answers from what is held and says so in `meta.note`;
* `search` covers **names, aliases and document titles**, never document bodies (the one question this design answers only approximately; the corpus FTS is for the server);
* only the top 6,000 entities by use are in the index; a name outside it is a 404 with a hint.

If full-text over bodies or arbitrary windows matter more than those limits, (b) is the next step and slots in behind `lib/api/ops-corpus.ts` without changing the tools (one more reader, same
results). Tools (`lib/api/ops-corpus.ts`, REST `/api/v1/{entity,about,timeline,related,series,search}`, MCP `entity`, `about`, `timeline`, `related`, `series`, `search`): every result carries
`meta.source` (the view schema), `meta.provenance` (products and documents it was derived from) and `meta.basis` (the kinds of number it holds); records carry `product`, `origin`, source URLs;
series carry `basis` and `unit`. A name that matches several entities returns `alternatives`; a country wins over a same-named place; `key` (from a result) is exact.

**Rate limits** (`middleware.ts`, `lib/api/ratelimit.ts`): a token bucket per client IP and surface, in memory per edge instance: `/api/v1` burst 40, 120 a minute; `/api/mcp` burst 30, 60 a minute.
Over the limit: `429`, `Retry-After`, `X-RateLimit-Limit/Remaining`, JSON body. Preflights and the site's own `/api/globe/*` are not limited. Middleware runs before the CDN, so cached reads count (they cost
bandwidth). The state is per instance, so the effective ceiling is higher by the number of instances until the limiter moves to shared storage (Edge Config / KV) at the same seam: only `take()` changes.

## Entity identity (the corpus fixes behind the entity views)

Names collided in the index: a country with a same-named geoledger place or profile organisation ("France", "Norway"), two profiles' spellings of one body ("Houthis" / "Houthi movement"),
a speaker and its organisation ("UN Security Council"), a chokepoint declared by two sources ("Strait of Hormuz"), an acronym ("ICC"). `corpus/identity.py`, data-driven by tables in `corpus/flags.py`:

* **Precedence** (`KIND_TIER`): when a name answers to several entities, the best kind tier wins: country > typed entities (org, person, place, ...) > untyped speaker (`actor`) > free-text `topic`.
  What is left after that (two typed kinds sharing a name, a person and a place) stays reported as ambiguous, never guessed.
* **Merging** (`MERGE_FAMILY`): declarations of one family are one entity when the *name* of one is a name or alias of the other (lab merges into org); an untyped speaker folds into the one typed
  entity answering to its name. Geoledger assets and registry capitals never merge on a name. The lowest-ranked declaration names the merged entity; the others' ids remain resolvable
  (`entity_merge`; `resolve.find` follows them) and every asserted id is rewritten to the canonical one. If a revision later *splits* an identity, the incremental build restarts from nothing
  (rows already folded together cannot be un-merged in place; `identity.merge_is_monotone`).
* Measured on the dev corpus (2,464 entities): unresolved names 469 -> 460, "Strait of Hormuz" (20 uses) and "Houthis" (11) no longer ambiguous. The server's 1,177 is re-measured by the
  first build after deploy: the schema version moved to 2, so `corpus-build` rebuilds from nothing and prints `unresolved names:` (and `newsroom corpus stats` lists the rest with reasons).

## Server commands

```
cd ~/Algent/backend
.venv/bin/python -m algent_backend.cli newsroom corpus build --full        # once after deploy (schema 2; also prints the new unresolved count)
.venv/bin/python -m algent_backend.cli newsroom views build --dry-run       # what would upload: views, bytes, Class A
.venv/bin/python -m algent_backend.cli newsroom views build                # build, store in views_store/, send what changed
.venv/bin/python -m algent_backend.cli newsroom views stats                 # per family: count, bytes, largest; the R2 guard's month so far
.venv/bin/python -m algent_backend.cli newsroom views show country/FR      # one stored view
~/Algent/infra/server/install_schedules.sh                                  # (sudo) installs the new timers `views` and `views-fast`
```

## Left open

* The two archive scans (situation streams, event views) re-read every daily each full run; a per-file mtime cache is the fix when the archive reaches thousands of files.
* `hud` and `country` fold in the live anomalies as of the build (at most 30 minutes old for the HUD); the panel route overlays the live count.
* Entity views are capped by use, so rarely-mentioned entities are only in the corpus; widen `ENTITY_VIEWS_MAX` or add (b) if agents need them.
* The site has no CI type-check or unit tests (foundation §6, threat 10): `view-check.mjs` is the first executable check of the site's lib code; it needs `npm install` once.
