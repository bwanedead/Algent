"""
THE PRODUCT REGISTRY. A product exists only if it is in this file (docs/architecture/foundation.md).

Everything operational about a product is stated here once and derived everywhere else (``views.py``): what the nightly backup and snapshot cover,
the envelope's per-store budgets, the systemd timers, the paid-job list, the docs table, the site contract. ``newsroom products check`` and
``tests/test_products_registry.py`` fail when the code and this file disagree, so a new product cannot be half-wired.

Adding a product: add a ``Product`` below with its stores, retention, budget, jobs and routes; add a page route and it must appear in
some product's ``site_routes``. Budgets say where their numbers come from; the 2026-10-23 sizes were measured on the server, "estimate" means
no measurement exists yet (run ``newsroom envelope --text`` and replace it).
"""

from __future__ import annotations

from . import locations as loc
from .model import Budget, Job, Product, Retention, Store

# ── jobs whose times come from a product's own flags (read lazily) ──────────────────────────────────
def _menu_at() -> str:
    from algent_backend.ops import flags

    return flags.MENU_UTC


def _daily_jobs() -> tuple[Job, ...]:
    from algent_backend.agent_system.agents.intel import flags as f

    out = [Job(f"daily-{e.n}", ("intel", "daily", "--domain", "geopolitics", "--research", "--edition", str(e.n)), at=e.utc, every_min=1440, spend="paid",
               what=f"geopolitics daily, part {e.n} ({e.label})") for e in f.EDITIONS]
    if f.AI_DAILY_SCHEDULED:
        out.append(Job("ai-daily", ("intel", "daily", "--domain", "ai", "--research"), at=f.AI_DAILY_UTC, every_min=1440, spend="paid", what="AI daily"))
    return tuple(out)


def _markets_daily_at() -> str:
    from algent_backend.markets import flags

    return flags.DAILY_UTC


def _calendar_every(minutes: int) -> str:
    """systemd minute steps stop at 59, so a longer cadence is written as an hourly step."""
    return f"*-*-* 0/{minutes // 60}:00:00" if minutes >= 60 else f"*:0/{minutes}"


def _live_jobs() -> tuple[Job, ...]:
    from algent_backend.live import flags as f

    feeds = tuple(Job(f"live-{feed}", ("live", "run", "--feed", feed), _calendar_every(m), every_min=m, lock=False, what=f"live feed {feed}")
                  for feed, m in f.CADENCE_MINUTES.items())
    return (*feeds, Job("ais", ("live", "ais"), kind="service", lock=False, what="AIS chokepoint counter (always on; needs ALGENT_AISSTREAM_KEY)"))


def _b(steady: float, warn: float, fail: float, written: float, growth: float, why: str) -> Budget:
    return Budget(steady, warn, fail, written, growth, why)


PRODUCTS: tuple[Product, ...] = (
    # ── editorial: what we write ──────────────────────────────────────────────────────────────────
    Product(
        id="dailies", title="Dailies (geopolitics, AI)", owner="agent_system/agents/intel",
        what="One report per desk per day, written in parts; the heat board, saved visuals and the situation registry live in the same store.",
        stores=(Store("intel_store", loc.intel, "ALGENT_INTEL_STORE", True,
                      budget=_b(21, 250, 1500, 80, 10, "~1.4 MB a day of dailies, boards and drafts plus ~0.3 MB of saved visuals (measured 10-23: 21 MB, 10 MB a week)")),
                Store("site_intel", loc.site_intel, "", True,
                      budget=_b(5, 200, 1000, 100, 2, "estimate: the published copy of the dailies (unmeasured; they exist nowhere else once the database is gone)"))),
        retention=(Retention("append-only", "dailies, boards, drafts and visuals are the record; ~10 MB a week is 2.8 years of headroom at the fail line",
                             "agent_system/agents/intel/daily.py::daily_dir", "on-write"),),
        irreplaceable=True, why="paid editorial work and published reports; the saved visuals exist only here (42 charts were lost when they were upload-only)",
        jobs=_daily_jobs, publishes=("daily/", "briefs/", "snapshots/", "theaters/", "/analytics/daily/"),
        site_routes=("/daily", "/daily/[desk]", "/daily/[desk]/[date]", "/daily/[desk]/archive", "/intel/briefs/[slug]", "/intel/events/[date]/[theater]/[n]"),
        feeds_from=("instruments", "statements", "library", "live", "sanctions", "calendar", "maritime", "geoledger", "actors"),
        heartbeat=("intel_store/daily/*/*.json",)),
    Product(
        id="situations", title="Situations (living files)", owner="agent_system/agents/intel",
        what="Each long-running story as one file, built from the dailies' sections; no extra cost, no store of its own.",
        retention=(Retention("derived", "rebuilt from the dailies on every daily run (theaters/<id>.json); clearing it loses nothing", "publishing/agent_feed.py::dossier_files", "on-write"),),
        why="derived from the dailies (intel_store holds the source)", manual="rebuilt on every daily run and by `newsroom publish`; no timer of its own", publishes=("theaters/",),
        site_routes=("/situations", "/situations/[id]", "/intel/graph"), feeds_from=("dailies", "actors", "pulses")),
    Product(
        id="pulses", title="Pulses (0-100 gauges)", owner="agent_system/agents/pulse",
        what="Model-assessed gauges per situation with append-only influence logs and watches; the reasoning behind every move is the asset.",
        stores=(Store("pulse_store", loc.pulse, "ALGENT_PULSE_STORE", True,
                      budget=_b(2, 50, 200, 20, 0.5, "measured 10-23: 2 MB, ~0.5 MB a week, append-only")),),
        retention=(Retention("append-only", "influences are never rewritten or removed; ~0.5 MB a week", "agent_system/agents/pulse/store.py::PulseStore", "on-write"),),
        irreplaceable=True, why="two weeks of Pulse reasoning were lost once when it was missing from the backup",
        manual="written by the daily runs (no timer of its own)", publishes=("pulses/",), site_routes=("/pulses",), feeds_from=("dailies",)),
    Product(
        id="articles", title="Articles", owner="agent_system/agents/editorial",
        what="Long-form researched pieces: leads, treatments and drafts (paid work the pipeline must never redo) and the published copy.",
        stores=(Store("draft_store", loc.draft, "ALGENT_DRAFT_STORE", True, budget=_b(5, 100, 500, 50, 1, "estimate: JSON drafts, a few a week; replace with the first envelope reading")),
                Store("treatment_store", loc.treatment, "ALGENT_TREATMENT_STORE", True, budget=_b(5, 100, 500, 50, 1, "estimate: as draft_store")),
                Store("lead_store", loc.lead, "ALGENT_LEAD_STORE", True, budget=_b(2, 100, 500, 50, 0.2, "estimate: derived leads, small JSON")),
                Store("site_articles", loc.site_articles, "", True, budget=_b(10, 200, 1000, 100, 2, "estimate: published markdown plus hero and figure images (unmeasured)"))),
        retention=(Retention("append-only", "every draft, treatment and lead is kept (lineage to its profile); a few MB a week", "agent_system/agents/editorial/draft_store.py::DraftStore", "on-write"),),
        irreplaceable=True, why="paid editorial work (memory: never redo paid work) and the published articles",
        manual="`newsroom run` by hand, irregular: an article is the operator's call", publishes=("articles/", "docs/", "/analytics/"),
        site_routes=("/articles", "/articles/[slug]"), feeds_from=("profiles",)),
    Product(
        id="profiles", title="Research profiles (the corpus)", owner="agent_system/agents/research",
        what="Every researched story's profile, claims and sources, append-only with history; the newsroom's knowledge base.",
        stores=(Store("profile_store", loc.profile, "ALGENT_PROFILE_STORE", True,
                      budget=_b(34, 300, 1500, 100, 5, "measured 10-23: 34 MB, ~5 MB a week; the asset, so the fail line is generous")),),
        retention=(Retention("append-only", "every save also writes _history/<id>/<rev>; nothing is overwritten or deleted", "agent_system/agents/research/store.py::JsonProfileStore", "on-write"),),
        irreplaceable=True, why="the corpus: it cannot be re-bought cheaply and sixteen profiles were once silently overwritten",
        manual="written by article and daily research runs", feeds_from=()),
    Product(
        id="menu", title="Menu (headlines) and run logs", owner="agent_system/runs",
        what="The newsroom menu of leads (paid, daily) and every pipeline run's log directory.",
        stores=(Store("runs_store", loc.runs, "ALGENT_RUNS_DIR", False, "run logs: rolling retention by design, indexed in runs_index.jsonl",
                      budget=_b(200, 1500, 4000, 1000, 0, "estimate: the newest 5 runs are kept (prune_runs), so size is flat; unmeasured")),
                Store("site_radar", loc.site_radar, "", True, budget=_b(2, 100, 500, 50, 0.5, "estimate: published menus, small JSON"))),
        retention=(Retention("prune", "only the newest 5 runs are kept; older history stays in runs_index.jsonl", "agent_system/runs/control_plane/layout.py::prune_runs", "on-write"),),
        irreplaceable=True, why="the published menus exist nowhere else once the database is gone; the run logs themselves are expendable",
        jobs=(Job("menu", ("run", "--to", "menu"), at=_menu_at, every_min=1440, spend="paid", what="newsroom menu"),),
        publishes=("radar/",), site_routes=("/daily/headlines", "/daily/headlines/[slug]")),
    # ── data: measured layers ─────────────────────────────────────────────────────────────────────
    Product(
        id="live", title="Live feeds (ships, aircraft, quakes, fires, outages)", owner="live",
        what="Free live feeds on timers plus the always-on AIS counter; events are snapshots, numbers go to instruments, hours feed baselines and anomalies.",
        stores=(Store("live_store", loc.live, "ALGENT_LIVE_STORE", False, "re-collected from public feeds; baselines relearn in ~3 weeks (the one real loss)",
                      budget=_b(46, 150, 500, 200, 0, "measured 10-23: 46 MB of snapshots and baselines; snapshots overwrite, hour files are pruned at 60 days")),),
        retention=(Retention("prune", "hour files older than HOUR_KEEP_DAYS (60) are deleted; event snapshots are replaced each run", "live/memory/hours.py::prune", "job:live-usgs"),),
        why="re-collectable from public feeds", jobs=_live_jobs, publishes=("live/",), site_routes=("/live",), feeds_from=(),
        heartbeat=("live_store/status.json",)),
    Product(
        id="flows", title="Flows (ship lanes, grain, money)", owner="flows",
        what="Lane aggregates from the AIS service plus the weekly Comtrade trade picture, as one document. Stored under live_store/flows.",
        retention=(Retention("overwrite", "tracker and days.json are bounded aggregates replaced atomically", "flows/store.py::root", "on-write"),),
        why="aggregates of the live stream, rebuilt as it runs",
        jobs=(Job("flows", ("flows", "publish"), "*:7/15", every_min=15, lock=False, what="ship-lane + grain/money flows document"),),
        publishes=("live/",), site_routes=(), feeds_from=("live",), heartbeat=("live_store/flows/days.json",)),
    Product(
        id="satellite", title="Satellite (Sentinel-2 chips, night lights)", owner="satellite",
        what="Change detection on watched sites from keyless imagery; stored under live_store/satellite.",
        retention=(Retention("prune", "dated chips are pruned to the KEEP_DATED (3) newest scenes per site plus the baseline", "satellite/store.py::KEEP_DATED", "on-write"),),
        why="re-observed daily; the append-only records.jsonl is small and re-derivable from imagery",
        jobs=(Job("satellite", ("satellite", "run"), "*-*-* 03:20", every_min=1440, lock=False, what="Sentinel-2 chips + night lights of watched sites"),),
        publishes=("live/", "/satellite/"), site_routes=("/intel/satellite",), feeds_from=(), heartbeat=("live_store/satellite/doc.json",)),
    Product(
        id="maritime", title="Maritime behaviour", owner="maritime",
        what="Behaviour events from the AIS stream (encounters, dark gaps, loitering, sanctioned vessels); the daily ship summaries are the long record.",
        stores=(Store("maritime_store", loc.maritime, "ALGENT_MARITIME_STORE", False, "the raw positions and 7-day event log are GB-scale and bounded by retention; the daily summaries are backed up",
                      budget=_b(50, 800, 3000, 800, 3, "estimate after compaction: profile book tens of MB + 7 days of compact log; the 1.7 GB log was the incident")),
                Store("maritime_daily", loc.maritime_daily, "", True, budget=_b(1, 100, 500, 50, 0.5, "estimate: one small summary file a day"))),
        retention=(Retention("rollup", "daily ship summaries are written then the raw event log is cut to LOG_KEEP_DAYS (7)", "maritime/flags.py::LOG_KEEP_DAYS", "job:maritime-rollup"),),
        irreplaceable=True, why="the daily summaries are the only long record of ship behaviour (backed up as maritime_daily)",
        jobs=(Job("maritime-rollup", ("maritime", "rollup", "--apply"), "*-*-* 04:05", every_min=1440, what="daily ship summaries + retention of the raw event log"),),
        publishes=("maritime/",), site_routes=("/intel/maritime",), feeds_from=("live",), heartbeat=("maritime_store/state.json",)),
    Product(
        id="sanctions", title="Sanctions", owner="sanctions",
        what="OFAC / UK / EU list diffs as designation events; an append-only event log plus one snapshot per source.",
        stores=(Store("sanctions_store", loc.sanctions, "ALGENT_SANCTIONS_STORE", True, budget=_b(7, 100, 500, 100, 0.5, "measured 10-23: 7 MB; events are append-only, snapshots replaced")),),
        retention=(Retention("append-only", "events.jsonl is never rewritten; snapshots/<src>.json are replaced atomically", "sanctions/store.py::root", "on-write"),),
        irreplaceable=True, why="forward capture: the diff history of the lists cannot be re-fetched",
        jobs=(Job("sanctions", ("sanctions", "fetch"), "2/6:25", every_min=360, what="sanctions list diffs"),),
        publishes=("sanctions/",), site_routes=("/intel/sanctions",), feeds_from=(), heartbeat=("sanctions_store/status.json",)),
    Product(
        id="calendar", title="Calendar (look-ahead)", owner="lookahead",
        what="Upcoming elections, central-bank decisions, summits, OPEC+ and extracted deadlines; append-only revisions of items.",
        stores=(Store("calendar_store", loc.calendar, "ALGENT_CALENDAR_STORE", True, budget=_b(2, 100, 500, 100, 0.3, "estimate: one revision line per changed item")),),
        retention=(Retention("append-only", "items.jsonl keeps every revision; status.json is replaced", "lookahead/store.py::root", "on-write"),),
        irreplaceable=True, why="revision history (a moved or withdrawn date) cannot be re-fetched",
        jobs=(Job("calendar", ("calendar", "refresh"), "*-*-* 04:40", every_min=1440, what="calendar refresh"),),
        publishes=("calendar/",), site_routes=("/calendar",), feeds_from=("statements",), heartbeat=("calendar_store/status.json",)),
    Product(
        id="ai_benchmarks", title="AI benchmarks", owner="ai_benchmarks",
        what="Benchmark scores (Epoch hub, SWE-bench, LMArena) and lab-claimed scores found by one capped model call a day.",
        stores=(Store("ai_benchmarks_store", loc.ai_benchmarks, "ALGENT_AI_BENCHMARKS_STORE", True,
                      budget=_b(3, 50, 200, 50, 0.3, "measured 10-23: 3 MB; results.jsonl is append-only")),),
        retention=(Retention("append-only", "results.jsonl is never edited; the catalog and status are replaced", "ai_benchmarks/store.py::root", "on-write"),),
        irreplaceable=True, why="forward-captured Arena snapshots and lab claims cannot be re-fetched",
        jobs=(Job("ai-bench", ("ai-benchmarks", "fetch"), "0/12:55", every_min=720, what="AI benchmark scores"),
              Job("ai-discovery", ("ai-benchmarks", "discover"), "*-*-* 06:50", every_min=1440, spend="capped",
                  what="lab-claimed scores: SearXNG + one capped model call (<$0.10/day, ai_benchmarks/flags.py)")),
        publishes=("data/ai-benchmarks.json",), site_routes=("/intel/ai",), feeds_from=("library",), heartbeat=("ai_benchmarks_store/status.json",)),
    Product(
        id="instruments", title="Instruments (public data series)", owner="instruments",
        what="Free public series (prices, energy, macro, live-feed daily counts), one append-only file per series.",
        stores=(Store("instruments_store", loc.instruments, "ALGENT_INSTRUMENTS_STORE", True, budget=_b(9, 100, 500, 100, 1, "measured 10-23: 9 MB; a line only for a new or revised period")),),
        retention=(Retention("append-only", "a fetch appends only a new or revised period; nothing is edited or removed", "instruments/store.py::store_dir", "on-write"),),
        irreplaceable=True, why="forward capture of revisions and the live-feed daily counts (the baselines' history)",
        jobs=(Job("instruments", ("instruments", "fetch"), "0/6:40", every_min=360, what="free public data series"),),
        publishes=("data/",), site_routes=(), feeds_from=("live",)),
    Product(
        id="statements", title="Statements (on the record)", owner="agent_system/agents/statements",
        what="Official statement transcripts collected on a timer; statements extracted from them are append-only.",
        stores=(Store("statements_store", loc.statements, "ALGENT_STATEMENTS_STORE", True, budget=_b(15, 100, 500, 60, 7, "measured 10-23: 15 MB, ~7 MB a week")),),
        retention=(Retention("append-only", "statements.jsonl is append-only (ids dedupe); raw transcripts are internal and kept with it", "agent_system/agents/statements/store.py::store_dir", "on-write"),),
        irreplaceable=True, why="extractions are paid model work and the record is the product",
        jobs=(Job("statements", ("statements", "collect", "--no-extract", "--no-reported"), "1/6:10", every_min=360, what="official statement transcripts (collection only)"),),
        publishes=("data/",), site_routes=("/intel/record",), feeds_from=("library",), heartbeat=("statements_store/seen.json",)),
    Product(
        id="actors", title="Actors (state profiles)", owner="actors",
        what="Country indicators and office-holders; append-only observations, one file per indicator.",
        stores=(Store("actors_store", loc.actors, "ALGENT_ACTORS_STORE", True, budget=_b(17, 100, 500, 50, 0.1, "measured 10-23: 17 MB, no writes in 7 days")),),
        retention=(Retention("append-only", "a fetch appends only a never-seen or changed (country, year); no line is edited", "actors/store.py::store_dir", "on-write"),),
        irreplaceable=True, why="refetchable but cheap to keep, and revisions are forward capture",
        manual="`newsroom actors fetch` by hand: indicators change yearly, no timer is needed",
        publishes=("actors/", "data/actors/"), site_routes=("/intel/actors", "/intel/actors/[iso]"), feeds_from=("instruments",)),
    Product(
        id="geoledger", title="Geoledger (assets and status events)", owner="geoledger",
        what="A ledger of physical assets and their status events (append-only), seeded from OpenStreetMap and curated lists.",
        stores=(Store("geoledger_store", loc.geoledger, "ALGENT_GEOLEDGER_STORE", True, budget=_b(17, 100, 500, 100, 1, "measured 10-23: 17 MB; append-only JSONL, growth is an estimate")),),
        retention=(Retention("append-only", "assets/events/merges.jsonl are never rewritten; cache/overpass is keyed by query hash (overwritten, finite)", "geoledger/store.py::root", "on-write"),),
        irreplaceable=True, why="status events are partly forward capture",
        manual="`newsroom geo ...` seeds and updates by hand; nothing in it changes between operator actions",
        publishes=("geo/",), site_routes=("/intel/places/[id]",), feeds_from=()),
    Product(
        id="markets", title="Markets and the paper trader", owner="markets",
        what="Read-only Polymarket mirror, our blind forecasts and the paper trader's decisions; the scored track record.",
        stores=(Store("markets_store", loc.markets, "ALGENT_MARKETS_STORE", True, budget=_b(8, 100, 500, 100, 2, "measured 10-23: 8 MB; every file is append-only JSON lines")),),
        retention=(Retention("append-only", "history is never rewritten so the record cannot be quietly improved; ~2 MB a week estimated", "markets/store.py::root", "on-write"),),
        irreplaceable=True, why="our forecasts and trades are the scored record; they cannot be reconstructed",
        jobs=(Job("markets", ("markets", "refresh"), "3/4:50", every_min=240, what="Polymarket mirror: markets, prices, resolutions; paper track record"),
              Job("markets-daily", ("markets", "daily"), at=_markets_daily_at, every_min=1440, spend="paid", what="Polymarket paper trader: forecasts, trades, marks")),
        publishes=("data/track-record.json",), site_routes=("/intel/forecasts", "/intel/track-record"), feeds_from=("dailies",), heartbeat=("markets_store/status.json",)),
    Product(
        id="library", title="Source library (crawl cache)", owner="library",
        what="The crawled pages the research and dailies read, in one SQLite file.",
        stores=(Store("library_store", loc.library, "ALGENT_LIBRARY_STORE", False, "the crawl cache (library.db): re-crawled by the library timer",
                      budget=_b(123, 400, 1000, 400, 0, "measured 10-23: 123 MB in one SQLite file (page-level writes), capped at MAX_DB_BYTES")),),
        retention=(Retention("prune", "enforce_retention drops the oldest pages past MAX_DB_BYTES (400 MB), news before analysis before primary", "library/store.py::enforce_retention", "job:library"),),
        why="re-crawled by the timer (about a day to refill)",
        jobs=(Job("library", ("library", "crawl", "--max", "150"), "0/4:20", every_min=240, what="source-library crawl (150 pages)"),),
        feeds_from=(), heartbeat=("library_store/library.db",)),
    # ── the machine itself ────────────────────────────────────────────────────────────────────────
    Product(
        id="agent_feeds", title="Agent feeds and API", owner="publishing",
        what="Machine-readable feeds of the corpus: /api/v1, MCP, RSS and the static /data tree.",
        stores=(Store("site_data", loc.site_data, "", True, budget=_b(10, 200, 1000, 100, 2, "estimate: the published JSON tree (public/data); unmeasured")),),
        retention=(Retention("derived", "built from the dailies, profiles and Pulses on publish; the bucket holds the served copy", "publishing/agent_feed.py::dossier_files", "on-write"),),
        irreplaceable=True,
        why="what was published exists nowhere else once the database is gone (the served copy is the only copy of the documents)", manual="rebuilt on every publish by the daily and article runs", publishes=("data/", "feeds/"), site_routes=("/developers",), feeds_from=("dailies", "situations", "pulses", "actors")),
    Product(
        id="site", title="Site hubs and surfaces", owner="sites/ohmega-monster",
        what="Pages that are navigation or presentation over other products: home, the Data hub, the globe HUD and the 3D lab.",
        retention=(Retention("derived", "presentation only; no data of its own", "", "on-write"),),
        why="reads the other products' published documents", site_routes=("/", "/data", "/globe", "/lab/scene"),
        feeds_from=("dailies", "situations", "live", "flows", "maritime", "actors", "geoledger", "pulses")),
    Product(
        id="ops", title="Operations (deploy, watchdog, envelope, housekeeping)", owner="ops",
        what="The jobs that keep the machine honest: deploy-on-push, the spend watchdog, the envelope log, daily housekeeping.",
        retention=(Retention("prune", "housekeeping deletes fetch-cache files past their TTL and per-job run logs older than 30 days", "ops/housekeeping.py::run", "job:housekeeping"),),
        why="code and logs only; ~/ops-log.md grows by a few lines a day",
        jobs=(Job("update", script="update.sh", calendar="*:0/5", every_min=5, lock=False, what="deploy-on-push"),
              Job("watchdog", ("watchdog",), "*:0/2", every_min=2, lock=False, what="kills paid runs over their time/spend limits"),
              Job("envelope", ("envelope", "--log"), "*-*-* 07:10", every_min=1440, what="one-line operating-envelope summary to ~/ops-log.md"),
              Job("housekeeping", ("products", "housekeeping", "--apply"), "*-*-* 03:55", every_min=1440, what="expire the fetch cache and old per-job run logs"))),
    Product(
        id="backup", title="Backups", owner="data_backup",
        what="The nightly git mirror, the R2 snapshot with a hash manifest, and the monthly restore drill.",
        retention=(Retention("prune", "snapshots are thinned to 14 daily + 8 weekly + 12 monthly", "data_backup/flags.py::KEEP_DAILY", "job:backup-snapshot"),),
        why="it is the backup (state in backup_state.json, objects in the private R2 bucket)",
        jobs=(Job("backup", ("backup", "mirror"), "*-*-* 06:15", every_min=1440, what="stores -> private algent-data archive"),
              Job("backup-snapshot", ("backup", "snapshot"), "*-*-* 06:40", every_min=1440, what="nightly tar.gz of the irreplaceable stores -> private R2 bucket"),
              Job("backup-drill", ("backup", "restore-drill"), "*-*-01 07:30:00", every_min=44640, what="restore the latest snapshot to a temp dir and verify it"))),
    Product(
        id="database", title="Legacy Postgres tables", owner="database",
        what="The paused Supabase/Postgres publishing path; its retention windows are kept running until it is deleted.",
        retention=(Retention("prune", "retention windows on the growing tables + VACUUM", "database/flags.py::LIVE_EVENTS_ENDED_DAYS", "job:db-prune"),),
        why="publication moved to the server and R2 (Supabase paused 10-22)",
        jobs=(Job("db-prune", ("db", "prune", "--apply"), "*-*-* 03:40", every_min=1440, what="retention windows on the Postgres tables + VACUUM"),)),
    Product(
        id="caches", title="Caches and scratch", owner="agent_system/tools, retrieval, data_ingestion",
        what="The page-fetch cache, the embeddings cache and the ingestion CLI's scratch output.",
        stores=(Store("fetch_cache", loc.fetch_cache, "ALGENT_FETCH_CACHE_DIR", False, "a page-fetch cache, refilled on demand",
                      budget=_b(50, 500, 2000, 500, 0, "estimate: entries expire after 6 h and housekeeping deletes them; unmeasured before it existed")),
                Store("retrieval_store", loc.retrieval, "ALGENT_RETRIEVAL_STORE", False, "embeddings derived from the profile store (switch off by default)",
                      budget=_b(5, 500, 2000, 200, 1, "estimate: vectors cached once per text; off by default")),
                Store("ingestion_store", loc.ingestion, "ALGENT_INGESTION_DIR", False, "scratch output of the ingestion CLI",
                      budget=_b(0, 2000, 8000, 2000, 0, "estimate: raw batches pruned to the newest N by the CLI (prune_raw_batches)"))),
        retention=(Retention("prune", "fetch cache entries past the 6 h TTL are deleted daily; ingestion raw batches are pruned by the CLI", "ops/housekeeping.py::run", "job:housekeeping"),),
        why="every store here is rebuilt on demand", manual="refilled on demand; expired by the ops housekeeping job", feeds_from=()),
)
