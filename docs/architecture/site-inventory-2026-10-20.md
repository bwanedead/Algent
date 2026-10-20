# Site inventory, 2026-10-20 (read-only audit)

> Purpose: one factual inventory of everything www.ohmega.monster publishes, so a single information architecture can be designed from it.
> Method: read of `sites/ohmega-monster/` (routes, components, `lib/`), the producers in `backend/algent_backend/`, `docs/architecture/`, `infra/server/`,
> plus the live site fetched with curl on 2026-10-20 (~08:30-10:00 UTC; Daily part 1 published, part 2 not yet due, AI daily for the 20th not yet due).
> Nothing in the repo was edited to produce this. Statements marked **(inference)** are my reading, not something a file or the live site says outright.
> Paths are repo-relative; `S/` = `sites/ohmega-monster/`, `B/` = `backend/algent_backend/`.

Contents: A products, B how theaters work, C visuals, D stat honesty audit, E navigation, F observations.

---

## Part A. Products (the unique things we produce)

### A0. Pipeline in one picture

```
FREE collectors on timers                      PAID, unattended (watchdog $15/run, $40/day)         PAID, operator-run only
ioda/usgs/adsb/firms/ais live feeds            05:00 menu        -> Headlines (+ X roundup)          newsroom run  -> Articles
instruments 6h, statements 6h, sanctions 6h    05:30 daily-1     -> Geopolitics Daily part 1          intel brief   -> Briefs
calendar 04:40, markets 4h, ai-bench 12h       07:30 markets-daily -> forecasts + paper trades        pulse reassess -> Pulses (no timer)
flows 15 min, library crawl 4h, backup 06:15   09:00 ai-daily    -> AI Daily                          actors fetch  -> Actor profiles (no timer)
ai-discovery 06:50 (capped < $0.10/day)        17:30 daily-2     -> Geopolitics Daily part 2 (append)
              |                                              |
              +-------> Postgres rows + JSON docs + Storage bucket `published-assets` <-------+
                                 |  (Next.js reads Supabase, ISR 300 s, S/lib/store.ts)
                                 +-> pages, /data/* feeds, /api/v1/*, /api/mcp, /feed.xml, llms.txt
```

Sources: `infra/server/install_schedules.sh`, `infra/server/jobs.sh`, `B/ops/schedule.py`, `B/agent_system/agents/intel/flags.py` (EDITIONS, AI_DAILY_UTC=09:00, AI_DAILY_SCHEDULED=True), `B/ops/flags.py` (MENU_UTC=05:00), `B/markets/flags.py` (DAILY_UTC=07:30).

Storage vocabulary used below:
- **doc** = row in Supabase table `published_intel_documents`, keyed by path (read by `S/lib/store.ts` `intelDoc`).
- **table** = a dedicated Supabase table read with `dbRows` (`live_events`, `live_stats`, `live_anomalies`, `maritime_events`, `sanctions_events`, `calendar_items`, `geo_assets`, `geo_asset_events`, `geo_grid`).
- **bucket** = public Storage bucket `published-assets` (images, daily visual specs, live snapshots under `live/`).
- Schema ids come from the writer module; where a product has none, "none (plain JSON)" is stated.

### A1. Editorial products

| # | Product | What it is (one line) | Backend producer | Cadence / cost | Storage path / table | Schema id | Every site route and component that shows it |
|---|---|---|---|---|---|---|---|
| 1 | **Geopolitics Daily** | One report per UTC day: headline, "day in 30 seconds", one section per theater in focus, Around the world sweep, market view, watch/quiet lists. Built in parts that append to one record. | `B/agent_system/agents/intel/daily.py` (`produce_daily`), `daily_editions.py` (part 2), CLI `newsroom intel daily --domain geopolitics --research --edition N` | Part 1 05:30 UTC (Europe/Asia), part 2 17:30 UTC (Americas). **Paid**, timers `ohmega-daily-1/2` via `newsroom schedule run` | doc `daily/geopolitics/<date>.json`; feed copy `data/daily/geopolitics/<date>.json` + `latest.json`; visuals/specs in bucket `/analytics/daily/geopolitics/<date>/`; internal `intel_store/daily_drafts/` | `ohmega.daily/1` (drafts: `ohmega.daily.drafts/1`) | `/geopolitics`, `/geopolitics/[date]` (`S/app/geopolitics/GeopoliticsDay.tsx` -> `components/DailyReport.tsx`); Home masthead headline + `TheaterRank` + `ChartOfDay` + glance "Theaters escalating" cell (`S/app/page.tsx`, `components/home/*`); `/intel` Archive list (14 dates, geopolitics only); `/globe` HUD panels "Today's report" and "Theaters" (`lib/globe-hud.ts`); country panel "Briefs" (`lib/globe-briefs.ts`); theater dossier "Latest" and day-by-day history (`lib/theater-history.ts`); `/intel/events/[date]/[theater]/[n]`; API `/api/v1/daily/geopolitics[/date]`, MCP `get_daily`, `/data/daily/...`, `/data/intel.json`, `/data/changes.json`; sitemap |
| 2 | **AI Daily** | Same recipe over the AI desk's own sources (14 AI feeds + Hacker News class); no sweep, no Spotlight, no statements extraction. | same `daily.py` with `--domain ai` (`B/agent_system/agents/intel/domains.py`), sources `B/library/ai_sources.py` | 09:00 UTC, one part a day. **Paid**, job `ai-daily` (authorised 2026-10-18 per flags comment) | doc `daily/ai/<date>.json`; heat boards in `boards/ai/` | `ohmega.daily/1` | `/ai`, `/ai/[date]` (`S/app/ai/AiDay.tsx` -> same `DailyReport`), `DomainSwitch` toggle on both dailies, nav "Daily" lights up on `/ai`; `/intel` door "AI Daily"; AI theaters' dossiers merge its sections into their history (`lib/theater-history.ts` reads both domains); API `/api/v1/daily/ai`. **Not on Home, not in the globe HUD, not in the `/intel` Archive list.** Only one report exists so far (2026-10-19, published 09:59 UTC) |
| 3 | **Daily section** (one theater, one day) | The unit inside a Daily: claim, bottom line, developments (researched/reported), since-yesterday changes, on-record, pulses, numbers, map, key figures, visuals, outlook. `updates[]` nest part-2 additions. | `daily.py` section writer + `numbers.py`, `on_record.py`, `geo.py`, `visuals.py`, `sensing.py` | with each Daily | inside the Daily doc | `ohmega.daily/1` | `components/DailyTheater.tsx` (only place the whole section renders); fragments of it reappear in A1 #4-6, #14, #17 |
| 4 | **Theater dossier** ("living file") | Deterministic aggregation of every Daily section, brief, board, forecast and Pulse for one theater, plus one model-written primer. | `B/agent_system/agents/intel/dossier.py` (`build_all`), `primers.py` (model, <=120 words, rewritten weekly), written by `B/publishing/intel_page.py` `publish_intel` | no timer of its own; rebuilt by every `publish_intel` (daily, menu, pulse, brief runs) | docs `theaters/<id>.json`, `theaters/index.json` | `ohmega.dossier/1`, `ohmega.dossier.index/1` | `/intel/theaters/[id]` (`S/app/intel/theaters/[id]/page.tsx` + `components/dossier/*`), `/intel/theaters` index, `/intel` directory list, `/intel/graph`, Home door + `TheaterRank` links to the Daily not the dossier, Daily section kicker "dossier ->", `ActorStrip`, API `/api/v1/theaters[/id]`, MCP `list_theaters`/`get_theater` |
| 5 | **Theater history** | Every past Daily section of a theater, newest first, each collapsed. | not produced: read at render from the Daily docs | n/a | reads `daily/geopolitics/*` and `daily/ai/*` | n/a | `components/dossier/TheaterHistory.tsx` (dossier only) via `lib/theater-history.ts` |
| 6 | **Dossier timeline** ("How we got here") | Developments from all Dailies and briefs merged on one list. | `dossier_timeline.py` (merge rule), inside `dossier.py` | with the dossier | inside `theaters/<id>.json` (`timeline[]`) | `ohmega.dossier/1` | `components/dossier/DossierTimeline.tsx` (dossier only). **Second timeline on the same page as #5** |
| 7 | **Briefs** (deep brief) | Occasional deep analysis of one theater with scored judgments. Legacy: 5 exist, newest 2026-10-01. | `B/agent_system/agents/intel/desk.py`, `brief.py`; CLI `newsroom intel brief` | **Operator-run only**, no timer | doc `briefs/<slug>.json`; feed `data/briefs/<slug>.json` | `ohmega.brief/1` | `/intel/briefs/[slug]` (`S/app/intel/briefs/[slug]/page.tsx`, 408 lines, has its own on-record, Pulses, actor map), linked from Daily "Deep brief ->" (`DailyTheater.tsx`), `TheaterHistory`, `DossierOutlook`; sitemap; API `/api/v1/briefs/{slug}`. Footer "Briefs" link and `/intel/briefs` redirect to `/intel/theaters` |
| 8 | **Pulses** | A persistent 0-100 model-assessed reading of one question about a situation, with band, 7-day velocity, history. 33 exist, 30 assessed. | `B/agent_system/agents/pulse/*`; proposed by the Daily (`PulseProposal`, `promote_ready_quietly` at `B/cli/newsroom/intel.py:373`), moved by article runs and `newsroom pulse reassess` (docstring says weekly; **no timer exists** in `install_schedules.sh`) | event-driven / manual. **Paid** (model) | Postgres Pulse tables (migrations 001, 003); snapshot docs `snapshots/<slug>.json`; feeds `data/pulses.json`, `data/pulses/<id>.json`; label cache `intel_store/pulse_labels.json` | `ohmega.intel/1` (snapshot), `ohmega.pulses/1`, `ohmega.pulse/1`, `ohmega.pulse_labels/1` | `/pulses` (`PulseWall`), Daily per-theater expander "Pulses (n)" (`PulseTiles`) and "All theaters side by side" table (`DailyGlance`), dossier `DossierPulses`, brief page, actor page, Home glance cell (`pulseCell`), `/intel` door hint, globe HUD "Pulses" panel + theater card + country panel, `/intel/forecasts` link, API `/api/v1/pulses[/id]` |
| 9 | **Forecasts (brief judgments)** | Probability statements from briefs, kept for scoring. 10 open, 0 resolved ("the record starts now"). | `B/agent_system/agents/intel/forecasts.py` | produced only when a brief is written (last 2026-10-01) | `intel_store/forecasts.jsonl` -> feed `data/forecasts.json` | `ohmega.forecasts/1` | `/intel/forecasts` (`SituationForecasts`), dossier `DossierOutlook`, API `/api/v1/forecasts`, `/data/changes.json` |
| 10 | **Track record / paper trader / market view** | Our blind forecasts vs Polymarket prices (Brier), plus a trading agent on $10,000 of pretend money. Second forecasting system, separate from #9. | `B/markets/` (`mirror.py` free, `desk.py`/`score.py` model) | mirror every 4 h (free, `ohmega-markets`); `markets-daily` 07:30 UTC **paid** | doc `data/track-record.json` | `ohmega.track-record/2` | `/intel/track-record`; Daily `DailyMarketView` ("Where we disagree with the market"); HUD "Paper trader" panel (`TraderPanel`); `/intel` doors "Track record" and "Forecasts"; API `/api/v1/track-record` |
| 11 | **Articles** (newsroom) | Long-form researched pieces with graded claims, sources, hero image. 80 exist; newest 2026-10-03 (2 in October, 35 in July). | newsroom pipeline: CLI `newsroom run`, `B/publishing/publish.py`, `agent_twin.py` | **Operator-run only**, paid | table `published_articles` (+ revisions); doc `data/articles/<slug>.json`, `data/index.json`; images in bucket `/analytics/<slug>/` | `ohmega.article/1`, `ohmega.index/1` | `/articles`, `/articles/[slug]`, Home "Latest articles" (3) + door, `/intel` Archive link, `/feed.xml` (RSS: articles only), API `/api/v1/articles`, MCP `search`, sitemap |
| 12 | **Headlines** (formerly Radar) | The newsroom "menu": ~40 other outlets' headlines, explicitly unverified. | `newsroom run --to menu` -> `B/publishing/radar_page.py`; same menu is posted to X | 05:00 UTC daily, **paid**, `ohmega-menu` | doc `radar/<YYYY-MM-DD-HHMM>.json` (kept forever) | none (plain JSON) | `/headlines`, `/headlines/[slug]` (older editions), collapsed strip under the newest Daily (`components/DailyHeadlines.tsx`, `<details>`), `/intel` door; `/radar*` redirects here. Also feeds the geopolitics heat-board base (radar class) |
| 13 | **Statements / On the record** | Who said what, from primary transcripts, with stance scores. | `B/agent_system/agents/statements/` collect (free) + extract (paid, runs inside Daily part 1 refresh); exported by `on_record.py` | collect every 6 h (`ohmega-statements`, `--no-extract`) | doc `record.json` (60-day window, **cap 1500**) | `ohmega.record/1` | `/intel/record` (`RecordBrowser`, `ToneChart`); Daily per-theater expander "On the record (n)" (`OnRecord.tsx`); dossier `DossierRecord` ("On the record (82)"); actor page; brief page; globe country panel counts; `/intel` door; API `/api/v1/statements`, MCP `get_statements` |
| 14 | **Actors / country pages** | Power profile of each state: people, economy, trade, energy, military, leaders, ranks. 104 profiled. | `B/actors/` (no model); CLI `newsroom actors`; `B/publishing/actors_feed.py` | **no timer**; page says data fetched 2026-10-05 | docs `actors/<ISO2>.json`, `actors/index.json`; feed `data/actors/*` | `ohmega.actor/1`, `ohmega.actor.index/1` | `/intel/actors`, `/intel/actors/[iso]`, dossier `ActorStrip` + `ActorNetwork`, Daily expander "Numbers and actors" (`numbers.actors`, copied into the Daily record), globe country panel "Against the world median", `/intel` door, API `/api/v1/actors[/iso]` |
| 15 | **Entity pages** | Linked objects: event (one development), place (asset), state, theater. | derived in the site: `S/lib/entities.ts`, `lib/places.ts` | n/a | read from Daily docs, `geo_assets`, `geo_asset_events`, `maritime_events` | n/a | `/intel/events/[date]/[theater]/[n]` (`DevelopmentDetail` + `PointMap`), `/intel/places/[id]`, `/intel/actors/[iso]`, `/intel/theaters/[id]`; links made by `components/entities/LinkedText.tsx` inside Daily/dossier prose. **No index page for events or places** |
| 16 | **Relationship graph** | Force graph of states and theaters. | derived: `lib/entities.ts` `entityGraph` | n/a | from dossier + actors docs | n/a | `/intel/graph` only (linked from the `/intel` tools list) |

### A2. Data layers (measured or derived; no editorial voice)

| # | Product | What it is | Backend producer | Cadence / cost | Storage | Schema id | Site routes and components |
|---|---|---|---|---|---|---|---|
| 17 | **Geoledger and Grid impact** | Named places (power plants, ports, bases) with dated status claims; per-country share of installed generating capacity claimed/reported/confirmed damaged. | `B/geoledger/` (seeds: WRI, OSM; status events extracted inside the Daily, `daily.py` `geo_ingest`); `grid.py` | with each Daily (paid extraction); migration 009/010 | tables `geo_assets`, `geo_asset_events`, `geo_grid` | none | Daily `GridImpact` + `AssetStatusLog` ("Strike & status log" expander) + map "Infrastructure" layer (`components/map/assetLayers.ts`), `/intel/actors/[iso]` (`GridImpact`), `/intel/places/[id]`, globe country panel "Grid impact" line, API `/api/v1/assets`, `/grid/{iso}`; **not on dossiers** |
| 18 | **Instruments** | Public time series (IMF PortWatch chokepoints, policy rates, prices, gas storage...). No model. | `B/instruments/` ; CLI `newsroom instruments fetch` | every 6 h, free (`ohmega-instruments`) | local store; **not published as its own doc**; surfaces only as `numbers.trackers` inside Daily sections and via API (Daily trackers + our own `live_stats`) | none | Daily expander "Numbers and actors" (`TheaterNumbers`, `TrackerTile`), Daily visual `tracker_compare`, Home "Biggest movers" fallback (`lib/glance.ts topMovers`), API `/api/v1/instruments[/id]`. No instruments page |
| 19 | **Live feeds / /live map** | Ships (AIS), aircraft, fires, quakes, internet outages, chokepoint counts, energy. | `B/live/` ; timers per feed (ioda 15 min, usgs 10, adsb 15, firms 180) + always-on service `ohmega-ais` (`newsroom live ais`) | free; snapshots to bucket `live/` every 60 s | tables `live_events`, `live_stats`; bucket `live/{points,tiles/*,summary,fires,energy,coverage,tracks/*,flows,world}` | none | `/live` (`LiveWorldMap`, `ChokepointTiles`, `EnergyPanel`, `LayerPanel`); `LiveNowStrip` in every Daily section and dossier head; Home glance cells (4 of 6); HUD "Live counters"; `/intel` door ("6 signals now"); API `/api/v1/live/events` |
| 20 | **Anomalies ("Unusual right now")** | Where live ships/aircraft/fires depart from Ohmega's own learned hour-of-week normal. | `B/live/memory/*` (baseline.py, anomalies.py); runs inside the stream service | continuous; added 2026-10-16 | table `live_anomalies` | none | `/live` (`UnusualStrip`, rings), Daily `UnusualHere` (rollup stored in the Daily as `unusual`), dossier `UnusualHere`, HUD Live panel "Unusual now", globe country counts, API `/api/v1/anomalies`, MCP `get_live_anomalies` |
| 21 | **Maritime behaviour** | AIS gaps, ship-to-ship, identity change, sanctioned-vessel seen, loitering. "A pattern seen, not intent." | `B/maritime/` (inside `ohmega-ais`) | continuous; code added 2026-10-17 | table `maritime_events` (migration 013) | none | `/intel/maritime`, `/live` "Shadow fleet" layer (off by default), `/intel/places/[id]` vessel pages, `/intel` door, API `/api/v1/maritime`, MCP `get_maritime_behaviour` |
| 22 | **Sanctions** | Diffs of OFAC/UK/EU lists into added/removed events. | `B/sanctions/`; CLI `newsroom sanctions fetch` | every 6 h, free | table `sanctions_events` (migration 012) | none | `/intel/sanctions`, HUD "Sanctions" panel, actor page, globe country counts, `/intel` door, API `/api/v1/sanctions`, MCP `get_sanctions` |
| 23 | **Calendar** | Dated things ahead (elections, central banks, summits, UNSC, OPEC+, extracted deadlines). | `B/lookahead/`; CLI `newsroom calendar refresh`; extra "unconfirmed" items extracted from Daily text (`daily.py` `calendar_extract`) | daily 04:40 UTC, free | table `calendar_items` | none | `/calendar`, Home "Coming up, next 14 days" strip, Daily per-theater "Coming up in this theater", HUD "Coming up", actor page (`ActorWatch`), `/intel` door, API `/api/v1/calendar` |
| 24 | **AI benchmarks** | Frontier model scores (Epoch hub, SWE-bench, LMArena), open vs closed lag, lab claims kept separate. | `B/ai_benchmarks/`; `ai-discovery` = one capped model call | fetch every 12 h; discovery daily 06:50 (<$0.10) | doc `data/ai-benchmarks.json` | `ohmega.ai-benchmarks/1` | `/intel/ai` only (`LabRaceChart`, `OpenClosedChart`, `BenchCard`); `/ai` footer link; `/intel` door; API `/api/v1/ai-benchmarks`. The AI Daily's "numbers" are this layer |
| 25 | **Flows** | Ship lanes from our AIS plus annual grain and goods-export flows (UN Comtrade). | `B/flows/`; CLI `newsroom flows publish` | every 15 min free; Comtrade weekly | bucket `live/flows.json` | none | Globe "Flows" layer (`components/flows/*`) and HUD "Ships, grain and money" panel only. No page |
| 26 | **Globe / personal HUD** | Interactive globe with pinnable panels. | site-only: `S/app/globe/page.tsx`, `lib/globe-hud.ts`, `lib/globe-data.ts` | built from the other products on each ISR | none | none | `/globe` (linked only from the spinning globe on Home and on `/geopolitics`; nav "Intelligence" highlights on it). Panel "Tweets of the day" is a stub (`tweets: null`, `lib/globe-hud.ts`, `lib/globe/hud-data.ts:67`) |
| 27 | **Agent API, MCP, feeds** | Read-only JSON over the published docs; MCP server; static feeds; RSS; llms files. | site-only: `S/lib/api/*`, `app/api/v1/[...path]`, `app/api/mcp`, `app/feeds/[...path]` (served at `/data/*` via rewrite), `app/feed.xml`, `app/llms-full.txt`, `public/llms.txt` | n/a | n/a | envelope `{data, meta}` | `/developers`, `/api/v1/index` (28 routes: see `lib/api/router.ts`), `/api/mcp` (15 tools), `/data/*`, `/feed.xml`, `/llms.txt`, `/llms-full.txt`, `/sitemap.xml`, `/robots.txt`. `middleware.ts` `gate` is the future key seam (passes everything today) |

### A3. Other things that exist

| Item | What | Where |
|---|---|---|
| Scene lab | Hidden test bench for the 3D viewer, hand-authored scenes, `noindex`, **no inbound link** | `S/app/lab/scene/page.tsx` |
| Source library | Internal crawl index of trusted sources (4 h timer); never served | `B/library/` |
| Reads / corpus / claim ledger | Internal research store behind Articles and Pulses | `B/retrieval/`, `ohmega_research/` |
| X posting | Menu roundup and article announcements post to X; embeds in articles via `components/XPostEmbed.tsx`; the HUD "Tweets" panel has no feed | `B/publishing/x_*.py` |
| Insight / briefing queues | Backend queues for posts; no site surface | `B/publishing/insight_queue.py`, `briefing_queue.py` |
| Operator desktop app | Tauri/React cockpit, separate from the site | `frontend/` |
| Theme toggle | Dark amber / paper, per browser | `components/ThemeToggle.tsx` |
| Glossary terms/tips | Popover definitions (heat, coverage, pulse, spotlight, unusual) | `lib/glossary.ts`, `components/Term.tsx`, `Tip.tsx` |

### A4. Counts on the live site today (for scale)

Routes: 30 `page.tsx` files + 8 `route.ts` handlers (plus `sitemap.ts`, `robots.ts`). Daily docs: 16 geopolitics (2026-10-01..20, **no reports 6-9 Oct**) + 1 AI. Theaters: 26 (see B). Pulses 33. Articles 80. Open forecasts 10. Statements 1500 (cap). Actors 104. Briefs 5. Page weight (HTML as fetched): `/geopolitics` 2.98 MB, `/ai` 1.53 MB, `/intel/record` 1.53 MB, `/intel/maritime` 1.31 MB, `/live` 0.54 MB, a theater dossier 0.81 MB, Home 72 KB.

---

## Part B. How theaters actually work

### B1. Is there a per-theater report each day? No. Daily sections accumulate into a dossier.

1. **The board makes theaters.** `heat.run` (`B/agent_system/agents/intel/heat.py`, run as step 1 of `produce_daily`) takes the window's headlines from three tagged classes (radar editions = the menu, Wikipedia Current Events, titles of our crawled library), makes **one model call to cluster them into theaters**, reusing registry ids for continuity (`docs/architecture/intel-desk.md`). Registry: `theaters.json`. Heat per theater = share of headlines of each class (attention, not danger; the glossary says so, `lib/glossary.ts:19`).
2. **Lifecycle** (`focus.classify`): `new` (first seen, never in a Daily), `active`, `quiet` when nothing new for 7 days (`FOCUS_DROP_DAYS`), `merged`. Branch/merge lineage lives in `lineage.py`/`dossier_lineage.py`.
3. **Focus decides who gets a section** (`focus.plan`): theaters in `new`/`active` with novelty > 0 (new headlines, statements, unusual instruments since their last section), ranked heat x novelty, `--top 5` ceiling (`B/cli/newsroom/intel.py:50`). So a theater gets a Daily section **only on days it has something new**. Today: 3 focus sections + 1 Spotlight = 4. Theaters not written up are listed as `watch` ("Also watching") or `quiet` at the bottom of the Daily (`DailyWatching.tsx`). Evidence: Gaza has 7 reports in 16 days, Sudan 6, Hormuz and Ukraine 16.
4. **Part 2 appends** (`daily_editions.py`): new theaters become new sections; theaters part 1 already covered get a nested `updates[]` entry. Part 1 is never rewritten.
5. **The dossier is the accumulator** (`dossier.py`, deterministic): "A theater with at least one daily section or brief has a dossier." It aggregates reports, briefs, boards, registry, forecasts and Pulses into `theaters/<id>.json`. The only model-written part is the primer (`primers.py`, <=120 words, reused up to 7 days). `built_at` is the newest input time, so unchanged dossiers are byte-identical.
6. **What a dossier page shows and from where** (`S/app/intel/theaters/[id]/page.tsx`, top to bottom, confirmed on the live page for the Hormuz theater):

| Block (live heading) | Component | Data |
|---|---|---|
| Header: claim, "Full assessment" popover, state strip, escalation track, domain tag | `DossierTop`, `EscalationTrack` | dossier `current`, `escalation_history`, `domain` |
| "Live now" strip | `LiveNowStrip` (client fetch of live snapshots) | live bucket |
| "Unusual in this theater" | `UnusualHere` | `anomaliesIn(d.map.bbox)` (live, now) |
| Lineage | `DossierLineage` | `lineage` |
| "Hottest Pulse" chart | `DossierPulses` | `d.pulses` + latest snapshot |
| "Latest" | `TheaterLatest` | newest Daily section (via `theaterDays`) |
| "Timeline: every day on file" (15 days, each a collapsed `<details>`) | `TheaterHistory` | every Daily section of both domains + briefs |
| Map | `DossierMap` -> `GeoMap` | `d.map` (places aggregated, 14-day half-life) |
| "Background in 60 seconds" | `DossierPrimer` | model primer |
| "Who is doing what to whom", "...by the numbers", "6 states involved" | `ActorNetwork`, `ActorStrip`, `StatesInvolved` | relations from briefs, developments, actors docs |
| "On the record (82)" | `DossierRecord` | `on_record` (<=150) |
| "How we got here" | `DossierTimeline` | merged timeline |
| "The numbers" | `DossierFigures` | `key_figures` series across days |
| "Where it's heading" | `DossierOutlook` | outlook, forecasts, indicators |
| "Related theaters" | `RelatedTheaters` | `lib/entities.ts` |

   **What is not on a dossier:** the Daily's visuals (timeline/mapstory/network/flow/tracker_compare/scene3d/charts), Numbers and actors panel, Grid impact, Strike & status log, Coming up. Those exist only inside the Daily section. The live Hormuz dossier contains zero `geo-figure` visuals.
7. **Overlap on the dossier page itself:** "Latest" repeats the top four developments of the newest Daily section; "Timeline: every day on file" and "How we got here" are two timelines; "On the record" repeats the Daily's per-theater expander; the Pulses block repeats the Daily's.

### B2. Counting: three different "theater" universes

| Where | Number shown today | What it counts |
|---|---|---|
| Home masthead link / glance cell / `TheaterRank` (`components/home/Hero.tsx`, `lib/glance.ts:113`) | "4 theaters, 3 escalating" | sections in the newest geopolitics Daily (includes the one-day Spotlight; changes after part 2) |
| Home door, `/intel` directory, `/intel/theaters` claim (`lib/sections.ts:50`) | "26 theaters, 13 escalating" | every non-merged dossier in the index, all domains |
| `/intel/graph` | "20 theaters" | theaters with graph ties |

The 26: 9 long-running geopolitics theaters (multi-day), **10 Spotlight one-day theaters** (`thr_spot_*`, each 1 report, e.g. France supermarket cyberattack, North Korea SLCM test), **5 `ai`-domain theaters** (1 report each, 2026-10-19) and **2 legacy `technology`-domain AI theaters** (`Frontier AI race...`, `Rogue AI agents...`; 0 reports in the Daily record, only an old brief). 9 + 10 + 5 + 2 = 26 (the Phobos theater is one of the 10 Spotlights). Of the "13 escalating", only 3 are long-running geopolitics theaters (Hormuz, Ukraine, Sudan); 5 are Spotlight theaters marked `rising` after a single report (Iraq deputy premiership, Argentina-UK, France cyberattack, North Korea SLCM, Pakistan KP) and 5 are AI-related (4 `ai`, 1 `technology`); several of these show "not assessed" for their top Pulse. Row labels show the raw domain string (`geopolitics`, `ai`, `technology`, or blank for Spotlight) in a small tag (`components/dossier/TheaterRows.tsx:41`).

### B3. Do AI theaters exist? Yes.

- The AI desk has 7 standing **topic areas used as lenses only** (frontier labs race; compute/chips; policy/law; AI in security; open weights; AI economics; safety) in `domains.py`; theaters stay emergent. The AI board is stored in `boards/ai/`; the registry is shared and each theater carries `domain`; the AI board sees only theaters whose domain is exactly `ai` (`domains.owns`), geopolitics keeps all legacy labels. **(inference)** that is why the two older `technology`-labelled AI theaters are orphaned from the AI Daily (0 reports) and the AI desk created fresh theaters on 2026-10-19 for the same subject matter.
- Shown at: `/ai[/date]` (sections), `/intel/theaters` index and `/intel` list (**mixed in with geopolitics, no filter, only a tiny domain tag**), `/intel/theaters/<id>` dossiers, `/intel/graph` (**inference**: included by registry). Not shown on Home `TheaterRank` (reads `latestDaily("geopolitics")` only), not in the globe HUD Theaters panel (geopolitics only, `lib/globe-hud.ts:25 DOMAIN`).
- Heat is a share within a domain's own headline classes, so AI heat (49.6, 19.8, 10.6) and geopolitics heat (5.7, 3.9, 2.1) are **different scales**, yet `/intel/theaters` sorts both by severity then heat (`app/intel/theaters/page.tsx` `bySeverity`).

### B4. Spotlight, "Around the world", Pulses

| Thing | Mechanism | Shown where |
|---|---|---|
| **Around the world** (sweep) | `sweep.py`: ONE cheap model call over free material of the last ~48 h that the focus did not cover (non-focus theater headlines, library titles no theater claimed, statements, flagged instrument moves). Region-grouped one-liners, each needs a source URL that was in the material and valid ISO2 countries. Geopolitics only (`Domain.sweep=False` for AI). `SWEEP_ENABLED=True`. | Daily only: `DailySweepBlock` ("Around the world"); API `daily.sweep`. Today: 6 regions x 1 item |
| **Spotlight** | The same sweep call may nominate ONE under-covered item; with `--research` it gets a full researched section (`SPOTLIGHT_SECTIONS=1`, a deliberate budget cap). A nominee that is not an existing theater becomes a new ad-hoc registry theater `thr_spot_<slug>` that then has a dossier like any other. | Daily: section marked `spotlight: true` with a "Spotlight - an under-covered story, researched in full" label (`DailyReport.tsx`), item tag in the sweep list. Afterwards the theater appears in every theater list with 1 report. **Result: 10 one-day theaters in 10 days** |
| **Pulses** | See A1 #8. They are attached to theaters by name (the section writer names which listed Pulses it bears on); positions are model-assessed, deltas computed from the store. Pulses are created from `PulseProposal`s, not from theaters, and outlive them; a Pulse not reassessed in >2 days shows "last read N Oct" in the Daily (`staleSince`, `DailyVisuals.tsx`). | `/pulses` and 8 other places |

---

## Part C. Visuals

### C1. Visual forms: producer, where rendered, where collapsed

Planning: ONE planning call over the day's sourced facts proposes 0-3 visuals per edition run (`VISUALS_MAX_PER_DAY=3`, `intel/flags.py`; today's report produced exactly 3 for 4 sections: Ukraine = `schematic`, Hormuz = `tracker_compare`, Sudan = `mapstory`, Phobos none). Record: section `visuals[]`.

| Form (`kind`) | Producer | Hosting | Renderer | Routes that render it | Collapsed or deferred? |
|---|---|---|---|---|---|
| `timeline` (native, has `spec`) | `timeline_spec.py` + `native_forms.py` (structured model call, grounded mechanically) | bucket `/analytics/daily/<domain>/<date>/<id>.timeline.json` + `.svg` still | `NativeTimeline.tsx` | Daily only | **COLLAPSED**: `components/DailyFigure.tsx:58-67` wraps it in `<details className="geo-figure geo-figure-optin">` with summary "Timeline: <title>" (comment: "Opt-in ... Collapsed until the reader asks"). The only visual form with a closed wrapper. Inside, each event's place/sources sit in a nested `<details className="nt-more">` (`NativeTimeline.tsx:70`) |
| `mapstory` | `mapstory_spec.py` | `.mapstory.json` + still | `MapStory.tsx` over `map/LiveMap` | Daily only | Visible, but **deferred**: fetches its spec when within 400 px of the viewport (`IntersectionObserver`, `MapStory.tsx:~250-262`), plays once when on screen. Step captions list is `<details className="ms-all">` closed unless load failed (`:228`) |
| `network` | `network_spec.py` | `.network.json` | `NativeNetwork.tsx` | Daily only | Visible; text alternative in closed `<details className="nv-all">` (`NativeNetwork.tsx:272`) |
| `flow` (native) | `flow_spec.py` | `.flow.json` | `NativeFlow.tsx` | Daily only | Visible; closed `<details className="nv-all">` (`NativeFlow.tsx:224`, open on failure). Older harness-drawn `flow` stay as images |
| `tracker_compare` | `tracker_compare_spec.py` (model picks ids, points read from the instruments store) | `.tracker_compare.json` | `NativeTrackerCompare.tsx`, `trackerChart.ts` | Daily; Home "Chart of the day" (the still preview, `components/home/Glance.tsx ChartOfDay`, `lib/glance.ts chartOfDay`) | Visible; closed `<details className="nv-all">` (`NativeTrackerCompare.tsx:217`). Line chips are toggles (user-hidden series) |
| `scene3d` | `scene_spec.py`, `scene3d.py`, `scene_preview.py` | `.scene.json` + PNG still | `Scene3D.tsx` (three.js r160 from CDN when scrolled into view) | Daily; `/lab/scene` (orphan test page) | Visible; **deferred** until in view (`Scene3D.tsx:~193-200`); alt text in closed `<details className="s3d-alt">` (`:295`) |
| `chart`, `comparison`, `map`, `scale`, `schematic`, `before_after`, legacy `flow` | `visuals.py` -> coding harness (grok/codex), static SVG/PNG, bucket `/analytics/daily/...` | image | `DailyFigure.tsx` fallback: `<img>` in a `Popover` "Enlarge" | Daily; Home Chart of the day (if it has a still); `schematic` is tagged (AI-images policy) | Visible as a thumbnail; the large view is behind a click (`DailyFigure.tsx:79`) |
| Theater maps | `geo.py`/`geo_layers.py` (validated points over Natural Earth) | inside the Daily/dossier doc (`map`) | `components/map/GeoMap.tsx` (MapLibre via `LiveMap`; `GeoMapStatic` SVG fallback) | Daily section, dossier (`DossierMap`) | Visible. User toggles for "disputed areas" and "Infrastructure" and "nearby traffic" persisted in `localStorage` (`GeoMap.tsx:~30-49`); infra and nearby are chips, not collapsed content |
| Point maps | derived | n/a | `places/PointMap.tsx` | `/intel/events/...`, `/intel/places/[id]` | Visible |
| Live map | live bucket | n/a | `LiveWorldMap.tsx`, `LiveMap.tsx`, `LayerPanel.tsx` | `/live`; MapStory reuses `LiveMap` | Layer toggles; "Shadow fleet" layer **off by default** |
| Globe | `lib/globe-data.ts` | n/a | `components/globe/GlobeViewer.tsx`, `GlobeSpinner.tsx` (Home masthead and `/geopolitics` strip) | `/globe`, Home, `/geopolitics` | Flows layer is a button (off by default) |
| Flows overlay | `B/flows/` | bucket `live/flows.json` | `components/flows/*` | globe only | Button |
| Key figures | model-extracted from research | Daily doc `key_figures[]` | `DailyVisuals.tsx KeyFigures` (value + bar vs baseline), `DossierFigures.tsx` (mini line charts across days) | Daily, dossier | Detail in `Popover` per figure |
| Native stat charts | derived | n/a | `Sparkline`, `TheaterNumbers`, `TrackerTile`, `GridImpact`, `ActorTable`, `TrackCharts`, `TraderBook`, `AiCharts`, `ToneChart`, `PulseSpectrum`, `EnergyPanel` gas band, `MiniTrack`, `SituationDumbbell`, `IntelViz` | respective tool pages | see D |
| Article images | newsroom analytics harness | bucket `/analytics/<slug>/` | `ArticleImage.tsx`, hero | `/articles*`, Home rows (monochrome thumbnail, "AI" tag when generated) | n/a |

### C2. Exact components and props that collapse or hide visuals/figures

| File and line | Mechanism | What it hides |
|---|---|---|
| `S/components/DailyFigure.tsx:58-67` | `<details className="geo-figure geo-figure-optin">`, no `open` | **every `timeline` visual that has a `spec`** (the only visual form collapsed) |
| `S/components/DailyFigure.tsx:79` | `Popover` "Enlarge" wrapper around `<img>` | full-size view of every static chart/schematic/comparison |
| `S/components/DailyReport.tsx:166-173` | `<Expander label="All theaters side by side">` and `<Expander label="The day, in more detail">` | the cross-theater table (state/direction/Pulses/coverage) and the longer day |
| `S/components/DailyTheater.tsx:137,171,177,183,189,195,202` | `<Expander>` x7 per section ("Assessment and what changed", "More developments", "On the record", "Strike & status log", "Numbers and actors", "Pulses", "Outlook, watch list and background") | everything below the top 3 developments, **including all Numbers/trackers and the Pulses** |
| `S/components/Expander.tsx` | the shared `<details className="geo-exp">` (no `open` prop exists) | all of the above |
| `S/components/GridImpact.tsx:119` | `<details className="gi-list">` | named plants behind the grid bars |
| `S/components/numbers/TheaterNumbers.tsx:142` | `<details className="num-more">` ("three visible, the rest behind a control") | tracker tiles past the first three |
| `S/components/DailyVisuals.tsx` `PulseTiles limit` + `Popover` "+N" | overflow chip | Pulses beyond `limit` |
| `S/components/DailyHeadlines.tsx:13` | `<details className="dh">` | the day's 41 headlines under the Daily |
| `S/components/dossier/TheaterHistory.tsx:77` | `<details className="th-day">` per day | every past day's section summary on the dossier |
| `S/components/dossier/DossierTop.tsx:39,105`, `DossierFigures.tsx:59`, `DossierOutlook.tsx:68`, `DossierTimeline.tsx:68`, `ActorNetwork.tsx:223` | `Popover` | "Full assessment", background, each figure's detail, each timeline row, relations table |
| `MapStory.tsx:228`, `NativeFlow.tsx:224`, `NativeNetwork.tsx:272`, `NativeTrackerCompare.tsx:217`, `Scene3D.tsx:295`, `NativeTimeline.tsx:70` | closed `<details>` | only the text alternative / sources, not the picture |
| `MapStory.tsx`, `NativeTimeline.tsx`, `Scene3D.tsx` (`IntersectionObserver`, `rootMargin: "400px"`) | lazy fetch | not hidden, but empty (a still or spinner) until scrolled near |

### C3. Why "visuals only appear in some places"

- Native/harness daily visuals are rendered **only** by `DailyTheater.tsx` (`DailyFigure`). Nothing else imports `DailyFigure`. They are absent from the dossier, event pages, the globe, `/ai`'s theater dossiers and the API's human equivalents. Home shows a single still of one of them.
- The maximum is 3 per edition run across all sections (a deliberate spend bound), so most sections have none (Phobos: none; AI Daily: 2 for 5 sections; geopolitics 3 for 4).
- Maps are the only visual every section gets (when it has validated points); they exist on the Daily and dossier but are drawn by two different wrappers fed from different data (`t.map` vs `d.map`).
- Tool pages each have their own charts (track record, AI benchmarks, tone, live) unrelated to the Daily's.

---

## Part D. Every number shown to readers (the honesty audit)

Legend for **Basis**: OFF = official or third-party figure; OUR-COUNT = our count from partial-coverage sensors (a minimum); OUR-DERIVED = our own derivation or estimate; MODEL = model-generated; MIXED = see row.
Collection start dates found: Daily docs from **2026-10-01** (theaters first seen 2026-09-28, no reports 6-9 Oct); live feeds and our AIS daily series from **2026-10-11** (earliest `period` returned by `/api/v1/instruments/live_*`, 10 days of data on 2026-10-20); live-memory baselines and anomaly detector code from **2026-10-16** (commit date); maritime detectors **2026-10-17**; sanctions events from **2026-10-01** (UK/EU 30-day backfill on first run; OFAC from first copy); paper trader **2026-10-18** ("Trading since 2026-10-18" on page); AI benchmark tracker **2026-10-17** (Epoch is backfilled; LMArena and lab claims are forward-only); flows **2026-10-18**; actors data fetched 2026-10-05. Hour-of-week baselines need `MIN_WEEKS = 3` (`B/live/memory/flags.py:31`) of history, so **(inference)** they cannot be mature before about 2026-11-01 to 11-06; until then every ring is `learning` (confidence halved).

### D1. Home and Daily headline numbers

| Stat (as shown) | File:line | Claims | True basis | Source | Baseline | Disclosed in UI? | Verdict |
|---|---|---|---|---|---|---|---|
| "Strait of Hormuz transits **0 ships / day -100% vs usual**" (Home glance cell 2) | `S/lib/glance.ts:32-46` (`chokepointCell`), `lib/live-shared.ts:107` (`shipTiles`), render `components/home/Glance.tsx` | Traffic through Hormuz collapsed to zero | OUR-COUNT from aisstream volunteer coastal receivers; Hormuz is poorly heard | `live_stats` series `live_ais_hormuz_transits`, source aisstream.io | median of up to 14 completed days before the latest, **minimum 5 days** (`MIN_DAYS_FOR_USUAL`), so on 2026-10-20 it is a median of ~8 days of our own data: series 0,0,1,1,2,3,0,0,0 gives a median of 0.5, displayed as "usual about 1", so 0 reads as -100% | Band subtitle says "our own counts, against their usual" (`Glance.tsx:19`). **No coverage caveat on Home.** The caveat exists only in the tracker popover ("Coverage is partial, so read the trend") and `/live` "How to read this" | **MISLEADING.** The truthful collapse is IMF PortWatch (2/day, about -97% y/y, in the same Daily). A count of 0 vs a median of 1 over 8 days of volunteer-receiver data is noise presented as -100%. The cell also picks "the chokepoint whose latest day departs furthest", a selection effect |
| "Tankers in Hormuz **0 now** / live count" | `lib/glance.ts:49-57` (`tankersCell`) | Zero tankers in the strait | OUR-COUNT (live board, same receiver limits) | `summary.json` gates | none | "live count" only | MISLEADING (same reason; presented as a fact about the strait) |
| "Military aircraft **42 seen / day +38% vs usual**" | `lib/glance.ts:59-78`, `lib/globe-hud.ts:87` | 42 military aircraft seen per day | OUR-DERIVED: sum over 6 regions of each region's **day maximum of aircraft in the air at once** (`B/live/feeds/adsb.py:5`, series `live_mil_*`), shown for the last **completed** day. Receiver-coverage dependent (military flights often silent) | adsb.lol | median of <=14 earlier days, min 5, our data since 2026-10-11 | label "seen / day" is wrong (it is a sum of simultaneous maxima, not unique aircraft); no caveat on Home or HUD; `/live` says "a count is a minimum" | MISLEADING label and baseline |
| "EU gas storage **74.6 % full +0.7 pts wk**" | `lib/glance.ts:80-95`, `components/live/EnergyPanel.tsx` | EU storage fill | OFF | GIE AGSI+ | prior week; `/live` also shades the range of earlier years | credit shown on `/live`; Home just says source-less "live" | OK (add credit/date) |
| "Iran Proxy Axis - Escalation **98 / 100, +8 pts 7d**" | `lib/glance.ts:96-111` | Escalation is 98 of 100 | MODEL (LLM-assessed 0-100 reading; delta computed from the Pulse store) | Pulse store | its own 7-day history; **Pulse created ~2026-10-01** | Pulse glossary says "gauge of how tense"; `/pulses` meta description says "Early readings - still calibrating" (not visible on page). No "model-assessed" label next to the number on Home | UNDISCLOSED as model judgment on Home |
| "Theaters escalating **3 of 4**" | `lib/glance.ts:113` | 3 of 4 theaters escalating | OUR-DERIVED from the newest Daily's sections; part 1 only until 17:30 UTC | Daily doc | none | footer "today's report" | Different universe from the "13 of 26" (B2) |
| "Chart of the day" title "Hormuz and Bab transits collapsed while Brent surged" | `lib/glance.ts:132` `chartOfDay`; `NativeTrackerCompare` still | A real collapse | MIXED: lines come from `public_display` instrument series (PortWatch + our AIS) indexed to 100 | instruments store | the window the model chose | caption sources listed | The chart can mix our AIS (0) with PortWatch; see D3 |
| Door hints: "26 theaters - 13 escalating", "6 signals now", "1500 statements - last 60 days", "16 dates - next 30 days", "71 additions - last 30 days", "0 markets compared - 344 open markets", "92 benchmarks - 62 labs", "104 states - 26 theaters", "41 headlines" | `S/lib/sections.ts:26-65` | counts of things | **Several are caps or windows**: 1500 = `max_statements` export cap (`record.json`), "6 signals" = number of headline strings on `/live`, "71 additions - last 30 days" while `/intel/sanctions` says "71 added ... in the last 90 days" (same 71, different windows; data begins 2026-10-01), Maritime hint is blank on the live site | various | n/a | window text only | MISLEADING where a cap reads as a total |
| Theater heat bars and "headlines per day" sparks | `components/home/Hero.tsx:79-101`, `components/dossier/TheaterRows.tsx` | importance of a theater | OUR-DERIVED: share of headlines (attention), different denominators per domain | heat board | other theaters | Home shows "escalating first, then by heat" with no definition; glossary defines heat as attention "not danger" (only in `Term` popovers) | heat reads as severity on Home |

### D2. Theater/Daily section numbers

| Stat | File | Basis | Baseline | Disclosed? | Verdict |
|---|---|---|---|---|---|
| Pulse tiles "90 out of 100, critical", "+1 vs 24h", "last read 18 Oct" | `components/DailyVisuals.tsx PulseTiles` (+ `staleSince`), `PulseTile.tsx` | MODEL | prior reading | stale marker only when >2 days | Presented as measurement; band words ("critical") are model labels |
| "Key figures" tiles ("550k families", "76 hits", "43 hotspots **+59% vs was 27 on 2026-10-12**") | `DailyVisuals.tsx:150-215` `KeyFigures` | MODEL-extracted from research text, kept only with a cited source URL; baseline is one earlier value the model picked | a single day, not a normal | "as of", source link in popover | "+59%" is a two-point comparison, not "vs usual"; looks like analysis |
| "Hormuz daily tanker transits (PortWatch) 1 vs 39 a year earlier"; "Oil flows through Hormuz 2.9 vs 20.8" | same | OFF (PortWatch) / MODEL-extracted (Kpler via news) | year-ago | source link | OK |
| Tracker tiles "now above X% of the past year" | `components/numbers/TrackerTile.tsx:36`, `B/instruments/moves.py:97-100` (`percentile_1y`) | OUR-DERIVED. The "past year" is **whatever history exists**: no minimum. For `live_ais_hormuz_transits` (9 points) the API returns `percentile_1y: 27.8` | trailing 365 days | not disclosed | **MISLEADING** for any series younger than a year |
| "unusual" flag, "outside its usual level" (`z > 2`) | `moves.py` (Z_LIMIT 2, MIN_SAMPLE 10) | OUR-DERIVED | own history | popover reason text | OK for PortWatch; for our 10-day AIS series it is statistically thin |
| Same panel shows IMF PortWatch **Bab el-Mandeb 31/day** next to our AIS **0/day**, and PortWatch **Hormuz 2** next to ours **0** | `TheaterNumbers` for the Hormuz theater (live Daily) | OFF vs OUR-COUNT | n/a | each tile has a "plain" sentence | Side-by-side contradiction with no reconciliation; third number "flows at 68% of pre-war levels" appears in dossier text |
| "Live now, in this theater: N military aircraft, tankers..." | `components/live/LiveNowStrip.tsx` | OUR-COUNT (box around the theater) | none | footer: "ones with no transponder are not seen" | OK but counts in a bbox are minimums |
| "Unusual in this theater: cargo ships 8.1x normal for 4 h (young baseline)" | `components/live/UnusualHere.tsx:30` | OUR-DERIVED vs hour-of-week normal | trailing days (learning) | "(young baseline)" and a footer paragraph | disclosed, but a ratio such as 8.1x on a 10-day baseline is fragile |
| Grid impact "**0% claimed struck - 0 MW**", "0% confirmed", "3 plants named" (Ukraine, with 76 hits reported) | `components/GridImpact.tsx:60-76` | OUR-DERIVED from `geo_asset_events` (extracted from text) | installed capacity "the ledger knows" (70 GW) | "last report 4 days ago", "of 70 GW installed capacity the ledger knows", "a party's own word" | **MISLEADING headline:** the two big numerals are only *claimed* and *confirmed*; "damage reported" (the bucket the three named plants are in) has no numeral, so heavy strikes read as 0%. Capacity is nameplate (stated in code, not on the page) |
| "On the record (16)" | `DailyTheater.tsx` | count of statements shown to the writer, per theater | n/a | label only | OK |
| Coverage spark / "Coverage = steady" | `DailyVisuals.tsx CoverSpark`, dossier | headlines per day for the theater | week | "Coverage" Term | the dossier shows `Coverage = steady` next to `Escalation rising` |

### D3. Live, globe/HUD, maritime

| Stat | File:line | Basis | Baseline | Disclosed? | Verdict |
|---|---|---|---|---|---|
| Chokepoint tiles: "**0 on 10-19, usual about 1 (-100%)**" (Hormuz), "Bab el-Mandeb 0, usual about 0", "Suez Canal 0 ... usual about 0", "Bosporus 0", "Taiwan Strait 3, usual about 0", "Malacca 52, usual 44 (+20%)" | `components/live/ChokepointTiles.tsx:42-60`, `lib/live-shared.ts:107-130` | OUR-COUNT, volunteer terrestrial AIS (aisstream), needs a coast receiver | median of up to 14 earlier completed days (min 5), ours since 2026-10-11 | `/live` "How to read this" bullet 2 (no receivers = no ships) + coverage layer; the tile itself has no caveat | **MISLEADING** where receivers are sparse. PortWatch shows Suez/Bab el-Mandeb/Bosporus with dozens of transits/day, ours 0. "in the strait now", "crossed today so far" are minimums |
| HUD "Live counters": "Chokepoint transits **55 ships/day +24% vs usual**", "Fire detections **141 per day +109% vs usual**", "Quakes 27 last 24 h", "Outages 7 ongoing" | `lib/globe-hud.ts:69-100`, `components/hud/panels/LivePanel.tsx:24-26` | OUR-COUNT: ships = **sum across all gates** (dominated by Malacca); fires = sum of the **4 watched boxes** only (Ukraine front, 2 Russian refinery belts, Gaza-Levant), not the world (`/live` header says "Fire hotspots 4,835"); quakes M4.5+ (USGS, OFF) | median of earlier days, min 5, ours since 2026-10-11; the first collection day (82 on the Ukraine-front box alone, 2026-10-11) is inside the median | none of the scope is stated on the panel | MISLEADING scope: "Fire detections" reads as global |
| "Unusual now" list and rings on `/live` ("fishing vessels 10.4x normal for 15 h ... learning 50 %") | `components/live/UnusualStrip.tsx:33`, `LiveWorldMap.tsx` | OUR-DERIVED | hour-of-week normal, learning | "learning", confidence 50 %, header "Ohmega analysis ... not a reported event"; limits list | Disclosed. All 8 visible rows are "learning" today |
| Fire hotspots (4,835), Earthquakes 27, Outages 7, Chokepoints 6, Anomalies 18 | `LiveWorldMap.tsx` layer chips | OFF (FIRMS, USGS, IODA) / OUR-DERIVED | n/a | "a fire hotspot is a satellite heat reading..." | OK |
| Maritime page "**1000 events in the last 30 days, 1000 still going**"; "AIS gap 937", "Open ocean 799" | `S/app/intel/maritime/page.tsx:23` (`maritimeEvents()`, default limit 1500, `lib/maritime.ts:64`) | OUR-DERIVED events, but the totals equal exactly **1000, which looks like the PostgREST row cap** (the code asks for 1500) **(inference)**; "still going" counts every open AIS gap (a ship that left coverage) | detector code dates from 2026-10-17, so a "last 30 days" label covers at most ~3 days **(inference)** | page says "a pattern seen, not a finding of intent"; no note that the list is truncated | **MISLEADING counts** (cap shown as total; a "last 30 days" label over ~3 days of detector history) |
| `/live` "Internet down nationwide in Guam since 17:10 UTC", quakes, heat readings | `lib/live.ts`, `LiveWorldMap` | OFF (IODA, USGS, FIRMS) | n/a | source line | OK |
| Flows panel "Chokepoints - ships a day, our AIS" and "Grain/Goods exports - UN trade statistics" | `components/hud/panels/FlowsPanel.tsx:~80-95` | OUR-COUNT (ships, `r7`) / OFF (Comtrade, reporter-declared, annual) | "usual" from lane memory since 2026-10-18 | footer: "watched N days; only what coastal receivers hear. Grain and money are a year of reported trade, not live" | Best-disclosed panel |
| Globe country panel "Against the world median" bars | `lib/globe-country.ts:30-50` `worldMedians` | OFF stats vs a median over the **104 profiled actors** (G20 + P5 + countries in the news), not the world | median of `allActors()` | tooltip says "World median" | MISLEADING label (the set is skewed to large economies); 2024-ish year stamp shown |
| Globe country counts: "N statements this week", "N sanctions events, 30 days", "N live anomalies" | `lib/globe-country.ts:55-70` | OUR-COUNT/derived | windows | labels have windows | statements capped at 1500 overall |
| HUD "Paper trader": "$X equity, -$163 on $10,000", open position P&L | `lib/globe-hud.ts traderBlock`, `TraderPanel.tsx` | MODEL decisions marked to Polymarket prices; 1 point of slippage | flat bankroll | "paper only, not advice"; curve says "day one" | OK; **history is 2 days** |

### D4. Tool pages

| Stat | File | Basis | Baseline / history | Disclosed? | Verdict |
|---|---|---|---|---|---|
| Track record: "-$163 trader P&L, worth $9,837", "-$107 fixed-rule baseline", "0% closed positions in profit (0 W 1 L)", "0 markets compared" | `S/app/intel/track-record/page.tsx:~55-100` | MODEL forecasts and trades; Polymarket prices (OFF) | trading since 2026-10-18; 1 closed position | "Paper trading only ... no money staked" | The 0% win rate is one trade; a ratio on n=1. Brier not yet defined (0 compared) |
| Trader notes "Market prices NO at 13% while desk sees 96%" | same | MODEL | n/a | page explains "desk" | "desk" is never defined |
| `/intel/forecasts` "76% chance by 2026-10-31" etc. | `SituationForecasts` | MODEL probabilities from briefs dated 2026-10-01 | none resolved | "No forecasts resolved yet - the record starts now" | Disclosed |
| `/pulses` "33 Pulses - 30 assessed - 0 calm - 100 extreme" | `app/pulses/page.tsx`, `PulseWall` | MODEL | n/a | scale words only | see D1 |
| `/intel/record`: "**1500 statements** in the last 60 days", tone dyads "United Kingdom -> Russia, 60 statements" with a stance mean | `app/intel/record/page.tsx:27`, `ToneChart` | MODEL-extracted stance (-2..+2); count is the export cap; same speaker appears under several spellings ("Volodymyr Zelensky 24" and "Zelenskyy 10", "Abbas Araghchi", "Seyed Abbas Araghchi", "Donald Trump", "Donald J. Trump") | window 60 d; tone needs >=4 statements on >=2 days | `SAID_NOTE` ("said, not true") | Cap shown as total; duplicate speakers split counts |
| `/intel/sanctions`: "71 added and 0 removed in the last 90 days" | `app/intel/sanctions/page.tsx:23,34` | OFF-derived (list diffs) | events begin 2026-10-01 | page text explains UK/EU 30-day first read and undated OFAC | "0 removed" and "90 days" overstate the window; disclosed in a paragraph |
| `/calendar`: "19 dated items from their sources", items marked "unconfirmed" | `app/calendar/page.tsx` | OFF (official schedules) + OUR-DERIVED (extracted from our own text) | n/a | "unconfirmed" tag and sentence | An unconfirmed row dated 21 Oct has "Oct. 19" in its title (extraction error) |
| `/intel/ai`: "92 benchmarks - 6,981 scores - 62 labs", "frontier is 167", "Open trails by 3.3 pts, about 5 months behind", "96% of the ceiling" | `app/intel/ai/page.tsx`, `ai_benchmarks/derive.py` | OFF scores (Epoch CC BY, LMArena, SWE-bench) + OUR-DERIVED lag/saturation | Epoch full history; LMArena and claims from 2026-10-17 | per-source freshness, STALE tags, hollow markers for lab claims | Best-disclosed tool page |
| `/intel/actors`: "largest economy among 104 actors", `#rank of N` | `app/intel/actors/page.tsx`, `lib/actors.ts` | OFF (World Bank, IMF, OWID...) | data fetched 2026-10-05 | page says latest year per figure | Rank denominators are "states with data", not the 104 |
| Theater index "13 of 26 theaters are escalating", chip "Critical", bars | `app/intel/theaters/page.tsx:60-75` | OUR-DERIVED | see B2 | key line | counts mix Spotlight/AI/legacy |

---

## Part E. Navigation as it stands

### E1. Chrome

- **Header nav** (`components/NavLinks.tsx`), one row: Home, **Daily** (`/geopolitics`; lit on `/ai*` too), **Theaters** (`/intel/theaters`), **Articles**, **Live**, **Intelligence** (`/intel`; lit for any path starting `/intel` except theaters, `/pulses`, `/calendar`, `/headlines`, `/globe`), plus ThemeToggle. 
- **Footer** (`app/layout.tsx`): Theaters, Actors, **Briefs** (-> redirects to `/intel/theaters`, so it duplicates "Theaters"), Record, RSS, Sitemap, Developers.
- **Page tag** on every page: DAILY / THEATER / ARTICLE / HEADLINES / TOOL (`components/PageTag.tsx`). The tag says "Tool" for ~15 different things.
- **Doors** (`lib/sections.ts`, `components/Doors.tsx`): the same hairline index rendered twice with different lists:
  - Home "Go deeper" (`homeDoors`, 5): The Daily, Theaters, Articles, Live map, Data & tools (`hint: ""`).
  - `/intel` "Data & tools" (`toolDoors`, 13): Pulses, The record, Calendar, Sanctions, Maritime, Forecasts, Track record, AI Daily, AI benchmarks, Graph, **Live (again)**, Actors, Headlines.
  - `Doors.tsx GLYPH` gives `/ai` the same "globe" glyph as `/geopolitics`; `/intel/ai`, `/intel/track-record` share the "pulse" glyph with Pulses and Forecasts.
  - Door hints are live counts (see D1) and only two doors (Daily, AI Daily) show a date.

### E2. Route table

| Route | Kind | Reachable from | Notes |
|---|---|---|---|
| `/` | Home | nav | dashboard: masthead, glance band, coming strip, theater rank, chart of day, doors, 3 articles |
| `/geopolitics`, `/geopolitics/[date]` | Daily | nav "Daily", Home links, `/intel` archive, DayNav | `DomainSwitch` to AI; ← → keys |
| `/ai`, `/ai/[date]` | Daily (AI) | `DomainSwitch`, `/intel` door "AI Daily" | not in nav, Home or the Archive list |
| `/intel` | directory | nav "Intelligence" | blocks: Theaters list (26), Data & tools, Archive (geopolitics only) |
| `/intel/theaters`, `/intel/theaters/[id]` | Theater | nav, Home, Daily kicker "dossier ->" | domains mixed |
| `/intel/briefs/[slug]` | Brief | Daily "Deep brief", history | `/intel/briefs` itself redirects |
| `/intel/events/[date]/[theater]/[n]` | Event | popover "Open on its own page" in a Daily | no index; popover only when theater appears once that day (`events` prop) |
| `/intel/places/[id]` | Place | Grid impact list, status log, map discs | no index; in sitemap |
| `/intel/actors`, `/intel/actors/[iso]` | Actors | footer, `/intel` door, flags | |
| `/intel/record` | Tool | footer, door | |
| `/intel/forecasts` | Tool | `/intel` door; `/pulses` page link | |
| `/intel/track-record` | Tool | door; HUD trader panel | links back to a retired `/intel/situation` (redirect) |
| `/intel/maritime`, `/intel/sanctions` | Tool | doors; `/live` and each other | |
| `/intel/graph` | Tool | **only the `/intel` tools list** | |
| `/intel/ai` | Tool (benchmarks) | door; `/ai` footer link | |
| `/pulses` | Tool | door; Daily/HUD links | not in nav; nav "Intelligence" lit |
| `/calendar` | Tool | door; Home strip "calendar ->" | |
| `/headlines`, `/headlines/[slug]` | Headlines | door; Daily collapsed strip | |
| `/articles`, `/articles/[slug]` | Article | nav | |
| `/live` | Tool | nav | |
| `/globe` | Tool | **only** the spinning globe image on Home and on `/geopolitics` (and the sitemap); not in nav or any door | |
| `/developers`, `/llms.txt`, `/llms-full.txt`, `/feed.xml`, `/sitemap.xml`, `/api/*`, `/data/*` | machine | footer (developers, RSS, sitemap) | |
| `/lab/scene` | test bench | **nothing links to it**; `noindex` | orphan |
| `/api/globe/country/[iso]` | internal JSON | HUD country panel | |

### E3. Redirects and rewrites (`S/next.config.mjs`)

| From | To | Type |
|---|---|---|
| `/intel/briefs` | `/intel/theaters` | permanent |
| `/intel/situation` | `/intel` | permanent |
| `/radar` | `/headlines` | permanent |
| `/radar/:slug` | `/headlines/:slug` | permanent |
| `/data/:path*` | `/feeds/:path*` (handler reads DB) | rewrite before filesystem |
| `/analytics/:path*` | CSP-hardened headers | headers |

Dead-label links still in the UI: footer "Briefs" and the track-record page's "Intelligence situation room ->" both resolve through a redirect.

### E4. Orphans and thinly linked pages

Nothing links to: `/lab/scene`. Linked from exactly one place: `/globe` (the spinner), `/intel/graph` (tools list), `/pulses` (tools list + deep links), `/intel/forecasts` (tools list), `/headlines` (tools list + collapsed strip), `/intel/ai` (tools list + `/ai` footer). Entity pages (events, places) have no index and are reached only through popovers/lists.

### E5. New vs stale: is freshness shown?

Present, per page and not in navigation: Home masthead date; Daily "Published 06:24 UTC" + "Researched / From headlines"; Theater index "20 Oct - 16 reports" per row; Pulses "As of ... UTC" and per-tile "last read 1 Oct"; `/live` "events updated 08:31 UTC" + per-layer ages; `/intel/ai` per-source "fetched 6 h ago" with STALE tags; GridImpact "last report 4 days ago"; Actors "data fetched 2026-10-05"; Headlines "Tue, Oct 20, 2026 - 05:02 UTC".
Absent: nothing in the header or doors signals which sections are current. Home shows "Latest articles" with the newest dated 2026-10-03 and no age cue (17 days); the AI Daily door shows "Mon, 19 Oct 2026" with no "yesterday"; Briefs (newest 2026-10-01), forecasts (made 2026-10-01), Pulses with "not yet assessed", Actors (15 days) look equally current; the Daily Archive list jumps from 5 Oct to 10 Oct without saying why.

---

## Part F. Quick observations (biggest sources of confusion)

1. **Four vocabularies for "the daily thing":** Daily, Report, Brief, Section/Update. The Daily page, the theater "Latest", the Home masthead and the HUD "Today's report" all re-present the same sentences from the same `daily` doc.
2. **"Theater" means three different sets** (4 / 26 / 20, B2), and the 26 are 9 real, 10 one-day Spotlight, 5 AI, 2 legacy AI. Spotlight creates a permanent theater every time it runs.
3. **AI is a second site inside the first:** its own Daily, theaters, dossiers, benchmarks and Pulses, yet it is only a tab on the Daily, a tool door, and unlabelled rows in the theater list; Home and the HUD ignore it.
4. **The Daily's richest content lives only in the Daily.** Visuals, numbers, grid impact, status log, coming-up exist solely in `DailyTheater.tsx`; the dossier gets text summaries and builds its own different map and figures. So the same theater has two maps, two timelines, two Pulse blocks.
5. **Only one visual form is collapsed (timeline)**, but 7 expanders per section hide everything else, and only 3 visuals are produced per edition run, so on most sections the "visual" is a map and a row of key figures.
6. **Statements appear in 6 places** (Daily expander, dossier, brief, actor page, `/intel/record`, globe counts) with the same 1500-capped ledger, and with unnormalised speaker names.
7. **Two forecasting systems:** brief judgments (`/intel/forecasts`, 10 open, dated 2026-10-01) and the Polymarket-scored forecasts (`/intel/track-record`, Daily "Where we disagree with the market"). Different pages, different "desk" probabilities, no common language.
8. **Three Hormuz traffic numbers on one screen:** PortWatch 2/day, our AIS 0/day, and the text "flows at 68% of pre-war levels" (Daily and dossier). Home headlines the one that is least reliable (our AIS, -100%).
9. **Short-history baselines are presented as "usual":** `vs usual` on Home, HUD and tiles is a median of <=14 days of our own data that started 2026-10-11; `percentile_1y` is computed over whatever exists. Only the anomaly list says "learning".
10. **Counts that are caps or windows read as totals:** 1500 statements, 1000 maritime events "still going", 71 sanctions in "30 days" and "90 days", "6 signals".
11. **Stat scopes are mislabelled:** "Military aircraft seen / day" is a sum of simultaneous maxima; "Fire detections" is four watched boxes; "world median" is a median of 104 profiled states; "Chokepoint transits" is volunteer-receiver coverage.
12. **Navigation does not match the product list:** header has 5 destinations plus a catch-all "Intelligence"; `/globe`, `/pulses`, `/calendar`, `/headlines`, `/ai` and `/intel/ai` (all prominent products) are one or two clicks deep or only reachable through a spinner/tab; the footer "Briefs" is a redirect to "Theaters"; "Live" is in the header and in the tool doors.
13. **Cadence is invisible and uneven:** Daily 2x/day paid, AI Daily 1x/day, Headlines 1x/day, Articles manual (last 17 days ago), Briefs manual (last 19 days), Pulses reassessed by hand (some "last read 1 Oct"), Actors manual (15 days), trader 2 days old, sanctions/live continuous. The UI gives no per-section "as of".
14. **Heavy pages:** `/geopolitics` ships ~3 MB of HTML (all seven expanders per section are server-rendered into the page), `/intel/record` 1.5 MB, `/intel/maritime` 1.3 MB, and `/live` resolves its map from several snapshot fetches; this adds to the "stuff everywhere" feel on a phone.
15. **Page tags do not partition anything:** one tag, "Tool", covers Pulses, Record, Calendar, Sanctions, Maritime, Forecasts, Track record, AI benchmarks, Graph, Live, Actors and the Intel directory; "Theater" tags dossiers and the index, "Daily" tags geopolitics and AI alike.
