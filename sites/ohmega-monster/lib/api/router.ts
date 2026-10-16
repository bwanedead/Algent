import { ASSET_STATUSES, ASSET_TYPES } from "@/lib/geoledger-shared";
import { SITE_URL } from "@/lib/site";

import { assetOp, assetsOp, gridOp } from "./ops-assets";
import { articleOp, articlesOp, searchOp } from "./ops-content";
import { anomaliesOp, instrumentOp, instrumentsOp, liveEventsOp } from "./ops-data";
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
    summary: "Text search over titles, headlines and names of articles, theaters, Pulses, briefs, daily reports and actors.",
    paged: true,
    query: [
      { name: "q", description: "Query words (all must match), 2-200 characters.", example: "hormuz" },
      { name: "type", description: "Restrict to one kind.", enum: ["article", "theater", "pulse", "brief", "daily", "actor"] },
    ],
    run: (_p, q) => searchOp(q),
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
