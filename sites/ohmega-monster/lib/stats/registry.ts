// THE stats registry: one typed entry per reader-facing number (docs/architecture/information-architecture.md section 4).
// Pure data, no I/O, client-safe. `<Stat>` (components/stats/Stat.tsx) and `lib/stats/render.ts` read it to decide how a number is
// worded (a minimum, a model's judgement, a capped list), whether a comparison may be shown, and what the info hover says.
// scripts/stats-audit.mjs lists every entry and the numeric renders that bypass it.
//
// Rules the entries encode (the operator's brief, 2026-10-20): say whose number it is; our counts are MINIMUMS because we only
// hear part of the world; a comparison to "usual" is our own history, which is young, so it is withheld until `min_history`.

/** official: a third party's figure, as published. our_count: our count from partial-coverage sensors (a minimum).
 *  our_derived: our own derivation/estimate from data. model: a model's reading or extraction. */
export type Basis = "official" | "our_count" | "our_derived" | "model";
/** none: no comparison is drawn. official_prior: the source's own earlier figures (year ago, prior week). our_history: OUR series. */
export type BaselineKind = "none" | "official_prior" | "our_history";
export type HistoryUnit = "days" | "resolved markets" | "statements";

/** Fields of the live summary's `provenance` block (backend live/provenance.py) that can supply a series start and history length. */
export type ProvenanceKey = "ships" | "aircraft" | "fires";

export type StatDef = {
  id: string;
  label: string;
  basis: Basis;
  source: { name: string; url?: string };
  /** Exactly what is counted, and where. */
  scope: string;
  /** For `our_count`: why it is a minimum. For others, the honest limit ("" when there is none worth saying). */
  coverage: string;
  baseline: BaselineKind;
  /** First day of the baseline series, when it is OURS. A FALLBACK: when `since_from` names a data source the data wins. */
  baseline_since: string | null;
  /** Where the real start date is read from at runtime ("live summary provenance.ships.since"). Empty: the date above is the only record. */
  since_from?: ProvenanceKey | "ledger" | "events" | "sanctions";
  /** History needed before a comparison/percentile/ratio may render; `null` when the stat never compares with our own history. */
  min_history: number | null;
  history_unit: HistoryUnit;
  /** Where the floor comes from (a backend flag, a statistical rule), so it is never an invented number. */
  min_history_origin: string;
  unit: string;
  /** Components/libs that render it (the audit script checks these exist). */
  surfaces: string[];
};

const DAYS_FLOOR = 21; // live memory MIN_WEEKS=3 (backend live/memory/flags.py): younger baselines are "learning". The live summary overrides it.
const FLOOR_ORIGIN = "live memory MIN_WEEKS=3 weeks (backend live/memory/flags.py): younger baselines are 'learning'";
const AIS = { name: "aisstream.io volunteer AIS receivers (Ohmega count)", url: "https://aisstream.io/" };
const PORTWATCH = { name: "IMF PortWatch", url: "https://portwatch.imf.org/" };
const NONE = { min_history: null, history_unit: "days" as const, min_history_origin: "never compared with our own history" };

type Loose = Partial<StatDef> & Pick<StatDef, "id" | "label" | "basis" | "source" | "scope" | "unit" | "surfaces">;
const def = (d: Loose): StatDef => ({ coverage: "", baseline: "none", baseline_since: null, ...NONE, ...d });

const MIN_COUNT = "Only what our receivers hear: where none are in range, ships pass unseen. Treat every figure as a minimum, never the true count.";

export const STATS: StatDef[] = [
  // ---- Home glance and Daily headline numbers (inventory D1) -------------------------------------------------------------
  def({
    id: "chokepoint_portwatch_transits", label: "Chokepoint transits (IMF PortWatch)", basis: "official", source: PORTWATCH, unit: "ships / day",
    scope: "Vessels crossing the named strait per day, from satellite AIS processed by the IMF; published weekly with about a week of lag.",
    baseline: "official_prior", min_history_origin: "the IMF series reaches back years; comparisons use its own earlier figures", surfaces: ["lib/glance.ts", "components/home/Glance.tsx"],
  }),
  def({
    id: "chokepoint_ais_transits", label: "Ships crossing a chokepoint (our AIS count)", basis: "our_count", source: AIS, unit: "ships / day",
    scope: "Ships whose AIS signal volunteer coastal receivers heard on both sides of a counting line across the strait, per UTC day.",
    coverage: MIN_COUNT, baseline: "our_history", baseline_since: "2026-10-11", since_from: "ships", min_history: DAYS_FLOOR, history_unit: "days",
    min_history_origin: FLOOR_ORIGIN, surfaces: ["lib/glance.ts", "components/live/ChokepointTiles.tsx", "components/numbers/TheaterNumbers.tsx"],
  }),
  def({
    id: "tankers_in_strait_now", label: "Tankers in the strait now", basis: "our_count", source: AIS, unit: "tankers",
    scope: "Tankers whose latest AIS position, heard by our receivers in the last minutes, lies inside the strait's box.",
    coverage: MIN_COUNT, surfaces: ["lib/glance.ts", "components/live/ChokepointTiles.tsx"],
  }),
  def({
    id: "ships_in_strait_now", label: "Ships in the strait now / crossed today", basis: "our_count", source: AIS, unit: "ships",
    scope: "Ships heard inside the strait's box right now, and crossings of the counting line so far today (UTC).",
    coverage: MIN_COUNT, surfaces: ["components/live/ChokepointTiles.tsx"],
  }),
  def({
    id: "mil_aircraft_peak", label: "Military aircraft in the air at once", basis: "our_derived", source: { name: "adsb.lol ADS-B (Ohmega daily peak)", url: "https://adsb.lol/" }, unit: "aircraft",
    scope: "For each of 6 watched regions, the most military aircraft in the air at one moment that UTC day; the figure is the SUM of those 6 peaks. It is not unique aircraft and not a total over the day.",
    coverage: "Only aircraft broadcasting ADS-B to volunteer receivers; military flights often fly silent, so this is a minimum.",
    baseline: "our_history", baseline_since: "2026-10-11", since_from: "aircraft", min_history: DAYS_FLOOR, history_unit: "days", min_history_origin: FLOOR_ORIGIN,
    surfaces: ["lib/glance.ts", "lib/globe-hud.ts", "components/hud/panels/LivePanel.tsx"],
  }),
  def({
    id: "eu_gas_storage", label: "EU gas storage", basis: "official", source: { name: "GIE AGSI+", url: "https://agsi.gie.eu/" }, unit: "% full",
    scope: "Share of EU underground gas storage capacity that is full, latest published day.", baseline: "official_prior",
    min_history_origin: "the source's own prior week and earlier years", surfaces: ["lib/glance.ts", "components/live/EnergyPanel.tsx"],
  }),
  def({
    id: "pulse_position", label: "Pulse reading", basis: "model", source: { name: "Ohmega Pulses (LLM-assessed 0 to 100 gauge)", url: "/pulses" }, unit: "/ 100",
    scope: "A language model's reading of how tense one relationship or question is, on a fixed 0 to 100 scale, re-read daily from the evidence.",
    coverage: "A judgement, not a measurement; the band words (critical, severe) are the model's labels.", baseline: "our_history", baseline_since: "2026-10-01",
    min_history: 7, history_unit: "days", min_history_origin: "a 7-day change needs 7 days of readings (the Pulse store keeps its own history)",
    surfaces: ["lib/glance.ts", "components/PulseTile.tsx", "components/DailyVisuals.tsx", "components/PulseWall.tsx", "components/hud/panels/PulsesPanel.tsx"],
  }),
  def({
    id: "theaters_escalating", label: "Sections escalating", basis: "our_derived", source: { name: "Ohmega Daily (writer and heat board)", url: "/daily" }, unit: "sections",
    scope: "Sections of the newest Daily whose escalation direction is 'rising', out of the sections that Daily wrote; a situation with no news that day has no section.",
    coverage: "Part 1 only until the second Daily run (17:30 UTC).", surfaces: ["lib/glance.ts", "app/intel/theaters/page.tsx"],
  }),
  def({
    id: "theater_heat", label: "Theater heat", basis: "our_derived", source: { name: "Ohmega heat board (share of headlines)" }, unit: "heat",
    scope: "How much of the day's headline attention a theater takes, relative to the others on its board. Attention, not danger.",
    coverage: "Different headline denominators per desk, so heat is never compared across desks.", surfaces: ["components/home/Hero.tsx", "components/dossier/TheaterRows.tsx"],
  }),
  def({
    id: "chart_of_day", label: "Chart of the day series", basis: "our_derived", source: { name: "instruments store (IMF PortWatch and Ohmega AIS, indexed to 100)" }, unit: "index",
    scope: "Lines chosen by the Daily writer from the instruments store, each indexed to 100 at the window start. A line labelled Ohmega AIS is our minimum count; one labelled IMF PortWatch is official.",
    coverage: "Mixing the two sources on one axis shows differences in coverage, not just in traffic.", surfaces: ["lib/glance.ts", "components/NativeTrackerCompare.tsx"],
  }),
  // door hints (lib/sections.ts)
  def({
    id: "door_statements", label: "Statements on the record", basis: "model", source: { name: "Ohmega statements ledger (model-extracted from primary texts)", url: "/intel/record" }, unit: "statements",
    scope: "Statements extracted from official transcripts and releases in the last 60 days. The public export is capped; the real total is published beside it.",
    coverage: "Only the feeds we collect; collection began 2026-10-01.", baseline_since: "2026-10-01", since_from: "ledger", surfaces: ["lib/sections.ts", "app/intel/record/page.tsx"],
  }),
  def({
    id: "door_signals", label: "Live signals now", basis: "our_derived", source: { name: "Ohmega live summary headlines", url: "/live" }, unit: "signals",
    scope: "Headline strings the live summary currently shows (at most 6): a display budget, not a count of everything happening.", surfaces: ["lib/sections.ts"],
  }),
  def({
    id: "door_calendar", label: "Dated items ahead", basis: "official", source: { name: "Official schedules and Ohmega extraction", url: "/calendar" }, unit: "dates",
    scope: "Scheduled events in the next 30 days from official calendars, plus dates extracted from our own text (marked unconfirmed).",
    coverage: "Extraction can mis-date an item; one whose title date disagrees with its item date is flagged unconfirmed.", surfaces: ["lib/sections.ts", "app/calendar/page.tsx"],
  }),
  def({
    id: "door_markets", label: "Markets compared", basis: "model", source: { name: "Ohmega forecasts vs Polymarket", url: "/intel/track-record" }, unit: "markets",
    scope: "Resolved Polymarket markets where we had a forecast, and the open markets we watch.", baseline_since: "2026-10-18", surfaces: ["lib/sections.ts"],
  }),
  def({
    id: "door_ai", label: "AI benchmarks and labs", basis: "official", source: { name: "Epoch AI, LMArena, SWE-bench", url: "/intel/ai" }, unit: "benchmarks",
    scope: "Benchmarks and labs present in the AI tracker, not all benchmarks that exist.", surfaces: ["lib/sections.ts", "app/intel/ai/page.tsx"],
  }),
  def({
    id: "door_states", label: "State profiles", basis: "official", source: { name: "World Bank, IMF, OWID (Ohmega profiles)", url: "/intel/actors" }, unit: "states",
    scope: "States Ohmega profiles: the G20, the permanent UN Security Council members and countries that appear in the news. Not every country.", surfaces: ["lib/sections.ts"],
  }),
  def({
    id: "door_headlines", label: "Other outlets' headlines", basis: "official", source: { name: "Headline radar (other outlets, unverified)", url: "/daily/headlines" }, unit: "headlines",
    scope: "Headlines collected from other outlets in the latest edition; we have not verified them.", surfaces: ["lib/sections.ts"],
  }),

  // ---- Theater / Daily section numbers (D2) -----------------------------------------------------------------------------
  def({
    id: "key_figure", label: "Key figure", basis: "model", source: { name: "Extracted by the Daily writer from cited sources" }, unit: "varies",
    scope: "A number the writer pulled from its research text and kept only with a cited source link. The comparison, if any, is one earlier value the writer picked: a two-point comparison, not 'versus usual'.",
    coverage: "The source is the cited page; we did not measure it.", surfaces: ["components/DailyVisuals.tsx"],
  }),
  def({
    id: "tracker_value", label: "Tracked series value", basis: "official", source: { name: "Instruments store (source named on each tile)" }, unit: "varies",
    scope: "The latest reading of a measured series (price, flow, rate) with its source and the day it is for. Internal sources are shown for context, never cited.",
    baseline: "official_prior", min_history_origin: "changes are against the series' own earlier readings", surfaces: ["components/numbers/TrackerTile.tsx", "components/numbers/TheaterNumbers.tsx"],
  }),
  def({
    id: "tracker_percentile", label: "Percentile of the past year", basis: "our_derived", source: { name: "Ohmega instruments moves (backend instruments/moves.py)" }, unit: "%",
    scope: "Where the latest value ranks among the stored readings of the trailing 365 days. Published as 'past year' only when the series really spans a year; younger series are ranked within the days we hold.",
    baseline: "our_history", baseline_since: null, min_history: 365, history_unit: "days", min_history_origin: "moves.TRAILING_DAYS=365: a year means a year",
    surfaces: ["components/numbers/TrackerTile.tsx", "lib/daily.ts"],
  }),
  def({
    id: "tracker_unusual", label: "Unusual flag (z-score)", basis: "our_derived", source: { name: "Ohmega instruments moves (backend instruments/moves.py)" }, unit: "flag",
    scope: "A reading more than 2 standard deviations from the series' own earlier readings.",
    coverage: "With the minimum sample the standard deviation is thin; on a young series of ours, treat it as a prompt to look.",
    baseline: "our_history", min_history: 10, history_unit: "days", min_history_origin: "moves.MIN_SAMPLE=10 earlier observations (backend instruments/moves.py)",
    surfaces: ["components/numbers/TrackerTile.tsx"],
  }),
  def({
    id: "live_now_in_theater", label: "Live now in this theater", basis: "our_count", source: { name: "Ohmega live feeds (AIS, ADS-B)", url: "/live" }, unit: "objects",
    scope: "Aircraft and ships heard inside the theater's map frame in the last minutes.", coverage: "Objects without a transponder, or out of receiver range, are not seen.", surfaces: ["components/live/LiveNowStrip.tsx"],
  }),
  def({
    id: "unusual_here", label: "Unusual in this theater", basis: "our_derived", source: { name: "Ohmega live memory (backend live/memory)", url: "/live" }, unit: "x normal",
    scope: "How far a place's count departs from its learned hour-of-week normal; marked 'young baseline' while the normal is still learning.",
    coverage: "A ratio on a young baseline is fragile.", baseline: "our_history", baseline_since: "2026-10-16", min_history: DAYS_FLOOR, history_unit: "days", min_history_origin: FLOOR_ORIGIN,
    surfaces: ["components/live/UnusualHere.tsx", "components/live/UnusualStrip.tsx"],
  }),
  def({
    id: "grid_share", label: "Grid impact: share of installed capacity", basis: "our_derived", source: { name: "Ohmega asset ledger and WRI / OpenStreetMap capacity", url: "/intel/places" }, unit: "% of capacity",
    scope: "Nameplate capacity of plants claimed struck, reported damaged, confirmed damaged or restored in the last 30 days, as a share of installed capacity the ledger knows. Claimed and confirmed overlap and are not added.",
    coverage: "Capacity is nameplate, not output; plant coverage is incomplete; a status is not an outage duration.", surfaces: ["components/GridImpact.tsx"],
  }),
  def({
    id: "on_record_theater", label: "On the record (theater)", basis: "model", source: { name: "Ohmega statements ledger" }, unit: "statements",
    scope: "Statements shown to the writer for this section, model-extracted from primary texts.", surfaces: ["components/OnRecord.tsx", "components/DailyTheater.tsx"],
  }),
  def({
    id: "coverage_spark", label: "Coverage (headlines per day)", basis: "our_derived", source: { name: "Ohmega heat board" }, unit: "headlines / day",
    scope: "Headlines per day naming the theater, over the last week. Attention, not danger.", surfaces: ["components/DailyVisuals.tsx", "components/dossier/TheaterRows.tsx"],
  }),

  // ---- Live, globe/HUD, maritime (D3) ------------------------------------------------------------------------------------
  def({
    id: "hud_gate_crossings", label: "Gate crossings, all gates summed", basis: "our_count", source: AIS, unit: "ships / day",
    scope: "The sum of daily crossings over every counting line we run. The total is dominated by Malacca, the busiest and best-heard strait; it is not a world figure.",
    coverage: MIN_COUNT, baseline: "our_history", baseline_since: "2026-10-11", since_from: "ships", min_history: DAYS_FLOOR, history_unit: "days", min_history_origin: FLOOR_ORIGIN,
    surfaces: ["lib/globe-hud.ts", "components/hud/panels/LivePanel.tsx"],
  }),
  def({
    id: "hud_fire_detections", label: "Fire detections (watched boxes)", basis: "our_count", source: { name: "NASA FIRMS VIIRS", url: "https://firms.modaps.eosdis.nasa.gov/map/" }, unit: "hotspots / day",
    scope: "Satellite heat detections per UTC day inside 4 boxes we watch: the Ukraine front, two southern Russia refinery belts and Gaza and the Levant. Not the world.",
    coverage: "A satellite sees a place a few times a day and cloud hides fires; a hotspot may be a wildfire or an industrial flare, not a strike.",
    baseline: "our_history", baseline_since: "2026-10-11", since_from: "fires", min_history: DAYS_FLOOR, history_unit: "days", min_history_origin: FLOOR_ORIGIN,
    surfaces: ["lib/globe-hud.ts", "components/hud/panels/LivePanel.tsx"],
  }),
  def({
    id: "quakes_24h", label: "Earthquakes, last 24 h", basis: "official", source: { name: "USGS", url: "https://earthquake.usgs.gov/" }, unit: "quakes",
    scope: "Earthquakes of magnitude 4.5 and above worldwide in the last 24 hours.", surfaces: ["lib/globe-hud.ts", "components/live/LiveWorldMap.tsx"],
  }),
  def({
    id: "outages_ongoing", label: "Internet outages ongoing", basis: "official", source: { name: "Georgia Tech IODA", url: "https://ioda.inetintel.cc.gatech.edu/" }, unit: "outages",
    scope: "Outages IODA currently reports as not yet ended, at country or region level.", coverage: "A measurement of reachability, not of cause.", surfaces: ["lib/globe-hud.ts", "components/live/LiveWorldMap.tsx"],
  }),
  def({
    id: "world_fire_hotspots", label: "Fire hotspots (world)", basis: "official", source: { name: "NASA FIRMS VIIRS", url: "https://firms.modaps.eosdis.nasa.gov/map/" }, unit: "hotspots",
    scope: "Satellite heat detections worldwide in the latest rolling picture.", coverage: "Wildfire and industrial flares are included.", surfaces: ["components/live/LiveWorldMap.tsx"],
  }),
  def({
    id: "live_anomalies", label: "Unusual now (anomalies)", basis: "our_derived", source: { name: "Ohmega live memory (backend live/memory)", url: "/live" }, unit: "anomalies",
    scope: "Places where a live count departs from its learned hour-of-week normal. Analysis, not a reported event.", coverage: "All rows are 'learning' until baselines mature; confidence is halved while learning.",
    baseline: "our_history", baseline_since: "2026-10-16", min_history: DAYS_FLOOR, history_unit: "days", min_history_origin: FLOOR_ORIGIN, surfaces: ["components/live/UnusualStrip.tsx", "components/live/LiveWorldMap.tsx"],
  }),
  def({
    id: "maritime_events", label: "Maritime behaviour events", basis: "our_derived", source: { name: "Ohmega maritime detectors on AIS (backend maritime/)", url: "/intel/maritime" }, unit: "events",
    scope: "Behaviour patterns the detectors flagged in the AIS we hear: an AIS gap where others stayed heard, a ship-to-ship meeting, an identity change, a sanctions match, a long dwell. Ended events stay 30 days.",
    coverage: "A pattern seen, never a finding of intent; only what volunteer and coastal receivers hear; 'still going' for an AIS gap means the ship has left our coverage, not that it is known to be dark.",
    baseline_since: "2026-10-17", since_from: "events", surfaces: ["app/intel/maritime/page.tsx", "components/maritime/MaritimeTable.tsx", "lib/sections.ts"],
  }),
  def({
    id: "flows_chokepoint", label: "Flows: ships a day, our AIS", basis: "our_count", source: AIS, unit: "ships / day",
    scope: "Ships per day along lanes between the places we watch, from our AIS; 'usual' is lane memory since flows began.", coverage: MIN_COUNT,
    baseline: "our_history", baseline_since: "2026-10-18", min_history: DAYS_FLOOR, history_unit: "days", min_history_origin: FLOOR_ORIGIN, surfaces: ["components/hud/panels/FlowsPanel.tsx", "components/flows"],
  }),
  def({
    id: "flows_trade", label: "Flows: goods and grain exports", basis: "official", source: { name: "UN Comtrade (reporter-declared)", url: "https://comtradeplus.un.org/" }, unit: "USD / tonnes",
    scope: "A year of trade as declared by the reporting country; annual, not live.", coverage: "Reporters differ in timeliness and completeness.", surfaces: ["components/hud/panels/FlowsPanel.tsx"],
  }),
  def({
    id: "world_median", label: "Median of the states we profile", basis: "our_derived", source: { name: "World Bank, IMF, OWID (Ohmega actors)", url: "/intel/actors" }, unit: "varies",
    scope: "The median of this figure over the 104 states Ohmega profiles (G20, P5 and countries in the news). It is not a world median.",
    coverage: "The set leans to large economies; each figure is the latest year the source has, shown with its year.", surfaces: ["lib/globe-country.ts", "components/globe"],
  }),
  def({
    id: "country_counts", label: "Country panel counts", basis: "our_derived", source: { name: "Ohmega ledger, sanctions list diffs, live anomalies" }, unit: "items",
    scope: "Statements this week (capped export), sanctions events in 30 days (collected since 2026-10-01), calendar items and live anomalies naming the country.",
    baseline_since: "2026-10-01", since_from: "sanctions", surfaces: ["lib/globe-country.ts"],
  }),
  def({
    id: "trader_pnl", label: "Paper trader P&L", basis: "model", source: { name: "Ohmega paper trader marked to Polymarket prices", url: "/intel/track-record" }, unit: "USD",
    scope: "A model's paper decisions, marked to Polymarket prices with one point of slippage. No money is staked.", coverage: "Days of history, one closed position.",
    baseline: "our_history", baseline_since: "2026-10-18", surfaces: ["lib/globe-hud.ts", "components/hud/panels/TraderPanel.tsx", "app/intel/track-record/page.tsx"],
  }),

  // ---- Tool pages (D4) ---------------------------------------------------------------------------------------------------
  def({
    id: "win_rate", label: "Win / hit rate", basis: "model", source: { name: "Ohmega paper trader and baseline", url: "/intel/track-record" }, unit: "%",
    scope: "Share of closed positions that ended in profit.", coverage: "A ratio on a handful of positions says nothing; it is hidden until enough have closed.",
    baseline: "none", min_history: 30, history_unit: "resolved markets", min_history_origin: "markets.flags.MIN_RESOLVED_FOR_VERDICT=30 (backend markets/flags.py)", surfaces: ["app/intel/track-record/page.tsx"],
  }),
  def({
    id: "brier_scores", label: "Brier score and skill", basis: "model", source: { name: "Ohmega forecasts vs Polymarket", url: "/intel/track-record" }, unit: "score",
    scope: "Mean squared error of our probabilities and the market's on the same resolved markets (0 is perfect).", coverage: "Undefined until markets resolve.",
    min_history: 30, history_unit: "resolved markets", min_history_origin: "markets.flags.MIN_RESOLVED_FOR_VERDICT=30", surfaces: ["app/intel/track-record/page.tsx"],
  }),
  def({
    id: "forecast_probability", label: "Forecast probability", basis: "model", source: { name: "Ohmega briefs", url: "/intel/forecasts" }, unit: "%",
    scope: "A model's probability for a dated question from the Daily briefs. None has resolved yet.", surfaces: ["components/SituationForecasts.tsx", "app/intel/forecasts"],
  }),
  def({
    id: "pulse_count", label: "Pulses (count)", basis: "model", source: { name: "Ohmega Pulse store", url: "/pulses" }, unit: "Pulses",
    scope: "Pulses we track and, of them, how many have a current assessed reading.", baseline_since: "2026-10-01", surfaces: ["app/pulses/page.tsx", "components/PulseWall.tsx", "lib/sections.ts"],
  }),
  def({
    id: "record_statements", label: "Statements in the ledger", basis: "model", source: { name: "Ohmega statements ledger (model-extracted from primary texts)", url: "/intel/record" }, unit: "statements",
    scope: "Statements in the public window (last 60 days). The export is capped; 'latest N' is shown when it is. One speaker is folded to one spelling.",
    coverage: "Only the feeds we collect. A statement proves it was said, not that it is true.", baseline_since: "2026-10-01", since_from: "ledger", surfaces: ["app/intel/record/page.tsx", "components/RecordBrowser.tsx"],
  }),
  def({
    id: "record_tone", label: "Tone (stance) between two parties", basis: "model", source: { name: "Ohmega statements ledger (stance by the extractor)" }, unit: "-2 to +2",
    scope: "Mean stance (-2 hostile to +2 conciliatory) of one party's statements about another, per day.", coverage: "A dyad needs at least 4 statements on at least 2 days.",
    min_history: 4, history_unit: "statements", min_history_origin: "on_record.MIN_TONE_STATEMENTS=4 (backend intel/on_record.py)", surfaces: ["components/ToneChart.tsx"],
  }),
  def({
    id: "sanctions_changes", label: "Sanctions additions and removals", basis: "official", source: { name: "OFAC SDN, UK Sanctions List, EU consolidated list (diffed by Ohmega)", url: "/intel/sanctions" }, unit: "entries",
    scope: "Entries added to or removed from the US, UK and EU lists, found by comparing each list with our previous copy. UK and EU were read for the last 30 days at first sight; the US list is undated, so its changes start from our first copy.",
    coverage: "Collection began 2026-10-01: 'none removed' means none seen since then.", baseline_since: "2026-10-01", since_from: "sanctions", surfaces: ["app/intel/sanctions/page.tsx", "lib/sections.ts"],
  }),
  def({
    id: "calendar_items", label: "Calendar items", basis: "official", source: { name: "Official schedules and Ohmega extraction", url: "/calendar" }, unit: "items",
    scope: "Dated items from official sources; items our own extraction found are marked unconfirmed.", coverage: "A title date that disagrees with the item date marks it unconfirmed.", surfaces: ["app/calendar/page.tsx"],
  }),
  def({
    id: "ai_benchmarks", label: "AI benchmark scores and gaps", basis: "official", source: { name: "Epoch AI (CC BY), LMArena, SWE-bench", url: "/intel/ai" }, unit: "varies",
    scope: "Published benchmark scores; the open-vs-closed lag and saturation figures are our own derivation from them.", baseline_since: "2026-10-17",
    coverage: "Epoch is backfilled; LMArena and lab claims are forward-only from 2026-10-17.", surfaces: ["app/intel/ai/page.tsx", "components/ai"],
  }),
  def({
    id: "actor_rank", label: "Rank among states", basis: "official", source: { name: "World Bank, IMF, OWID", url: "/intel/actors" }, unit: "rank",
    scope: "Rank among the states with data for that figure (not all 104 profiled states, not all countries).", surfaces: ["app/intel/actors/page.tsx", "lib/actors.ts"],
  }),
  def({
    id: "theater_counts", label: "Theater counts", basis: "our_derived", source: { name: "Ohmega theater registry", url: "/intel/theaters" }, unit: "theaters",
    scope: "Counts mix three universes: the sections in the newest Daily (about 4), the active theater files (about 26) and the legacy dossier set. Each count says which one it is.",
    surfaces: ["app/intel/theaters/page.tsx", "lib/sections.ts"],
  }),
];

const BY_ID = new Map(STATS.map((s) => [s.id, s]));

/** The registry entry for an id. Throws on an unknown id so a typo fails loudly in development and the audit, never silently on the page. */
export function statDef(id: string): StatDef {
  const d = BY_ID.get(id);
  if (!d) throw new Error(`stats registry: unknown id "${id}"`);
  return d;
}

export const BASIS_LABEL: Record<Basis, string> = {
  official: "Official figure",
  our_count: "Our count (a minimum)",
  our_derived: "Our own derivation",
  model: "Model-assessed",
};
