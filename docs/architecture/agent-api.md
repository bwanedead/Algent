# Agent API — the site as a resource for AI agents

> Code: `sites/ohmega-monster/lib/api/` (ops, router, MCP), `app/api/v1/`, `app/api/mcp/`, `app/developers/`,
> `app/llms-full.txt/`, `middleware.ts`. Human guide: `/developers`. Direction: serve agents from the claim/profile
> corpus (the corpus is the asset); monetization later, behind the seam below.

## Principle

The API serves the **documents the site already publishes** (`published_intel_documents` / `published_articles`,
read through `lib/store.ts`; see `published-content.md`). It adds filtering, paging, stable ids, links and an
envelope, and re-derives nothing. So the API cannot disagree with the pages, there is no second pipeline, and a
publish is visible in the API within the site's 300 s revalidate. Read-only, public, no auth, CORS `*` on GET.

## Layout

| Module | Role |
|---|---|
| `lib/api/util.ts` | `ApiResult`, `ApiError`, doc/param/pagination helpers |
| `lib/api/envelope.ts` | the response contract: envelope, CORS, cache headers, errors |
| `lib/api/ops-desk.ts` | daily, theaters, briefs, Pulses, statements, actors, changes, forecasts |
| `lib/api/ops-content.ts` | articles (markdown + claims twin), search |
| `lib/api/ops-data.ts` | instruments, live events |
| `lib/api/router.ts` | THE route table (path, summary, params, op): feeds dispatch, `/index`, `/developers`, OpenAPI |
| `lib/api/openapi.ts` | OpenAPI 3.1 built from the route table |
| `lib/api/mcp.ts`, `mcp-tools.ts` | hand-rolled MCP server (JSON-RPC) and its tools: adapters over the same ops |
| `lib/api/guide.ts` | `/llms-full.txt`, generated from routes + tools |

Adding an endpoint = one op + one `ROUTES` entry (+ optionally an MCP tool). Server-only: nothing under
`lib/api/` may be imported by a `"use client"` component.

## REST: `/api/v1`

Envelope: `{data, meta:{as_of, source, version, cite_as, license, verification?, note?, next?}}`; errors
`{error:{code,message}, meta:{version}}` (400 `bad_request`, 404 `not_found`). `meta.source` is the published
document schema (`ohmega.daily/1`...). `cite_as` is the canonical human URL. `verification` appears in `meta` only
when the whole response has one level (instruments `measured`, live events `feed_reported`, an article's status);
daily developments and dossier timeline rows carry their own `researched|reported`. Lists page with `limit` (max
200) + opaque `cursor`; `meta.next` is the ready-made next URL.

Endpoints: `index`, `daily/{domain}[/{date|latest}]`, `theaters`, `theaters/{id}`, `briefs/{slug}`, `pulses`,
`pulses/{id}` (history + readings), `articles`, `articles/{slug}`, `statements?actor=&since=&signal=`, `actors`,
`actors/{iso}`, `instruments`, `instruments/{id}`, `live/events?kind=&since=&severity=`,
`assets?bbox=&type=&country=&status=&has_events=` and `assets/{id}` (the geoledger, `ops-assets.ts`, see `geoledger.md`: places
with the latest status and its claimant; a claim is never a confirmation; at least one filter required), `search?q=&type=`,
`changes`, `forecasts`, plus `openapi.json`.

Data sources per endpoint: daily/Pulses/changes/forecasts/briefs/actors are the `data/*` feed documents; theaters
the `theaters/*` dossiers (the drawing `map` is dropped; `places[]` has coordinates); statements the `record.json`
ledger (`lib/record.ts`, 60-day window); articles `lib/articles.ts` + the `data/articles/<slug>.json` twin (claims
with grade and sources); live events `lib/live.ts` (`live_events`, last 400); search a bounded in-memory match over
titles/headlines/names (no new index).

**Instruments caveat.** The instruments store is not published as its own document. `/instruments` serves (a) the
trackers in the latest daily report's `numbers.trackers` (id = catalog series id; changes, `unusual`, spark) and
(b) our own `live_stats` series (ship counts, last ~45 days, full points). A full multi-year instrument history
needs a publish step (a `data/instruments/<id>.json` feed from `instruments/store.py`); then `instrumentOp` reads it.

**Caching.** Handlers are `force-dynamic` and send `public, s-maxage=300, stale-while-revalidate=3600`, so Vercel's CDN
serves repeats; underlying fetches use the site's data cache (300 s). 404s cache 60 s, errors not at all.

## MCP: `/api/mcp`

Streamable HTTP, stateless, JSON replies only (no SSE, no sessions). `POST` JSON-RPC 2.0: `initialize` (negotiates
2025-06-18 / 2025-03-26 / 2024-11-05), `ping`, `tools/list`, `tools/call`; notifications get 202; `GET`/`DELETE` 405.
A failing tool returns `isError: true` text (so the model can recover); unknown tool/method are JSON-RPC errors.
Tools (all `readOnlyHint`): `get_daily`, `list_theaters`, `get_theater`, `list_pulses`, `get_pulse`, `search`,
`get_statements`, `get_live_events`, `get_live_anomalies`, `get_assets`, `get_instrument`. Results are one JSON text block with `as_of`, `cite_as`,
`license`; `get_daily` / `get_theater` / `get_pulse` are compacted (`view=full` for the whole daily) and any result
is cut at 30 000 characters with a pointer to the REST twin. Client setup is on `/developers#mcp`.

## Discovery

`public/llms.txt` (hand-written pointers), `/llms-full.txt` (generated), `/api/v1/index`, `/api/v1/openapi.json`,
`/developers`, `<link rel="alternate" type="application/json">` on the daily, theater, actor, Pulses and article
pages (and the root), `robots.ts` (allows `/api`), sitemap entry for `/developers`.

## Keys and monetization (the seam, not built)

Everything public passes `middleware.ts` (`matcher: /api/:path*`) via one function, `gate`. To add a keyed tier:

1. In `gate`, read `X-Api-Key` / `Authorization: Bearer`, validate against an edge-safe store (Edge Config / KV),
   and return 401/429 or tag the request with `x-ohmega-tier`.
2. Tier-dependent cache: keyed requests must vary the CDN cache (`Vary: x-ohmega-tier`) or skip `s-maxage`.
3. Tier differences belong in the ops via an `Args` field (e.g. deeper `limit`, full history, bulk export), never in
   forked handlers. `LICENSE` in `envelope.ts` is the terms text; update it with the tier.
4. Soft rate limiting (per IP/key) also goes in `gate`; today the CDN cache is the only protection.

## Unverified / left

Written without a build or runtime: Next 14 handler signatures follow the existing `app/feeds/[...path]` route, but
`next build`, the CDN headers and an MCP client handshake still need a first run. No tests (handlers are thin and
the site has no TS test harness).
