import { ASSET_STATUSES, ASSET_TYPES } from "@/lib/geoledger-shared";

import { LICENSE } from "./envelope";
import { assetOp, assetsOp, gridOp } from "./ops-assets";
import { searchOp } from "./ops-content";
import { anomaliesOp, instrumentOp, instrumentsOp, liveEventsOp } from "./ops-data";
import { calendarOp, sanctionsOp } from "./ops-forward";
import { aboutOp, entityOp, relatedOp, seriesOp, timelineOp } from "./ops-corpus";
import { maritimeOp } from "./ops-maritime";
import { KIND_ORDER as MARITIME_KINDS } from "@/lib/maritime-shared";
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
    description:
      "Text search over titles, headlines and names of articles, theaters, Pulses, briefs, daily reports and actors, and over the corpus: any country, organisation, person, place, vessel, lab, model or situation by name or alias (type entity; open one with the entity tool) and document titles (type document). Names and titles only, not document bodies. Returns ids and citable URLs; fetch details with the matching tool or the result's api_url.",
    inputSchema: schema(
      { q: str_("Query words (all must match)."), type: str_("Restrict to one kind.", { enum: ["article", "theater", "pulse", "brief", "daily", "actor", "entity", "document"] }), limit: limit_(20), cursor: cursor_ },
      ["q"],
    ),
    run: searchOp,
  },
  {
    name: "entity",
    title: "Entity from the corpus",
    description:
      "Who or what a name is, from the corpus behind the reports: a country, organisation, person, place, vessel, lab, model or situation. Returns aliases, counts, the latest status, typed relations (head of state, affiliated with, stance...), what it is most connected to, its measured series (each with a basis: official, our_count, our_derived, model, reported) and the newest documents, claims and events with their sources. An ambiguous name returns alternatives (pass key to choose); a country wins over a same-named place. Use about, timeline, related and series for more.",
    inputSchema: schema({ name: str_("A name or alias, e.g. 'Strait of Hormuz', 'IRGC', 'France'."), key: str_("A key from a previous result's match.key (wins over the name), e.g. entity/org/nato.") }),
    run: entityOp,
  },
  {
    name: "about",
    title: "Everything about an entity since a date",
    description:
      "Documents (dailies, briefs, profiles, statements, articles), claims (with grounding, confidence and source URLs) and events about an entity, newest first, each with the product and record it came from. The corpus holds the newest material per entity (about 15 documents, 10 claims, 15 events); the result says when a since is older than that.",
    inputSchema: schema({
      entity: str_("A name or alias."),
      key: str_("A key from a previous result (wins over entity)."),
      since: str_("Only on or after this date (YYYY-MM-DD)."),
      kinds: str_("Comma-separated. claim, event, document select whole sections; any other value filters by item kind (daily, brief, profile, development ...)."),
      limit: limit_(30),
    }),
    run: aboutOp,
  },
  {
    name: "timeline",
    title: "Timeline of an entity",
    description: "An entity's documents and events in date order (oldest first), each with sources; a development repeated across reports appears once.",
    inputSchema: schema({ entity: str_("A name or alias."), key: str_("A key from a previous result."), since: str_("Only on or after this date (YYYY-MM-DD)."), limit: limit_(50) }),
    run: timelineOp,
  },
  {
    name: "related",
    title: "What an entity is connected to",
    description:
      "What an entity is most connected to and why: typed edges x3, shared claims x2, shared events x1.5, shared documents x1 (the parts are shown, so you can see whether a link was stated or only co-occurred), plus the typed relations with their evidence.",
    inputSchema: schema({ entity: str_("A name or alias."), key: str_("A key from a previous result."), kinds: str_("Only related entities of these kinds, comma-separated (country, org, person, place ...)."), limit: limit_(15) }),
    run: relatedOp,
  },
  {
    name: "series",
    title: "Measured series from the corpus",
    description:
      "A measured series with its unit and basis (official = published by the body that measures it; our_count = a minimum from our receivers; our_derived = our computation; model = a model's reading; reported = a figure a source cited): one metric across the entities that have it (gdp, population, chk_hormuz_transits, bench.* ...), or one entity's own series (pass entity or key). A name matching several metrics returns the candidates.",
    inputSchema: schema({
      metric: str_("A metric id, or the start of one ending in . or * to list a family, e.g. gdp, chk_hormuz_transits, bench."),
      entity: str_("An entity whose own series to return."),
      key: str_("A key from a previous result."),
      since: str_("Only points on or after this date or year."),
      limit: limit_(30),
      cursor: cursor_,
    }),
    run: seriesOp,
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
    name: "get_live_anomalies",
    title: "Live anomalies",
    description:
      "Ohmega's own analysis of where live ship, aircraft and satellite-fire counts depart from their learned normal for that place and hour of the week: each with place, how far (ratio and a plain sentence), how long, confidence and whether the baseline is still learning. Original analysis (ohmega_derived), not reported by any source; it shows a pattern departs from normal, not why. Receiver-coverage gaps are screened out.",
    inputSchema: schema({
      layer: str_("What is counted.", { enum: ["ship", "air", "fire"] }),
      direction: str_("Above or below normal.", { enum: ["above", "below"] }),
      active: str_("true: still going; false: recently closed.", { enum: ["true", "false"] }),
      country: str_("Country name as the desk writes it, e.g. Iran."),
      since: str_("Only started on or after this date or ISO instant."),
      limit: limit_(20),
      cursor: cursor_,
    }),
    run: anomaliesOp,
  },
  {
    name: "get_calendar",
    title: "What is coming",
    description:
      "Dated upcoming items, soonest first: elections, central-bank rate decisions (Fed, ECB, Bank of England), UN Security Council meetings, OPEC+ meetings, and deadlines or meetings Ohmega's own reports named. Each has a source URL and a confidence (high = official schedule, medium = compiled from announcements, low = extracted from our earlier reports and unconfirmed). A date is a plan, not an outcome.",
    inputSchema: schema({
      kind: str_("Kind of item.", { enum: ["election", "central_bank", "summit", "security_council", "opec", "deadline", "vote"] }),
      country: str_("ISO alpha-2 code the item concerns, e.g. US."),
      confidence: str_("Confidence.", { enum: ["high", "medium", "low"] }),
      days: str_("Days ahead (default 45, max 240)."),
      limit: limit_(30),
      cursor: cursor_,
    }),
    run: calendarOp,
  },
  {
    name: "get_sanctions",
    title: "Sanctions designations",
    description:
      "Who was added to or removed from the US OFAC SDN list, the UK Sanctions List and the EU consolidated financial sanctions list, found by comparing each list with its previous copy: name, kind (person, entity, vessel, aircraft), programme, countries, date, and the list it came from. A listing is an act of the publishing government, not a finding of guilt.",
    inputSchema: schema({
      list: str_("Which list.", { enum: ["ofac", "uk", "eu"] }),
      action: str_("Added or removed.", { enum: ["designated", "delisted"] }),
      type: str_("Kind of party.", { enum: ["person", "entity", "vessel", "aircraft"] }),
      country: str_("ISO alpha-2 code the party is tied to, e.g. RU."),
      since: str_("Only on or after this date."),
      limit: limit_(30),
      cursor: cursor_,
    }),
    run: (a) => sanctionsOp({ ...a, source: a.list }),
  },
  {
    name: "get_maritime_behaviour",
    title: "Vessel behaviour events",
    description:
      "Ohmega's own analysis of the ship positions it hears (AIS): vessels that went silent where other ships kept being heard (ais_gap), ship-to-ship encounters in open water (sts), identity changes (renames, IMO or flag changes), vessels matching a sanctions designation (sanctioned) and long dwells over chokepoints or cable corridors (loiter). Each event has why_flagged, a confidence and evidence points. Original analysis (ohmega_derived), not reported by any source: a pattern seen, never a finding of intent. Receiver-coverage gaps, ports and anchorage crowds are screened out.",
    inputSchema: schema({
      kind: str_("Kind of behaviour.", { enum: [...MARITIME_KINDS] }),
      active: str_("true: still going; false: ended.", { enum: ["true", "false"] }),
      flag: str_("ISO alpha-2 flag state of a vessel involved, e.g. PA."),
      area: str_("Part of an area name, or a country the area touches, e.g. Hormuz."),
      imo: str_("7-digit IMO number."),
      mmsi: str_("9-digit MMSI."),
      min_confidence: str_("Only at or above this confidence, 0 to 1."),
      since: str_("Only started on or after this date or ISO instant."),
      limit: limit_(20),
      cursor: cursor_,
    }),
    run: maritimeOp,
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
    ...(r.provenance ? { provenance: r.provenance } : {}),
    ...(r.basis && r.basis.length > 0 ? { basis: r.basis } : {}),
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
