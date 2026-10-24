import { ASSET_STATUSES, ASSET_TYPES } from "@/lib/geoledger-shared";
import { SITE_URL } from "@/lib/site";

import { assetOp, assetsOp, gridOp } from "./ops-assets";
import { articleOp, articlesOp, searchOp } from "./ops-content";
import { aboutOp, entityOp, relatedOp, seriesOp, timelineOp } from "./ops-corpus";
import { anomaliesOp, instrumentOp, instrumentsOp, liveEventsOp } from "./ops-data";
import { calendarOp, sanctionsOp } from "./ops-forward";
import { maritimeOp } from "./ops-maritime";
import { satelliteOp } from "./ops-satellite";
import { aiBenchmarksOp } from "./ops-ai";
import { trackRecordOp } from "./ops-track";
import { KIND_ORDER as MARITIME_KINDS } from "@/lib/maritime-shared";
import { KINDS, TOPICS } from "@/lib/calendar-shared";
import {
  actorOp, actorsOp, apiUrl, briefOp, changesOp, dailyOp, deskAsOf, forecastsOp, pulseOp, pulsesOp, statementsOp, theaterOp, theatersOp,
} from "./ops-desk";
import { abs, notFound, type ApiResult } from "./util";

// The route table of /api/v1: the SINGLE source for dispatch, the index document, /developers' list and the
// OpenAPI spec (lib/api/openapi.ts). Adding an endpoint = one entry here + its op. Thin by design: params are
// parsed from the path and query and handed to an op (lib/api/ops-*.ts); the MCP tools call the same ops.

export type QueryParam = { name: string; description: string; enum?: readonly string[]; example?: string };
export type PathParam = { description: string; example: string };
export type Route = {
  /** OpenAPI-style template, e.g. "/daily/{domain}/{date}". */
  path: string;
  summary: string;
  query?: QueryParam[];
  pathParams?: Record<string, PathParam>;
  /** Adds the limit and cursor parameters. */
  paged?: boolean;
  run: (p: Record<string, string>, q: Record<string, string>) => Promise<ApiResult>;
};

const Q_LIMIT: QueryParam = { name: "limit", description: "Page size (default 50, max 200).", example: "20" };
const Q_CURSOR: QueryParam = { name: "cursor", description: "Opaque cursor from meta.next of the previous page." };
export const pagingParams = (): QueryParam[] => [Q_LIMIT, Q_CURSOR];

const SINCE = "Only items on or after this date or instant (YYYY-MM-DD or ISO 8601).";
const Q_ENTITY: QueryParam = { name: "entity", description: "A name or alias of a country, organisation, person, place, vessel, lab, model or situation.", example: "Strait of Hormuz" };
const Q_KEY: QueryParam = { name: "key", description: "A view key from a previous result's match.key (exact; wins over the name), e.g. entity/org/nato or country/FR." };
const Q_LIST_LIMIT: QueryParam = { name: "limit", description: "How many items per list (default 30, max 200).", example: "20" };
const BANDS = ["calm", "elevated", "severe", "critical", "unassessed"] as const;

export const ROUTES: Route[] = [
  { path: "/index", summary: "What exists: every endpoint, the data model and how fresh the desk is.", run: () => indexOp() },
  {
    path: "/daily/{domain}/{date}",
    summary: "One daily report (sections per theater, developments with sources and verification, on-the-record statements, sweep, outlook). date is YYYY-MM-DD or 'latest'.",
    pathParams: {
      domain: { description: "Report domain.", example: "geopolitics" },
      date: { description: "YYYY-MM-DD or 'latest'.", example: "latest" },
    },
    run: (p) => dailyOp(p),
  },
  {
    path: "/daily/{domain}",
    summary: "The newest daily report of a domain (alias of /daily/{domain}/latest).",
    pathParams: { domain: { description: "Report domain.", example: "geopolitics" } },
    run: (p) => dailyOp({ domain: p.domain, date: "latest" }),
  },
  {
    path: "/theaters",
    summary: "Theaters under watch (a theater is one running situation). heat = how much it is in the news, not how bad it is.",
    paged: true,
    query: [
      { name: "domain", description: "Filter by domain.", example: "geopolitics" },
      { name: "q", description: "Name contains." },
    ],
    run: (_p, q) => theatersOp(q),
  },
  {
    path: "/theaters/{id}",
    summary: "One theater's living dossier: current assessment, timeline with sources and verification, places, actors, Pulses, forecasts, statements.",
    pathParams: { id: { description: "Theater id from /theaters.", example: "iran-us-confrontation" } },
    run: (p) => theaterOp(p),
  },
  {
    path: "/briefs/{slug}",
    summary: "A brief: the deep analysis of one theater (timeline, indicators, competing explanations, scored judgments).",
    pathParams: { slug: { description: "Brief slug from a theater's briefs[] or /search.", example: "example-brief" } },
    run: (p) => briefOp(p),
  },
  {
    path: "/pulses",
    summary: "Pulses: persistent 0-100 readings of one question about the world, with band and confidence. History is on the item.",
    paged: true,
    query: [
      { name: "band", description: "Filter by band.", enum: BANDS },
      { name: "status", description: "Filter by status.", enum: ["experimental", "active", "dormant"] },
      { name: "q", description: "Name, question or situation contains." },
    ],
    run: (_p, q) => pulsesOp(q),
  },
  {
    path: "/pulses/{id}",
    summary: "One Pulse with its definition and the full reading history (every reading: date, mode, position, decision, reasoning).",
    pathParams: { id: { description: "Pulse id from /pulses.", example: "pls_example" } },
    run: (p) => pulseOp(p),
  },
  {
    path: "/articles",
    summary: "Published articles, newest first (metadata only).",
    paged: true,
    query: [
      { name: "tag", description: "Exact tag." },
      { name: "q", description: "Title or dek contains." },
    ],
    run: (_p, q) => articlesOp(q),
  },
  {
    path: "/articles/{slug}",
    summary: "One article: markdown, graded claims with sources, corrections, how to cite.",
    pathParams: { slug: { description: "Article slug from /articles.", example: "example-article" } },
    run: (p) => articleOp(p),
  },
  {
    path: "/statements",
    summary: "Who said what: the on-the-record ledger (exact quotes only when quote is set). A statement proves it was said, not that it is true.",
    paged: true,
    query: [
      { name: "actor", description: "Speaker, affiliation or target name, or an ISO alpha-2 code.", example: "IR" },
      { name: "since", description: SINCE, example: "2026-10-01" },
      { name: "signal", description: "Signal type, e.g. threat, warning, red_line, offer.", example: "threat" },
    ],
    run: (_p, q) => statementsOp(q),
  },
  { path: "/actors", summary: "Actors (state profiles).", paged: true, query: [{ name: "q", description: "Name or ISO code contains." }], run: (_p, q) => actorsOp(q) },
  {
    path: "/actors/{iso}",
    summary: "One state's power profile: leaders, population, economy, trade, energy, military (each figure with year, rank and source), recent statements, the theaters and Pulses it is in.",
    pathParams: { iso: { description: "ISO 3166-1 alpha-2 code.", example: "IR" } },
    run: (p) => actorOp(p),
  },
  { path: "/instruments", summary: "Measured series (ship transits, prices, storage...): latest value, freshness and source.", paged: true, run: (_p, q) => instrumentsOp(q) },
  {
    path: "/instruments/{id}",
    summary: "One measured series: latest value, changes over horizons, 'unusual' flag and recent points, with its source URL.",
    pathParams: { id: { description: "Instrument id from /instruments.", example: "hormuz_transits" } },
    run: (p) => instrumentOp(p),
  },
  {
    path: "/live/events",
    summary: "Current live events from public feeds (internet outages, earthquakes, military aircraft, fire hotspots), each with its source URL. Relayed, not verified by Ohmega.",
    paged: true,
    query: [
      { name: "kind", description: "Event kind.", enum: ["outage", "quake", "aircraft", "fire"] },
      { name: "since", description: SINCE, example: "2026-10-10" },
      { name: "severity", description: "Severity.", enum: ["info", "notable", "major"] },
    ],
    run: (_p, q) => liveEventsOp(q),
  },
  {
    path: "/anomalies",
    summary:
      "Where live ships, aircraft and satellite fire detections depart from Ohmega's own learned normal for that place and hour of the week (e.g. tankers 60% below normal in the Strait of Hormuz for 18 h), with ratio, duration, confidence and a plain sentence. Original analysis (ohmega_derived); coverage gaps are screened out.",
    paged: true,
    query: [
      { name: "layer", description: "What is counted.", enum: ["ship", "air", "fire"] },
      { name: "direction", description: "Above or below normal.", enum: ["above", "below"] },
      { name: "active", description: "true: still going; false: recently closed.", enum: ["true", "false"] },
      { name: "country", description: "Country name as the desk writes it.", example: "Iran" },
      { name: "since", description: SINCE, example: "2026-10-10" },
    ],
    run: (_p, q) => anomaliesOp(q),
  },
  {
    path: "/calendar",
    summary:
      "What is coming: dated upcoming items (elections and referendums, central-bank decisions, data releases, commodity reports, summits, courts, AI and tech events, launches, our markets' resolution dates, deadlines our own reports named), soonest first and merged across sources, each with a topic, an importance, a grade and its sources. A date is a plan, not an outcome.",
    paged: true,
    query: [
      { name: "kind", description: "Kind of item.", enum: KINDS.map((k) => k.id) },
      { name: "topic", description: "Topic chip on /calendar.", enum: TOPICS.map((t) => t.id) },
      { name: "country", description: "ISO 3166-1 alpha-2 code the item concerns.", example: "US" },
      { name: "situation", description: "Situation id the item is linked to (from our own watches).", example: "sit_russia_nato" },
      { name: "grade", description: "official = the body's own schedule; announced = compiled or company-confirmed; estimated = from a rule or projection; unconfirmed = our own reading.", enum: ["official", "announced", "estimated", "unconfirmed"] },
      { name: "confidence", description: "The older three-level form of grade: high = official, medium = announced or estimated, low = unconfirmed.", enum: ["high", "medium", "low"] },
      { name: "min_importance", description: "1 routine, 2 notable (default), 3 major.", enum: ["1", "2", "3"] },
      { name: "routine", description: "true: include routine items (weekly stock reports, UN Security Council meetings).", enum: ["true", "false"] },
      { name: "days", description: "How many days ahead (default 45, max 180).", example: "30" },
    ],
    run: (_p, q) => calendarOp(q),
  },
  {
    path: "/sanctions",
    summary:
      "Sanctions designations and delistings on the US OFAC SDN, UK and EU lists, found by comparing each list with its previous copy: who, what kind (person, entity, vessel, aircraft), programme, countries, date and the list it came from. Newest first.",
    paged: true,
    query: [
      { name: "list", description: "Which list.", enum: ["ofac", "uk", "eu"] },
      { name: "action", description: "Added or removed.", enum: ["designated", "delisted"] },
      { name: "type", description: "Kind of party.", enum: ["person", "entity", "vessel", "aircraft"] },
      { name: "country", description: "ISO 3166-1 alpha-2 code the party is tied to.", example: "RU" },
      { name: "since", description: SINCE, example: "2026-10-01" },
    ],
    run: (_p, q) => sanctionsOp({ ...q, source: q.list }),
  },
  {
    path: "/maritime",
    summary:
      "Vessel behaviour events Ohmega derived from the AIS it hears: ships that went silent where others kept being heard, ship-to-ship encounters in open water, identity changes (renames, IMO or flag changes), vessels matching a sanctions list, and long dwells over chokepoints and cable corridors. Each has a reason, a confidence and its evidence points. A pattern seen, never a finding of intent.",
    paged: true,
    query: [
      { name: "kind", description: "Kind of behaviour.", enum: MARITIME_KINDS },
      { name: "active", description: "true: still going; false: ended.", enum: ["true", "false"] },
      { name: "flag", description: "ISO 3166-1 alpha-2 flag state of a vessel involved.", example: "PA" },
      { name: "area", description: "Part of the name of the area, or a country the area touches.", example: "Hormuz" },
      { name: "imo", description: "7-digit IMO number.", example: "9074729" },
      { name: "mmsi", description: "9-digit MMSI.", example: "636092000" },
      { name: "min_confidence", description: "Only events at or above this confidence, 0 to 1.", example: "0.5" },
      { name: "since", description: SINCE, example: "2026-10-01" },
    ],
    run: (_p, q) => maritimeOp(q),
  },
  {
    path: "/satellite",
    summary:
      "Satellite watch: places the desk tracks (struck or damaged assets, places in today's developments, chokepoints) with a before and after Sentinel-2 chip of the same ground, a change score and night lights against the site's own history. Ohmega's own computation: a machine signal that pixels differ, never an interpretation; a cloudy pair is inconclusive, and a site with little history is 'learning'. Every judgement carries basis, method_note, baseline_since and n_obs.",
    paged: true,
    query: [
      { name: "label", description: "Change verdict.", enum: ["changed", "steady", "learning", "inconclusive"] },
      { name: "kind", description: "A place from the ledger or a chokepoint zone.", enum: ["asset", "zone"] },
      { name: "country", description: "ISO 3166-1 alpha-2 code of the place.", example: "UA" },
    ],
    run: (_p, q) => satelliteOp(q),
  },
  {
    path: "/track-record",
    summary:
      "Ohmega's reality check: its own probability forecasts on Polymarket markets (made blind to the price, stored immutably) scored against the market's price at the same moment. Brier score and log loss for both, calibration, open paper positions, resolved markets including the misses. PAPER ONLY, not financial advice.",
    run: () => trackRecordOp(),
  },
  {
    path: "/ai-benchmarks",
    summary:
      "Frontier AI model scores across public benchmarks (Epoch AI hub, SWE-bench, LMArena): the best score so far, the frontier over time, open-weights against closed, per-lab series and how close each benchmark is to saturation. Measured scores only in the series; lab-claimed scores are listed apart as `claimed`. Without a filter: one summary row per benchmark.",
    query: [
      { name: "benchmark", description: "A benchmark id or part of its name; returns the full series for the matches.", example: "gpqa" },
      { name: "lab", description: "With benchmark: only this lab's series (lab id, e.g. anthropic, openai, google, meta, deepseek).", example: "anthropic" },
    ],
    run: (_p, q) => aiBenchmarksOp(q),
  },
  {
    path: "/assets",
    summary:
      "Geolocated places (power plants, substations, refineries, fuel depots, ports, airbases, bases, dams) with the latest thing said about their state and by whom. A claimed strike is a party's claim, not a confirmation. Give at least one filter.",
    paged: true,
    query: [
      { name: "bbox", description: "west,south,east,north in degrees.", example: "30,46,38,52" },
      { name: "type", description: "Kind of place.", enum: ASSET_TYPES },
      { name: "country", description: "ISO 3166-1 alpha-2 code.", example: "UA" },
      { name: "status", description: "Latest status on record.", enum: ASSET_STATUSES },
      { name: "has_events", description: "true: only places with a status on record; false: only those without.", enum: ["true", "false"] },
    ],
    run: (_p, q) => assetsOp(q),
  },
  {
    path: "/assets/{id}",
    summary: "One place and its full status history: every dated event with the party who said it, confidence and source URLs.",
    pathParams: { id: { description: "Asset id from /assets.", example: "wri-UKR0000123" } },
    run: (p) => assetOp(p),
  },
  {
    path: "/grid/{iso}",
    summary:
      "Ohmega's grid-impact rollup for a country: installed generating capacity (WRI/OSM) and the share claimed struck, reported damaged, confirmed damaged or destroyed and restored over 7 and 30 days, split by fuel, plus the affected plants. Claimed and confirmed are separate and overlap. Original analysis (ohmega_derived).",
    pathParams: { iso: { description: "ISO 3166-1 alpha-2 code.", example: "UA" } },
    run: (p) => gridOp(p),
  },
  {
    path: "/search",
    summary:
      "Text search over titles, headlines and names of articles, theaters, Pulses, briefs, daily reports and actors, and over the corpus index: every country, organisation, person, place, vessel, lab, model and situation by name or alias (type=entity) and the titles of published documents (type=document). Names and titles only, never document bodies.",
    paged: true,
    query: [
      { name: "q", description: "Query words (all must match), 2-200 characters.", example: "hormuz" },
      { name: "type", description: "Restrict to one kind.", enum: ["article", "theater", "pulse", "brief", "daily", "actor", "entity", "document"] },
    ],
    run: (_p, q) => searchOp(q),
  },
  {
    path: "/entity",
    summary:
      "Who or what a name is, from the corpus: aliases, counts, the latest status, typed relations (head of state, affiliated with, stance...), what it is most connected to, its measured series (each with a basis) and the newest documents, claims and events with their sources. A country, an organisation, a person, a place, a vessel, a lab, a model or a situation. Ambiguous names return alternatives; a country wins over a same-named place.",
    query: [{ ...Q_ENTITY, name: "name", description: "A name or alias to resolve (or pass key)." }, Q_KEY],
    run: (_p, q) => entityOp(q),
  },
  {
    path: "/about",
    summary:
      "Everything the corpus holds about an entity since a date: documents (dailies, briefs, profiles, statements, articles), claims (with grounding, confidence and their source URLs) and events, newest first, each with the product and record it came from.",
    query: [Q_ENTITY, Q_KEY, { name: "since", description: SINCE, example: "2026-10-01" }, { name: "kinds", description: "Comma-separated: claim, event, document select whole sections; any other value filters by item kind (daily, brief, profile, development, status_damaged ...).", example: "claim,event" }, Q_LIST_LIMIT],
    run: (_p, q) => aboutOp(q),
  },
  {
    path: "/timeline",
    summary: "An entity's documents and events in date order (oldest first); a development repeated by several reports appears once.",
    query: [Q_ENTITY, Q_KEY, { name: "since", description: SINCE, example: "2026-10-01" }, Q_LIST_LIMIT],
    run: (_p, q) => timelineOp(q),
  },
  {
    path: "/related",
    summary: "What an entity is most connected to and why: typed edges x3, shared claims x2, shared events x1.5, shared documents x1 (the parts are shown), plus the typed relations with their evidence.",
    query: [Q_ENTITY, Q_KEY, { name: "kinds", description: "Only related entities of these kinds (comma-separated: country, org, person, place, ...).", example: "country,org" }, Q_LIST_LIMIT],
    run: (_p, q) => relatedOp(q),
  },
  {
    path: "/series",
    summary:
      "A measured series from the corpus with its unit and basis (official, our_count, our_derived, model, reported): one metric across the entities that have it (gdp, population, chk_hormuz_transits, bench.* ...), or an entity's own series (pass entity or key). A metric name that matches several returns the candidates.",
    query: [
      { name: "metric", description: "A metric id, or the start of one ending in . or * to list a family.", example: "gdp" },
      Q_ENTITY,
      Q_KEY,
      { name: "since", description: SINCE, example: "2020-01-01" },
    ],
    paged: true,
    run: (_p, q) => seriesOp(q),
  },
  {
    path: "/changes",
    summary: "What changed in the last 30 days, newest first: Pulse moves, new briefs and daily reports, forecasts made and resolved. Poll this to stay current.",
    paged: true,
    query: [
      { name: "since", description: SINCE, example: "2026-10-01" },
      { name: "type", description: "Event type.", enum: ["pulse_created", "pulse_moved", "brief_published", "daily_published", "forecast_made", "forecast_resolved"] },
    ],
    run: (_p, q) => changesOp(q),
  },
  {
    path: "/forecasts",
    summary: "Every forecast we made (probability, horizon, resolution criteria, status) and the public Brier scorecard.",
    paged: true,
    query: [{ name: "status", description: "Filter by status.", enum: ["open", "yes", "no", "void"] }],
    run: (_p, q) => forecastsOp(q),
  },
];

// ---- index ----------------------------------------------------------------------------------------------

async function indexOp(): Promise<ApiResult> {
  const as_of = await deskAsOf();
  return {
    data: {
      name: "Ohmega Monster agent API",
      version: "v1",
      description:
        "Read-only JSON over the claim/profile corpus behind ohmega.monster: daily intelligence reports, theater dossiers, Pulses (0-100 readings with history), articles with graded claims, on-the-record statements, actor profiles, measured series and live events. Every response is {data, meta} with as_of, cite_as, source and license.",
      base_url: apiUrl(""),
      openapi: apiUrl("/openapi.json"),
      docs: abs("/developers"),
      mcp: { url: abs("/api/mcp"), transport: "streamable-http", docs: abs("/developers#mcp") },
      also: { llms_txt: abs("/llms.txt"), llms_full: abs("/llms-full.txt"), static_feeds: abs("/data/intel.json"), rss: abs("/feed.xml") },
      endpoints: ROUTES.map((r) => ({ path: `/api/v1${r.path}`, summary: r.summary, url: apiUrl(r.path.replace(/\{[^}]+\}/g, (m) => `:${m.slice(1, -1)}`)) })),
      conventions: {
        envelope: "{data, meta:{as_of, source, version, cite_as, license, verification?, note?, next?}}",
        pagination: "limit and cursor query parameters; meta.next is the next page's URL when there is one",
        citing: "cite_as is the canonical human URL; give it and the as_of date when you quote",
        verification: "daily developments and dossier timeline rows: 'researched' (our research established it) or 'reported' (another outlet; a lead, not a finding)",
        auth: "none today; read-only and public",
      },
    },
    as_of,
    cite_as: SITE_URL,
    source: "ohmega.api.index",
  };
}

// ---- dispatch -------------------------------------------------------------------------------------------

function match(route: Route, segs: string[]): Record<string, string> | null {
  const tpl = route.path.split("/").filter(Boolean);
  if (tpl.length !== segs.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < tpl.length; i++) {
    const t = tpl[i];
    if (t.startsWith("{")) {
      try {
        params[t.slice(1, -1)] = decodeURIComponent(segs[i]);
      } catch {
        return null;
      }
    } else if (t !== segs[i]) return null;
  }
  return params;
}

/** Resolve a request path (segments after /api/v1) and query to a result. Throws ApiError. */
export async function dispatch(segments: string[], search: URLSearchParams): Promise<ApiResult> {
  const segs = segments.length === 0 ? ["index"] : segments;
  const query: Record<string, string> = {};
  search.forEach((v, k) => {
    if (!(k in query)) query[k] = v;
  });
  for (const route of ROUTES) {
    const params = match(route, segs);
    if (params) return route.run(params, query);
  }
  throw notFound(`endpoint /api/v1/${segs.join("/")}`);
}
