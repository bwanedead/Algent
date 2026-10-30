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

from collections.abc import Callable

from . import locations as loc
from .model import Budget, Contract as K, Job, Product, Retention, Store

#: After-hooks of a job that publishes a report: the fast views build (Home, the globe HUD and the daily hub reflect it within minutes instead of at the
#: next half-hour tick) and then a smoke test of the production site (it must still serve everything the new report touches). Each runs as a job of its own.
AFTER_PUBLISH = ("views-fast", "site-smoke")


# ── jobs whose times come from a product's own flags (read lazily) ──────────────────────────────────
def _menu_at() -> str:
    from algent_backend.ops import flags

    return flags.MENU_UTC


def _daily_jobs() -> tuple[Job, ...]:
    from algent_backend.agent_system.agents.intel import flags as f

    out = [Job(f"daily-{e.n}", ("intel", "daily", "--domain", "geopolitics", "--research", "--edition", str(e.n)), at=e.utc, every_min=1440, spend="paid",
               est_min=70 if e.n == 1 else 45, deadline_min=120, what=f"geopolitics daily, part {e.n} ({e.label})", then=AFTER_PUBLISH) for e in f.EDITIONS]
    if f.AI_DAILY_SCHEDULED:
        out.append(Job("ai-daily", ("intel", "daily", "--domain", "ai", "--research"), at=f.AI_DAILY_UTC, every_min=1440, spend="paid", est_min=40, deadline_min=120, what="AI daily", then=AFTER_PUBLISH))
    return tuple(out)


def _markets_daily_at() -> str:
    from algent_backend.markets import flags

    return flags.DAILY_UTC


def _markets_gaps_at() -> str:
    from algent_backend.markets import flags

    return flags.GAPS_UTC


def _markets_fast_calendar() -> str:
    """Every FAST_EVERY_H hours at :20, which is 30 minutes after the free mirror pass (3/4:50) has refreshed prices and resolutions."""
    from algent_backend.markets import flags

    return f"*-*-* 0/{flags.FAST_EVERY_H}:20:00"


def _markets_day_calendar() -> str:
    """The day book's runs: DAY_RUN_HOURS at minute DAY_RUN_MINUTE (UTC), e.g. ``*-*-* 8,14,20:40:00``."""
    from algent_backend.markets import flags

    return f"*-*-* {','.join(str(h) for h in flags.DAY_RUN_HOURS)}:{flags.DAY_RUN_MINUTE:02d}:00"


def _strategy_calendar(sid: str) -> Callable[[], str]:
    """A roster strategy's runs: its hours at its minute (UTC), staggered by ``markets/strategies.py`` so no two strategies fire close together."""
    def calendar() -> str:
        from algent_backend.markets import strategies

        st = strategies.get(sid)
        return f"*-*-* {','.join(str(h) for h in st.run_hours)}:{st.run_minute:02d}:00"

    return calendar


def _gap_min(hours: tuple[int, ...]) -> float:
    """The longest gap between a strategy's runs, in minutes (wrapping past midnight), at least an hour."""
    hs = sorted(hours)
    return float(max([(b - a) % 24 or 24 for a, b in zip(hs, hs[1:] + hs[:1])]) * 60)


def _strategy_jobs() -> tuple[Job, ...]:
    """One capped job per independent roster strategy (day, daily and fast keep their own jobs below), all editorial priority."""
    from algent_backend.markets import strategies

    return tuple(Job(f"markets-{st.id}", ("markets", "strategy", st.id), _strategy_calendar(st.id), every_min=_gap_min(st.run_hours), spend="capped", priority=1, est_min=5, est_mb=400, max_wait_min=30,
                     deadline_min=40, what=f"{st.name} ({st.method_name}): its own research and probabilities, paper bets {st.horizon_h / 24:g} days out, {len(st.run_hours)} runs a day"
                     + (f"; must fill {st.min_orders} order(s) a run" if st.must_trade else "") + (f"; must fill {st.min_fills_day} order(s) a day" if st.min_fills_day else ""))
                 for st in strategies.roster() if st.id not in ("day", "daily", "fast"))


def _calendar_every(minutes: int) -> str:
    """systemd minute steps stop at 59, so a longer cadence is written as an hourly step."""
    return f"*-*-* 0/{minutes // 60}:00:00" if minutes >= 60 else f"*:0/{minutes}"


def _live_jobs() -> tuple[Job, ...]:
    from algent_backend.live import flags as f

    feeds = tuple(Job(f"live-{feed}", ("live", "run", "--feed", feed), _calendar_every(m), every_min=m, lock=False, est_mb=120, what=f"live feed {feed}")
                  for feed, m in f.CADENCE_MINUTES.items())
    return (*feeds, Job("ais", ("live", "ais"), kind="service", lock=False, what="AIS chokepoint counter (always on; needs ALGENT_AISSTREAM_KEY)"))


#: The views' families (``views/flags.BUDGET_BYTES``): one contract each, ``ohmega.view.<family>``, over ``views/<key>.json``. Builders stamp their own schema
#: from here (``contracts.view_schema``), so there is one place that says which version a view family is at.
VIEW_FAMILIES = {"country": "country/*", "situation": "situation/*", "situations": "situations", "entity": "entity/*/*", "event": "event/*/*", "series": "series/*",
                 "series-index": "series-index", "home": "home", "hud": "hud", "daily-hub": "daily-hub", "graph": "graph", "search-index": "search-index", "manifest": "manifest"}


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
        contracts=(K("ohmega.daily", 1, ("daily/*/*.json", "data/daily/*/*.json")), K("ohmega.brief", 1, ("briefs/*.json", "data/briefs/*.json")), K("ohmega.snapshot", 1, ("snapshots/*.json",))),
        site_routes=("/daily", "/daily/[desk]", "/daily/[desk]/[date]", "/daily/[desk]/archive", "/intel/briefs/[slug]", "/intel/events/[date]/[theater]/[n]"),
        feeds_from=("instruments", "statements", "library", "live", "sanctions", "calendar", "maritime", "geoledger", "actors"),
        heartbeat=("intel_store/daily/*/*.json",)),
    Product(
        id="situations", title="Situations (living files)", owner="agent_system/agents/intel",
        what="Each long-running story as one file, built from the dailies' sections; no extra cost, no store of its own.",
        retention=(Retention("derived", "rebuilt from the dailies on every daily run (theaters/<id>.json); clearing it loses nothing", "publishing/agent_feed.py::dossier_files", "on-write"),),
        why="derived from the dailies (intel_store holds the source)", manual="rebuilt on every daily run and by `newsroom publish`; no timer of its own", publishes=("theaters/",),
        contracts=(K("ohmega.dossier", 1, ("theaters/*.json",)), K("ohmega.dossier.index", 1, ("theaters/index.json",))),
        site_routes=("/situations", "/situations/[id]", "/intel/graph"), feeds_from=("dailies", "actors", "pulses")),
    Product(
        id="pulses", title="Pulses (0-100 gauges)", owner="agent_system/agents/pulse",
        what="Model-assessed gauges per situation with append-only influence logs and watches; the reasoning behind every move is the asset.",
        stores=(Store("pulse_store", loc.pulse, "ALGENT_PULSE_STORE", True,
                      budget=_b(2, 50, 200, 20, 0.5, "measured 10-23: 2 MB, ~0.5 MB a week, append-only")),),
        retention=(Retention("append-only", "influences are never rewritten or removed; ~0.5 MB a week", "agent_system/agents/pulse/store.py::PulseStore", "on-write"),),
        irreplaceable=True, why="two weeks of Pulse reasoning were lost once when it was missing from the backup",
        manual="written by the daily runs (no timer of its own)", publishes=("pulses/",), contracts=(K("ohmega.pulse", 1, ("pulses/*.json", "data/pulses/*.json")),), site_routes=("/pulses",), feeds_from=("dailies",)),
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
        contracts=(K("ohmega.article.source", 1, ("articles/*.json",)), K("ohmega.article.index", 1, ("articles/index.json",))),
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
        jobs=(Job("menu", ("run", "--to", "menu"), at=_menu_at, every_min=1440, spend="paid", est_min=30, deadline_min=120, what="newsroom menu"),),
        publishes=("radar/",), contracts=(K("ohmega.radar", 1, ("radar/*.json",)),), site_routes=("/daily/headlines", "/daily/headlines/[slug]")),
    # ── data: measured layers ─────────────────────────────────────────────────────────────────────
    Product(
        id="live", title="Live feeds (ships, aircraft, quakes, fires, outages)", owner="live",
        what="Free live feeds on timers plus the always-on AIS counter; events are snapshots, numbers go to instruments, hours feed baselines and anomalies.",
        stores=(Store("live_store", loc.live, "ALGENT_LIVE_STORE", False, "re-collected from public feeds; baselines relearn in ~3 weeks (the one real loss)",
                      budget=_b(46, 150, 500, 200, 0, "measured 10-23: 46 MB of snapshots and baselines; snapshots overwrite, hour files are pruned at 60 days")),),
        retention=(Retention("prune", "hour files older than HOUR_KEEP_DAYS (60) are deleted; event snapshots are replaced each run", "live/memory/hours.py::prune", "job:live-usgs"),),
        why="re-collectable from public feeds", jobs=_live_jobs, publishes=("live/",), site_routes=("/live",), feeds_from=(),
        contracts=(K("ohmega.live.events", 1, ("live/events.json",)), K("ohmega.live.stats", 1, ("live/stats.json",)), K("ohmega.live.anomalies", 1, ("live/anomalies.json",)),
                   K("ohmega.live.world", 1, ("live/world.json",)), K("ohmega.live.summary", 1, ("live/summary.json",)), K("ohmega.live.energy", 1, ("live/energy.json",)),
                   K("ohmega.live.fires", 1, ("live/fires.json",)), K("ohmega.live.vessels", 1, ("live/vessels.json",)), K("ohmega.live.aircraft", 1, ("live/aircraft.json",)),
                   K("ohmega.live.coverage", 1, ("live/coverage.json",)), K("ohmega.live.points", 1, ("live/points.json",)), K("ohmega.live.tiles.index", 1, ("live/tiles/index.json",)),
                   K("ohmega.live.tile", 1, ("live/tiles/*.json",)), K("ohmega.live.tracks", 1, ("live/tracks/**",))),
        heartbeat=("live_store/status.json",)),
    Product(
        id="flows", title="Flows (ship lanes, grain, money)", owner="flows",
        what="Lane aggregates from the AIS service plus the weekly Comtrade trade picture, as one document. Stored under live_store/flows.",
        retention=(Retention("overwrite", "tracker and days.json are bounded aggregates replaced atomically", "flows/store.py::root", "on-write"),),
        why="aggregates of the live stream, rebuilt as it runs",
        jobs=(Job("flows", ("flows", "publish"), "*:7/15", every_min=15, lock=False, est_mb=150, what="ship-lane + grain/money flows document"),),
        publishes=("live/",), contracts=(K("ohmega.flows", 1, ("live/flows.json",)),), site_routes=(), feeds_from=("live",), heartbeat=("live_store/flows/days.json",)),
    Product(
        id="satellite", title="Satellite (Sentinel-2 chips, night lights)", owner="satellite",
        what="Change detection on watched sites from keyless imagery; stored under live_store/satellite.",
        retention=(Retention("prune", "dated chips are pruned to the KEEP_DATED (3) newest scenes per site plus the baseline", "satellite/store.py::KEEP_DATED", "on-write"),),
        why="re-observed daily; the append-only records.jsonl is small and re-derivable from imagery",
        jobs=(Job("satellite", ("satellite", "run"), "*-*-* 03:20", every_min=1440, lock=False, est_min=5, est_mb=300, what="Sentinel-2 chips + night lights of watched sites"),),
        publishes=("live/", "/satellite/"), contracts=(K("ohmega.satellite", 1, ("live/satellite.json",)),), site_routes=("/intel/satellite",), feeds_from=(), heartbeat=("live_store/satellite/doc.json",)),
    Product(
        id="maritime", title="Maritime behaviour", owner="maritime",
        what="Behaviour events from the AIS stream (encounters, dark gaps, loitering, sanctioned vessels); the daily ship summaries are the long record.",
        stores=(Store("maritime_store", loc.maritime, "ALGENT_MARITIME_STORE", False, "the raw positions and 7-day event log are GB-scale and bounded by retention; the daily summaries are backed up",
                      budget=_b(50, 800, 3000, 800, 3, "estimate after compaction: profile book tens of MB + 7 days of compact log; the 1.7 GB log was the incident")),
                Store("maritime_daily", loc.maritime_daily, "", True, budget=_b(1, 100, 500, 50, 0.5, "estimate: one small summary file a day"))),
        retention=(Retention("rollup", "daily ship summaries are written then the raw event log is cut to LOG_KEEP_DAYS (7)", "maritime/flags.py::LOG_KEEP_DAYS", "job:maritime-rollup"),),
        irreplaceable=True, why="the daily summaries are the only long record of ship behaviour (backed up as maritime_daily)",
        jobs=(Job("maritime-rollup", ("maritime", "rollup", "--apply"), "*-*-* 04:05", every_min=1440, priority=4, what="daily ship summaries + retention of the raw event log"),
              Job("maritime-vessels", ("maritime", "publish"), "*-*-* 04:35", every_min=1440, priority=4, what="the per-vessel documents (maritime/vessel/*.json), once a day; live passes skip them"),),
        publishes=("maritime/",), site_routes=("/intel/maritime",),
        contracts=(K("ohmega.maritime.events", 1, ("maritime/recent.json", "maritime/live.json", "maritime/vessel/*.json")), K("ohmega.maritime.counts", 1, ("maritime/counts.json",))), feeds_from=("live",), heartbeat=("maritime_store/state.json",)),
    Product(
        id="sanctions", title="Sanctions", owner="sanctions",
        what="OFAC / UK / EU list diffs as designation events; an append-only event log plus one snapshot per source.",
        stores=(Store("sanctions_store", loc.sanctions, "ALGENT_SANCTIONS_STORE", True, budget=_b(7, 100, 500, 100, 0.5, "measured 10-23: 7 MB; events are append-only, snapshots replaced")),),
        retention=(Retention("append-only", "events.jsonl is never rewritten; snapshots/<src>.json are replaced atomically", "sanctions/store.py::root", "on-write"),),
        irreplaceable=True, why="forward capture: the diff history of the lists cannot be re-fetched",
        jobs=(Job("sanctions", ("sanctions", "fetch"), "2/6:25", every_min=360, what="sanctions list diffs"),),
        publishes=("sanctions/",), contracts=(K("ohmega.sanctions", 1, ("sanctions/recent.json", "sanctions/country/*.json")),), site_routes=("/intel/sanctions",), feeds_from=(), heartbeat=("sanctions_store/status.json",)),
    Product(
        id="conflict", title="Attack log (conflict events)", owner="conflict",
        what="Attacks, clashes and mass-violence events as one normalised record: GDELT (machine-coded from news, keyless, every 15 minutes) plus ReliefWeb, ACLED and UCDP built and inactive "
             "until their keys are set. Stores events only, never a source's raw file; rolling retention by age and size.",
        stores=(Store("conflict_store", loc.conflict, "ALGENT_CONFLICT_STORE", False, "every source is re-fetchable and the machine-coded part is bounded to a rolling window by design; the documents and the corpus index keep what they published",
                      budget=_b(85, 120, 200, 20, 0, "estimate from a live pull (10-24: 11 GDELT files = 391 events = 0.22 MB, ~1.8 MB a day, x 45-day window, plus the small curated sources); prune also caps the folder at conflict/flags.py MAX_STORE_MB (150)")),),
        retention=(Retention("prune", "event shards older than KEEP_DAYS_MACHINE (45; machine-coded only) or KEEP_DAYS_OTHER (365) are deleted, then the oldest until the folder is under MAX_STORE_MB (150)", "conflict/store.py::prune", "on-write"),),
        why="re-fetchable events in a rolling window; nothing here is the only copy",
        jobs=(Job("conflict", ("conflict", "fetch", "--source", "gdelt"), "*:4/15", every_min=15, lock=False, est_min=1, est_mb=200, what="GDELT 15-minute event files (keyless)"),
              Job("reliefweb", ("conflict", "fetch", "--source", "reliefweb"), "*:41", every_min=60, lock=False, est_min=1, est_mb=150, what="ReliefWeb reports (needs an approved ALGENT_RELIEFWEB_APPNAME; reports so until set)"),
              Job("conflict-daily", ("conflict", "fetch", "--source", "acled", "--source", "ucdp"), "*-*-* 05:20", every_min=1440, lock=False, est_min=2, est_mb=200,
                  what="ACLED + UCDP (need ALGENT_ACLED_EMAIL/PASSWORD, ALGENT_UCDP_TOKEN; report so until set)")),
        publishes=("conflict/",), contracts=(K("ohmega.conflict.recent", 1, ("conflict/recent.json",)), K("ohmega.conflict.country", 1, ("conflict/country/*.json",))),
        site_routes=("/intel/attacks",), feeds_from=("geoledger",), heartbeat=("conflict_store/status.json",)),
    Product(
        id="gnss", title="GPS interference (jamming zones)", owner="gnss",
        what="Zones where aircraft report poor navigation accuracy (ADS-B NACp), derived by us hourly from sampled ADS-B counts and cross-checked against GPSJam's top band. "
             "Stores per-cell counts and derived zones only, never aircraft records or GPSJam's full file.",
        stores=(Store("gnss_store", loc.gnss, "ALGENT_GNSS_STORE", True,
                      budget=_b(9, 40, 150, 3, 0.1, "estimate from a live pass (10-24): an hour line is 5 KB (7 days kept, ~1 MB), GPSJam's top band 129 KB a day for 30 days (~4 MB) then only ours, closed-day sums ~10 KB a day; 400-day cap")),),
        retention=(Retention("prune", "hour tallies older than HOURS_KEEP_DAYS (7) are dropped once their day sum is saved; zone files lose GPSJam's cells after ZONES_FULL_DAYS (30); everything goes after KEEP_DAYS (400)", "gnss/store.py::prune", "on-write"),),
        irreplaceable=True, why="the baseline (closed-day sums and our zones) is our own derivation from ADS-B that cannot be re-fetched: past ADS-B is gone",
        jobs=(Job("gnss", ("gnss", "run"), "*:12", every_min=60, lock=False, est_min=2, est_mb=150, what="ADS-B sample around known trouble spots + GPSJam top band, zones rebuilt"),),
        publishes=("gnss/", "live/"), contracts=(K("ohmega.gnss.latest", 1, ("gnss/latest.json",)), K("ohmega.gnss.overlay", 1, ("live/gnss.json",))),
        site_routes=("/intel/gnss",), feeds_from=(), heartbeat=("gnss_store/status.json",)),
    Product(
        id="calendar", title="Calendar (look-ahead)", owner="lookahead",
        what="Upcoming elections, central-bank decisions, releases, commodity reports, summits, courts, AI/tech events, launches, our markets' resolutions and extracted deadlines; append-only revisions of items.",
        stores=(Store("calendar_store", loc.calendar, "ALGENT_CALENDAR_STORE", True,
                      budget=_b(1, 100, 500, 100, 0.1, "estimate (unmeasured): ~700 items x ~0.7 KB on first fill; a revision line only when a date moves (launches, markets); published: calendar/next.json ~250 KB + ~80 country files, each hash-skipped")),),
        retention=(Retention("append-only", "items.jsonl keeps every revision; status.json is replaced", "lookahead/store.py::root", "on-write"),),
        irreplaceable=True, why="revision history (a moved or withdrawn date) cannot be re-fetched",
        jobs=(Job("calendar", ("calendar", "refresh", "--group", "schedules"), "*-*-* 04:40", every_min=1440, priority=3, est_min=3, est_mb=150, what="calendar: official schedules (daily class)"),
              Job("calendar-fast", ("calendar", "refresh", "--group", "fast"), "3/6:35", every_min=360, priority=3, est_min=4, est_mb=150, what="calendar: earnings, launches, our markets and watches (six-hourly class)")),
        publishes=("calendar/",), contracts=(K("ohmega.calendar", 1, ("calendar/next.json", "calendar/markets.json", "calendar/country/*.json")),), site_routes=("/calendar",), feeds_from=("statements",), heartbeat=("calendar_store/status.json",)),
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
        publishes=("data/ai-benchmarks.json",), contracts=(K("ohmega.ai-benchmarks", 1, ("data/ai-benchmarks.json",)),), site_routes=("/intel/ai",), feeds_from=("library",), heartbeat=("ai_benchmarks_store/status.json",)),
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
        publishes=("data/", "record.json"), contracts=(K("ohmega.record", 1, ("record.json",)),), site_routes=("/intel/record",), feeds_from=("library",), heartbeat=("statements_store/seen.json",)),
    Product(
        id="actors", title="Actors (state profiles)", owner="actors",
        what="Country indicators and office-holders; append-only observations, one file per indicator.",
        stores=(Store("actors_store", loc.actors, "ALGENT_ACTORS_STORE", True, budget=_b(17, 100, 500, 50, 0.1, "measured 10-23: 17 MB, no writes in 7 days")),),
        retention=(Retention("append-only", "a fetch appends only a never-seen or changed (country, year); no line is edited", "actors/store.py::store_dir", "on-write"),),
        irreplaceable=True, why="refetchable but cheap to keep, and revisions are forward capture",
        manual="`newsroom actors fetch` by hand: indicators change yearly, no timer is needed",
        publishes=("actors/", "data/actors/"), contracts=(K("ohmega.actor", 1, ("actors/*.json",)), K("ohmega.actor.index", 1, ("actors/index.json",))), site_routes=("/intel/actors", "/intel/actors/[iso]"), feeds_from=("instruments",)),
    Product(
        id="geoledger", title="Geoledger (assets and status events)", owner="geoledger",
        what="A ledger of physical assets and their status events (append-only), seeded from OpenStreetMap and curated lists.",
        stores=(Store("geoledger_store", loc.geoledger, "ALGENT_GEOLEDGER_STORE", True, budget=_b(17, 100, 500, 100, 1, "measured 10-23: 17 MB; append-only JSONL, growth is an estimate")),),
        retention=(Retention("append-only", "assets/events/merges.jsonl are never rewritten; cache/overpass is keyed by query hash (overwritten, finite)", "geoledger/store.py::root", "on-write"),),
        irreplaceable=True, why="status events are partly forward capture",
        manual="`newsroom geo ...` seeds and updates by hand; nothing in it changes between operator actions",
        publishes=("geo/",), site_routes=("/intel/places/[id]",),
        contracts=(K("ohmega.geo.place", 1, ("geo/a/*.json",)), K("ohmega.geo.assets", 1, ("geo/c/*.json", "geo/events-assets.json")), K("ohmega.geo.countries", 1, ("geo/countries.json",)),
                   K("ohmega.geo.grid", 1, ("geo/grid/*.json",)), K("ohmega.geo.events", 1, ("geo/events/*.json",))), feeds_from=()),
    Product(
        id="markets", title="Markets and the paper trader", owner="markets",
        what="Read-only Polymarket mirror, our blind forecasts and the paper traders' decisions (daily, fast and day books), the corpus-research traces and gap requests; the scored track record.",
        stores=(Store("markets_store", loc.markets, "ALGENT_MARKETS_STORE", True, budget=_b(8, 100, 500, 100, 5, "measured 10-23: 8 MB; every file is append-only JSON lines; the fast book and research traces add ~3 MB a week (estimate; traces are pruned at 60 days)")),),
        retention=(Retention("append-only", "history is never rewritten so the record cannot be quietly improved; ~2 MB a week estimated", "markets/store.py::root", "on-write"),
                   Retention("prune", "research traces (observability, never read by scoring) older than TRACE_KEEP_DAYS are dropped by the free refresh pass; forecasts, decisions, gaps and fills are never pruned", "markets/flags.py::TRACE_KEEP_DAYS", "job:markets")),
        irreplaceable=True, why="our forecasts and trades are the scored record; they cannot be reconstructed",
        jobs=(Job("markets", ("markets", "refresh"), "3/4:50", every_min=240, what="Polymarket mirror: markets, prices, resolutions; paper track record"),
              Job("markets-daily", ("markets", "daily"), at=_markets_daily_at, every_min=1440, spend="paid", est_min=15, deadline_min=120, what="daily trader strategy: its own research and probabilities, paper trades, marks",
                  then=AFTER_PUBLISH),
              Job("markets-fast", ("markets", "fast"), _markets_fast_calendar, every_min=480, spend="capped", priority=2, est_min=6, est_mb=400, max_wait_min=45, deadline_min=60,
                  what="fast strategy: markets settling within days, its own research and paper trades every 4 h (own cap; gated like a paid job)"),
              Job("markets-day", ("markets", "day"), _markets_day_calendar, every_min=720, spend="capped", priority=1, est_min=5, est_mb=400, max_wait_min=30, deadline_min=40,
                  what="day strategy: an agent that browses Polymarket and picks its own 0-2 day paper bets, 3 runs a day (own caps; gated like a paid job)"),
              *_strategy_jobs(),
              Job("markets-gaps", ("markets", "gaps"), at=_markets_gaps_at, every_min=1440, spend="paid", est_min=20, deadline_min=180,
                  what="research the bots' most-asked corpus gaps into profiles (capped $0.50/day)")),
        publishes=("data/track-record.json",), contracts=(K("ohmega.track-record", 2, ("data/track-record.json",), accepts=(1,)),),
        site_routes=("/intel/forecasts", "/intel/track-record"), feeds_from=("dailies", "profiles"), heartbeat=("markets_store/status.json",)),
    Product(
        id="experiments", title="Experiment lab (protocol comparisons)", owner="experiment",
        what="Phase 1 of the experiment framework: frozen and forked forecasting protocols compared on one question and one evidence snapshot; write-once manifests, prompts, outputs, resolutions. Off by default; read-only over the markets store and the corpus index.",
        stores=(Store("experiment_store", loc.experiments, "ALGENT_EXPERIMENT_STORE", False, "an early lab: runs on resolved markets can be re-run from the markets store, and the first frozen control is a few KB; add to the backup (one line here) when a result starts to matter",
                      budget=_b(0.1, 20, 100, 5, 0.5, "estimate (unmeasured): a run is ~30 KB (snapshot of <= 4000 documents is the bulk, stored once per question); no run is scheduled")),),
        retention=(Retention("append-only", "write-once files, never rewritten; a run is a few tens of KB and only a person starts one", "experiment/store.py::write_once", "manual"),),
        why="early lab data; a frozen control is small but re-capturing it later would capture later code, so back it up before relying on it",
        manual="newsroom lab questions|run|decide|list|show|branch|score|verify (no timer on purpose: an experiment is a decision, and a live run spends money)",
        feeds_from=("markets", "corpus_index")),
    Product(
        id="acquisition", title="Acquisition ledger (when we first held each source)", owner="acquisition",
        what="Append-only ledger of the first time a corpus build saw each source unit (key + content hash). It survives every index rebuild, which resets the index's own ingest times; the experiment lab reads it to replay history without hindsight.",
        stores=(Store("acquisition_store", loc.acquisition, "ALGENT_ACQUISITION_STORE", True, budget=_b(0.5, 20, 100, 20, 0.2, "estimate (unmeasured): ~200 bytes a unit version; a few thousand units and a few new versions a day")),),
        retention=(Retention("append-only", "ledger.jsonl is never rewritten; a unit version is one line, forever (small)", "acquisition/store.py::load", "job:corpus-build"),),
        irreplaceable=True, why="acquisition times cannot be reconstructed after the fact: a rebuild only knows when it ran, so a lost ledger loses what we held when",
        manual="written by `newsroom corpus build` (the corpus-build job) as a side effect; read by `newsroom lab`; nothing to run by hand",
        feeds_from=("corpus_index",)),
    Product(
        id="library", title="Source library (crawl cache)", owner="library",
        what="The crawled pages the research and dailies read, in one SQLite file.",
        stores=(Store("library_store", loc.library, "ALGENT_LIBRARY_STORE", False, "the crawl cache (library.db): re-crawled by the library timer",
                      budget=_b(123, 400, 1000, 400, 0, "measured 10-23: 123 MB in one SQLite file (page-level writes), capped at MAX_DB_BYTES")),),
        retention=(Retention("prune", "enforce_retention drops the oldest pages past MAX_DB_BYTES (400 MB), news before analysis before primary", "library/store.py::enforce_retention", "job:library"),),
        why="re-crawled by the timer (about a day to refill)",
        jobs=(Job("library", ("library", "crawl", "--max", "150"), "0/4:20", every_min=240, what="source-library crawl (150 pages)"),),
        feeds_from=(), heartbeat=("library_store/library.db",)),
    Product(
        id="corpus_index", title="Corpus index (queryable view of the record)", owner="corpus",
        what="One rebuildable SQLite index over the other products' stores: entities, relations, documents, claims, sources, events and series with provenance; the query API agents and retrieval use.",
        stores=(Store("corpus_store", loc.corpus, "ALGENT_CORPUS_STORE", False, "derived; `newsroom corpus build --full` rebuilds it from the other products' stores",
                      budget=_b(75, 400, 1500, 80, 3, "measured 10-23 on the dev stores: 74 MB (130 k observations dominate); estimate for the server until `newsroom corpus stats` runs there")),),
        retention=(Retention("derived", "rebuilt from the record; --full builds a fresh compact file, incremental builds VACUUM past 25% free pages", "corpus/build.py::build", "job:corpus-build"),),
        why="derived: every row comes from another product's store; deleting it loses nothing",
        jobs=(Job("corpus-build", ("corpus", "build"), "2/4:25", every_min=240, priority=2, est_min=1, est_mb=190, what="incremental corpus index build (after the daily, AI and markets runs)"),),
        feeds_from=("dailies", "pulses", "profiles", "articles", "statements", "sanctions", "calendar", "geoledger", "maritime", "markets", "instruments", "actors", "ai_benchmarks"),
        heartbeat=("corpus_store/corpus.db",)),
    Product(
        id="views", title="Views (server-built pages and agent data)", owner="views",
        what="Small versioned JSON views the server builds from the staged documents and the corpus index (country, situation, entity, event, home, hud, daily hub, theater-state graph, search index) and publishes to R2, so no page and no agent aggregates raw documents at request time.",
        stores=(Store("views_store", loc.views, "ALGENT_VIEWS_STORE", False, "derived; `newsroom views build` rebuilds every view from the other products' stores",
                      budget=_b(120, 400, 1500, 120, 2, "estimate from the dev corpus: up to 8 k entity views of ~10 KB, ~250 country views of ~20 KB, situation views of up to 450 KB; replace with `newsroom views stats` from the server")),),
        retention=(Retention("derived", "rebuilt each run from the record; a full build prunes keys it no longer produces from the store (bucket objects are overwritten, never listed)", "views/build.py::build_all", "job:views"),),
        why="derived: every field comes from another product's published documents or the corpus index; deleting the store loses nothing",
        jobs=(Job("views", ("views", "build"), "2/4:50", every_min=240, priority=2, est_min=2, deadline_min=60, what="build every view and publish the changed ones (after corpus-build)", then=("site-smoke",)),
              Job("views-fast", ("views", "build", "--only", "home,hud,daily-hub"), "*:10/30", every_min=30, lock=False, priority=2, est_min=1.5, est_mb=300, what="refresh the home, globe HUD and daily-hub views (no corpus; a changed daily shows within half an hour)"),
              Job("orphan-prune", ("publish", "prune-orphans", "--prefix", "views/"), "*-*-* 05:20", every_min=1440, priority=4, preemptible=True,
                  what="delete views no longer produced (the first build's place views), at most ORPHAN_PRUNE_MAX_PER_RUN a day within the R2 guard")),
        publishes=("views/",), contracts=tuple(K(f"ohmega.view.{fam}", 1, (f"views/{path}.json",)) for fam, path in VIEW_FAMILIES.items()),
        feeds_from=("dailies", "situations", "pulses", "actors", "articles", "statements", "sanctions", "calendar", "geoledger", "markets", "corpus_index"),
        heartbeat=("views_store/manifest.json",)),
    Product(
        id="staging", title="Staging channel (preview data)", owner="publishing",
        what="A sample of what production publishes, under the staging/ prefix of the same bucket, so a preview deployment is checked against real data before promotion.",
        retention=(Retention("prune", "staged objects not rewritten for STAGING_KEEP_DAYS (14) are deleted; a daily-operations cap and a byte cap bound it between prunes",
                             "publishing/staging.py::prune", "job:staging-prune"),),
        why="derived: rebuilt from the local stores by `newsroom publish stage-from-prod`; deleting it loses nothing",
        jobs=(Job("staging-prune", ("publish", "staging-prune"), "*-*-* 05:05", every_min=1440, priority=4, preemptible=True, what="delete staged objects older than the staging retention"),),
        publishes=("staging/",), feeds_from=("views", "dailies")),
    # ── the machine itself ────────────────────────────────────────────────────────────────────────
    Product(
        id="agent_feeds", title="Agent feeds and API", owner="publishing",
        what="Machine-readable feeds of the corpus: /api/v1, MCP, RSS and the static /data tree.",
        stores=(Store("site_data", loc.site_data, "", True, budget=_b(10, 200, 1000, 100, 2, "estimate: the published JSON tree (public/data); unmeasured")),),
        retention=(Retention("derived", "built from the dailies, profiles and Pulses on publish; the bucket holds the served copy", "publishing/agent_feed.py::dossier_files", "on-write"),),
        irreplaceable=True,
        why="what was published exists nowhere else once the database is gone (the served copy is the only copy of the documents)", manual="rebuilt on every publish by the daily and article runs", publishes=("data/", "feeds/"),
        contracts=(K("ohmega.forecasts", 1, ("data/forecasts.json",)), K("ohmega.changes", 1, ("data/changes.json",)), K("ohmega.intel.index", 1, ("data/intel.json",)),
                   K("ohmega.pulses", 1, ("data/pulses.json",))), site_routes=("/developers",), feeds_from=("dailies", "situations", "pulses", "actors")),
    Product(
        id="site", title="Site hubs and surfaces", owner="sites/ohmega-monster",
        what="Pages that are navigation or presentation over other products: home, the Data hub, the globe HUD and the 3D lab.",
        retention=(Retention("derived", "presentation only; no data of its own", "", "on-write"),),
        why="reads the other products' published documents", site_routes=("/", "/explore", "/globe", "/lab/scene"),
        jobs=(Job("site-smoke", ("site", "smoke", "--log"), "*:17", every_min=60, lock=False, est_mb=60,
                  priority=2, what="smoke test of the production site: every route, sampled dynamic pages, the agent API, freshness (hourly, and after each publish job)"),),
        feeds_from=("dailies", "situations", "live", "flows", "maritime", "actors", "geoledger", "pulses")),
    Product(
        id="ops", title="Operations (deploy, watchdog, envelope, housekeeping)", owner="ops",
        what="The jobs that keep the machine honest: deploy-on-push, the spend watchdog, the envelope log, daily housekeeping.",
        retention=(Retention("prune", "housekeeping deletes fetch-cache files past their TTL and per-job run logs older than 30 days", "ops/housekeeping.py::run", "job:housekeeping"),),
        why="code and logs only; ~/ops-log.md grows by a few lines a day",
        publishes=("status/",), contracts=(K("ohmega.status", 1, ("status/*.json",)),),
        jobs=(Job("update", script="update.sh", calendar="*:0/5", every_min=5, lock=False, est_mb=80, what="deploy-on-push"),
              Job("watchdog", ("watchdog",), "*:0/2", every_min=2, lock=False, est_min=0.2, est_mb=50, what="kills paid runs over their time/spend limits"),
              Job("envelope", ("envelope", "--log"), "*-*-* 07:10", every_min=1440, priority=4, what="one-line operating-envelope summary to ~/ops-log.md"),
              Job("housekeeping", ("products", "housekeeping", "--apply"), "*-*-* 03:55", every_min=1440, priority=4, preemptible=True, what="expire the fetch cache and old per-job run logs"))),
    Product(
        id="backup", title="Backups", owner="data_backup",
        what="The nightly git mirror, the R2 snapshot with a hash manifest, and the monthly restore drill.",
        retention=(Retention("prune", "snapshots are thinned to 14 daily + 8 weekly + 12 monthly", "data_backup/flags.py::KEEP_DAILY", "job:backup-snapshot"),),
        why="it is the backup (state in backup_state.json, objects in the private R2 bucket)",
        jobs=(Job("backup", ("backup", "mirror"), "*-*-* 06:15", every_min=1440, priority=4, what="stores -> private algent-data archive"),
              Job("backup-snapshot", ("backup", "snapshot"), "*-*-* 06:40", every_min=1440, priority=4, what="nightly tar.gz of the irreplaceable stores -> private R2 bucket"),
              Job("backup-drill", ("backup", "restore-drill"), "*-*-01 07:30:00", every_min=44640, priority=4, preemptible=True, what="restore the latest snapshot to a temp dir and verify it"))),
    Product(
        id="database", title="Legacy Postgres tables", owner="database",
        what="The paused Supabase/Postgres publishing path; its retention windows are kept running until it is deleted.",
        retention=(Retention("prune", "retention windows on the growing tables + VACUUM", "database/flags.py::LIVE_EVENTS_ENDED_DAYS", "job:db-prune"),),
        why="publication moved to the server and R2 (Supabase paused 10-22)",
        jobs=(Job("db-prune", ("db", "prune", "--apply"), "*-*-* 03:40", every_min=1440, priority=4, what="retention windows on the Postgres tables + VACUUM"),)),
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
