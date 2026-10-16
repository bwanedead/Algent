import { ASSET_STATUSES, ASSET_TYPES } from "@/lib/geoledger-shared";

import { LICENSE } from "./envelope";
import { assetOp, assetsOp, gridOp } from "./ops-assets";
import { searchOp } from "./ops-content";
import { instrumentOp, instrumentsOp, liveEventsOp } from "./ops-data";
import { dailyOp, pulseOp, pulsesOp, statementsOp, theaterOp, theatersOp } from "./ops-desk";
import { arr, isObj, objs, type ApiResult, type Args, type Obj } from "./util";

// The MCP tools: thin adapters over the SAME ops the REST API uses (lib/api/ops-*.ts), plus compact views so a
// tool result fits a model's context. Every result is one JSON text block carrying as_of, cite_as and the
// license, so an agent can cite what it read. Protocol: lib/api/mcp.ts. Docs: docs/architecture/agent-api.md.

export type Tool = {
  name: string;
  title: string;
  description: string;
  inputSchema: Obj;
  run: (args: Args) => Promise<ApiResult>;
  /** Shrinks the op's data for model context; absent = pass through. */
  compact?: (data: unknown) => unknown;
};

const str_ = (description: string, extra: Obj = {}): Obj => ({ type: "string", description, ...extra });
const limit_ = (def: number): Obj => ({ type: "integer", minimum: 1, maximum: 200, default: def, description: "Maximum items to return." });
const cursor_ = str_("Opaque cursor from a previous result's next_cursor, to get the next page.");
const schema = (properties: Obj, required: string[] = []): Obj => ({ type: "object", properties, required, additionalProperties: false });

const pick = (o: Obj, keys: string[]): Obj => Object.fromEntries(keys.filter((k) => k in o).map((k) => [k, o[k]]));

// ---- compact views --------------------------------------------------------------------------------------

function compactDaily(data: unknown): unknown {
  if (!isObj(data)) return data;
  const sweep = isObj(data.sweep) ? data.sweep : null;
  return {
    ...pick(data, ["id", "domain", "date", "built_at", "headline", "the_day", "cite_as"]),
    theaters: objs(data.theaters).map((t) => ({
      ...pick(t, ["theater_id", "name", "headline", "bottom_line", "outlook", "watch_next"]),
      escalation: t.escalation,
      pulses: objs(t.pulses).map((p) => pick(p, ["id", "name", "position", "band", "change_24h", "change_7d"])),
      developments: objs(t.developments).map((d) => pick(d, ["headline", "detail", "when", "where", "verification", "sources"])),
      on_record: objs(t.on_record).map((s) => pick(s, ["speaker", "role", "date", "quote", "paraphrase", "signal", "url"])),
    })),
    sweep: objs(sweep?.regions).map((r) => ({ region: r.region, items: objs(r.items).map((i) => pick(i, ["text", "countries", "sources"])) })),
    note: "developments[].verification: 'researched' = our research established it; 'reported' = another outlet reported it (a lead). Pass view=full for everything.",
  };
}

function compactTheater(data: unknown): unknown {
  if (!isObj(data)) return data;
  return {
    ...pick(data, ["id", "theater_id", "name", "domain", "first_seen", "last_seen", "days_covered", "primer", "current", "forecasts", "briefs", "cite_as"]),
    pulses: objs(data.pulses).map((p) => pick(p, ["id", "name", "situation", "position", "band"])),
    timeline: objs(data.timeline).slice(0, 15).map((t) => pick(t, ["date", "headline", "detail", "where", "verification", "sources"])),
    actors: arr(data.actors).slice(0, 10),
    places: objs(data.places).slice(0, 10).map((p) => pick(p, ["name", "country", "lat", "lon", "last_date"])),
    on_record: objs(data.on_record).slice(0, 10).map((s) => pick(s, ["speaker", "role", "date", "quote", "paraphrase", "signal", "url"])),
    reports: arr(data.reports).slice(0, 5),
    note: "Trimmed for context: full timeline, relations, figures and statements are at the REST twin (api_url).",
  };
}

function compactPulse(data: unknown): unknown {
  if (!isObj(data)) return data;
  const readings = objs(data.readings);
  return {
    ...pick(data, ["id", "name", "situation", "status", "position", "band", "confidence", "velocity_7d", "last_assessed", "evidence_through", "definition", "cite_as"]),
    history: arr(data.history).slice(-30),
    readings: readings.slice(-10).map((r) => pick(r, ["at", "mode", "moves_pulse", "decision", "position", "rationale", "confidence", "article_url"])),
    readings_total: readings.length,
  };
}

// ---- the tools ------------------------------------------------------------------------------------------

export const TOOLS: Tool[] = [
  {
    name: "get_daily",
    title: "Daily intelligence report",
    description:
      "The day's intelligence report: per theater, what happened (developments with sources and a researched/reported verification), who said what, outlook and what to watch, plus Pulse positions. Defaults to the newest geopolitics report.",
    inputSchema: schema({
      domain: str_("Report domain.", { default: "geopolitics" }),
      date: str_("YYYY-MM-DD or 'latest'.", { default: "latest" }),
      view: str_("'summary' (default, compact) or 'full' (the whole document, large).", { enum: ["summary", "full"], default: "summary" }),
    }),
    run: dailyOp,
    compact: compactDaily,
  },
  {
    name: "list_theaters",
    title: "List theaters",
    description: "Theaters (running situations) under watch, with heat (how much in the news, not how bad) and escalation direction. Use get_theater for a dossier.",
    inputSchema: schema({ q: str_("Name contains."), domain: str_("Filter by domain."), limit: limit_(30), cursor: cursor_ }),
    run: theatersOp,
  },
  {
    name: "get_theater",
    title: "Theater dossier",
    description: "One theater's living dossier: current assessment, timeline (each row with sources and verification), places, actors, Pulses, forecasts, recent statements.",
    inputSchema: schema({ id: str_("Theater id from list_theaters.") }, ["id"]),
    run: theaterOp,
    compact: compactTheater,
  },
  {
    name: "list_pulses",
    title: "List Pulses",
    description:
      "Pulses: persistent 0-100 readings of one question about the world (0 is the calm end, 100 the extreme end; see low_end/high_end), with band, confidence and 7-day velocity. Early readings, still calibrating.",
    inputSchema: schema({
      band: str_("Filter by band.", { enum: ["calm", "elevated", "severe", "critical", "unassessed"] }),
      q: str_("Name, question or situation contains."),
      limit: limit_(30),
      cursor: cursor_,
    }),
    run: pulsesOp,
  },
  {
    name: "get_pulse",
    title: "Pulse with history",
    description: "One Pulse: its definition, current reading, history and the most recent readings with reasoning (audit readings are blind checks that never move the Pulse).",
    inputSchema: schema({ id: str_("Pulse id from list_pulses.") }, ["id"]),
    run: pulseOp,
    compact: compactPulse,
  },
  {
    name: "search",
    title: "Search",
    description: "Text search over titles, headlines and names of articles, theaters, Pulses, briefs, daily reports and actors. Returns ids and citable URLs; fetch details with the matching get_* tool or the result's api_url.",
    inputSchema: schema(
      { q: str_("Query words (all must match)."), type: str_("Restrict to one kind.", { enum: ["article", "theater", "pulse", "brief", "daily", "actor"] }), limit: limit_(20), cursor: cursor_ },
      ["q"],
    ),
    run: searchOp,
  },
  {
    name: "get_statements",
    title: "On-the-record statements",
    description:
      "Who said what: statements by named people and bodies (exact quote only when 'quote' is set, else a paraphrase), with signal (threat, warning, offer...), stance and source URL. A statement proves it was said, not that it is true.",
    inputSchema: schema({
      actor: str_("Speaker, affiliation or target name, or an ISO alpha-2 code like IR."),
      since: str_("Only on or after this date (YYYY-MM-DD)."),
      signal: str_("Signal type, e.g. threat, warning, red_line, offer."),
      limit: limit_(30),
      cursor: cursor_,
    }),
    run: statementsOp,
  },
  {
    name: "get_live_events",
    title: "Live events",
    description: "Current live events from public feeds: internet outages, earthquakes, military aircraft, fire hotspots. Each has a source URL; relayed, not verified by Ohmega.",
    inputSchema: schema({
      kind: str_("Event kind.", { enum: ["outage", "quake", "aircraft", "fire"] }),
      since: str_("Only on or after this date or ISO instant."),
      severity: str_("Severity.", { enum: ["info", "notable", "major"] }),
      limit: limit_(30),
      cursor: cursor_,
    }),
    run: liveEventsOp,
  },
  {
    name: "get_assets",
    title: "Places and their status history",
    description:
      "Geolocated infrastructure (power plants, substations, refineries, fuel depots, ports, airbases, bases, dams) with the latest dated statement about its state and WHO made it: claimed_struck is a party's claim, reported_damaged and confirmed_damaged come from others. Filter by bbox, type, country, status or has_events; pass id for one place's full history with sources.",
    inputSchema: schema({
      id: str_("Asset id from a previous result; returns the full status history."),
      bbox: str_("west,south,east,north in degrees, e.g. 30,46,38,52."),
      type: str_("Kind of place.", { enum: [...ASSET_TYPES] }),
      country: str_("ISO alpha-2 code, e.g. UA."),
      status: str_("Latest status on record.", { enum: [...ASSET_STATUSES] }),
      has_events: str_("true: only places with a status on record.", { enum: ["true", "false"] }),
      limit: limit_(30),
      cursor: cursor_,
    }),
    run: (a) => (a.id ? assetOp(a) : assetsOp(a)),
  },
  {
    name: "get_grid_impact",
    title: "Grid-impact rollup",
    description:
      "Ohmega's own analysis of how much of a country's installed generating capacity has been claimed struck, reported damaged, confirmed damaged or destroyed, and restored over 7 and 30 days, by fuel, with the affected plants. Claimed and confirmed are separate tallies that overlap: never add them. Capacity is nameplate, not lost output.",
    inputSchema: schema({ iso: str_("ISO alpha-2 code, e.g. UA.") }, ["iso"]),
    run: (a) => gridOp(a),
  },
  {
    name: "get_instrument",
    title: "Measured series",
    description: "A measured series (ship transits through chokepoints, prices, storage...): latest value, change over horizons, whether it is unusual against its own history, with source. Omit id to list the available series.",
    inputSchema: schema({ id: str_("Instrument id; omit to list all."), limit: limit_(50), cursor: cursor_ }),
    run: (a) => (a.id ? instrumentOp(a) : instrumentsOp(a)),
  },
];

// ---- running a tool -------------------------------------------------------------------------------------

/** Keeps one tool result inside a sane context budget. */
export const MAX_RESULT_CHARS = 30000;

export async function runTool(tool: Tool, args: Args): Promise<string> {
  const r = await tool.run(args);
  const view = args.view === "full" ? undefined : tool.compact;
  const out = {
    data: view ? view(r.data) : r.data,
    as_of: r.as_of,
    cite_as: r.cite_as,
    source: r.source,
    ...(r.verification ? { verification: r.verification } : {}),
    ...(r.note ? { note: r.note } : {}),
    ...(r.next_cursor ? { next_cursor: r.next_cursor } : {}),
    license: LICENSE,
  };
  const text = JSON.stringify(out);
  return text.length <= MAX_RESULT_CHARS
    ? text
    : `${text.slice(0, MAX_RESULT_CHARS)}\n[truncated at ${MAX_RESULT_CHARS} characters: narrow the request (limit, filters) or use the REST API at ${r.cite_as} for the full document]`;
}

/** MCP arguments arrive as JSON values; ops take strings. Non-scalar values are rejected upstream by validation. */
export function toArgs(raw: unknown): Args {
  const out: Args = {};
  if (!isObj(raw)) return out;
  for (const [k, v] of Object.entries(raw)) {
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") out[k] = String(v);
  }
  return out;
}
