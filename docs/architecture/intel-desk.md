# The intelligence desk: board, novelty, lifecycle, focus

Vision: `docs/vision/ohmega-intelligence-engine.md` ("The intelligence desk", "Depth: from dashboard to model").
Code: `backend/algent_backend/agent_system/agents/intel/` (`base.py`, `heat.py`, `novelty.py`, `focus.py`, `daily.py`).

The desk's focus follows the world: a theater enters when something new happens, leaves when nothing has for about
a week, and detection draws on a base wider than our own radar.

## The board (`heat.run`, `newsroom intel heat`)

1. **Base** (`base.assemble`): the window's headlines from three tagged source classes — `radar` (our editions),
   `wikipedia` (Current Events: cited events that happened) and `library` (titles of recent documents in our
   crawled trusted-source index). A class that fails to load is absent. Near-identical titles inside a class
   (same content words) are dropped; the rest is cut to `CLUSTER_LINE_BUDGET` lines by water-filling (equal share
   per class, surplus to the others), spread over days and over each class's groups.
2. **Cluster**: one model call groups the lines into theaters, reusing registry ids (identity continuity).
3. **Heat** (`heat.measure`): per class and window, share = theater members / headlines of that class (the
   *shown* lines are the denominator). A window's share is the mean over classes that have data; a class with no
   headlines is absent, never zero. Trend (heating/cooling/steady/new) compares the mean share change with the
   standard error of that mean. Heat = 100 x (w x recent + 0.25 x earlier). `by_class` on each heat row shows the parts.
4. **Novelty** (`novelty.measure`, mechanical): per theater, items dated after its last daily section — new member
   headlines by class, statements on record that `sensing` ties to it, matched series newly outside their range
   (unusual now, not as of the last section). Record: `heat[].novelty = {since, headlines{class}, statements,
   instruments, total, newest}`.
5. **Lifecycle** (`focus.classify`): `last_novel` = newest dated thing seen (only moves forward; persisted in
   `theaters.json` with `state`). `quiet` when older than `FOCUS_DROP_DAYS = 7` (the operator's rule, 10-04);
   `new` when first seen in the window and never in a daily; otherwise `active`. Novelty returning makes it
   active again on the next board. Registry theaters absent from a board are listed in `board.lifecycle`.

## Focus (`focus.plan`, used by `daily.produce_daily`)

- In focus: `new`/`active` theaters with novelty > 0, ranked by heat x novelty total. `--top` is a ceiling.
- `watch` (daily record): live theaters not written up — `nothing_new` or `over_budget` — with a one-line note.
- `quiet` (daily record): once-covered theaters that went quiet, with last change date and countries.
- Boards without lifecycle data fall back to the old top-by-heat and empty `watch`/`quiet`.
- A theater in focus whose novelty is zero-ish gets a `NEW SINCE` line in the section task; the daily doctrine
  says an unchanged section is short and says so.

## Site

`/geopolitics` daily: "Also watching" and "Quiet" after the sections (`DailyWatching.tsx`); `/intel/theaters`
rows show the lifecycle state (from the dossier index `state`/`last_novel`).

## Numbers and power (`numbers.py`, no model)

Operator steer (10-04): no market tickers. A daily price is low information and a stored price reads as a live
quote it is not; what helps is the tangible structure of the actors, in annual statistics with their years, plus the
few dated physical or structural series. So the daily record carries (both blocks optional: older records have neither):

- `theaters[].numbers = {as_of, actors[], trackers[]}`.
  - `actors` (at most `MAX_ACTORS = 5`, a first-screen group): `{iso2, name, leaders{head_of_state,
    head_of_government}, metrics{<id>: {label, unit, value, year, rank, of, source, trend?}}, trade{exports?, imports?:
    {year, total, products[], partners[]}}}`. Metrics (`numbers.ACTOR_METRICS`): GDP, GDP per person, population,
    growth; energy production/use/net import dependence and oil/gas/coal production vs consumption; exports/imports
    (% GDP, USD), fuel share of exports; IMF gross debt, fiscal balance and current account (% GDP), reserves (USD,
    months of imports), external debt, central bank policy rate; military spending (USD, % GDP), personnel. `rank`
    is among states; `trend` = `[[year, value]...]`, the last `TREND_YEARS = 10` years, for `TRENDED` metrics with
    at least three. `trade` = the top `TOP_RANKED = 5` product groups (HS sections) and partner countries with USD
    value and share of that flow's total, in the latest year the country filed. WHICH actors: the ones the desk
    already named, resolved with `actors.registry.resolve` (a trailing bracketed gloss, "Iran (Foreign Ministry)", is
    dropped first; prose is never scanned): developments' actors, validated places' countries, the latest brief's
    relation endpoints, and the shown statements' speaker affiliation and counterparts. Most-named first; actors
    with nothing stored are skipped.
  - `trackers` (at most `MAX_TRACKERS = 8`): only series that pass `numbers.tracker_ok` — chokepoint transits (physical
    flows, published with a lag, always shown with their as-of date) and central bank policy rates (`POLICY_RATES`).
    Prices, FX and yields are never trackers. Each: `{id, name, unit, freq, source, source_url, internal, value, as_of,
    age_days, changes{prev,7d,30d,1y: {from, from_period, pct}}, unusual, reasons[], outside, percentile_1y, spark[]}`;
    an internal-source series is flagged, carries no URL and is never a citation. `spark` = the last year, downsampled
    to at most `SPARK_POINTS = 60`.
- Failure stays local: a part that raises becomes empty (`trackers_error` / `actors_error` on the block).
- Dropped from the first design: the record-level `markets` block and the "Markets & flows" strip.

Site: each theater gets a "Numbers" panel (`components/numbers/TheaterNumbers.tsx`) under the map. Two small tables of
the theater's actors, one scale per column, each cell a value, a bar and a ten-year trend line: "Who they are" (GDP,
GDP per person, people, arms spending) and "Balance sheet" (debt/GDP, budget, current account, reserves; the signed
ones are bars around zero). Tapping an actor opens the shared Popover (`ActorDetail.tsx`): leaders, every metric with
its year, trend and world rank, oil/gas/coal made vs used, and the ranked top exports/imports by product and by
partner, with sources. Below, the dated flows and rates as tiles (`TrackerTile.tsx`, three visible, the rest behind a
control). One sparkline (`Sparkline.tsx`) serves everything. The accent marks "unusual" only. Annual statistics are
labelled as such on the panel.
