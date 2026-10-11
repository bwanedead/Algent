import { SITE_URL } from "@/lib/site";

import { TOOLS } from "./mcp-tools";
import { articlesOp } from "./ops-content";
import { dailyOp } from "./ops-desk";
import { ROUTES } from "./router";
import { isObj, objs, str } from "./util";

// The long-form machine guide served at /llms-full.txt: llms.txt's pointers expanded into the whole API surface and
// data model, generated from the route table and tool list so it cannot drift, plus a small "what is here now" block.

async function now(): Promise<string> {
  const lines: string[] = [];
  try {
    const d = (await dailyOp({})).data;
    if (isObj(d)) lines.push(`- Newest daily report: ${str(d.date)}: ${str(d.headline)} (${SITE_URL}/api/v1/daily/geopolitics/latest)`);
  } catch {
    /* no report yet: say nothing */
  }
  try {
    const a = (await articlesOp({ limit: "8" })).data;
    for (const x of objs(isObj(a) ? a.articles : [])) lines.push(`- Article ${str(x.published_at).slice(0, 10)}: ${str(x.title)} (${str(x.cite_as)})`);
  } catch {
    /* no articles: say nothing */
  }
  return lines.length > 0 ? lines.join("\n") : "- (nothing published yet)";
}

export async function llmsFull(): Promise<string> {
  const endpoints = ROUTES.map((r) => {
    const params = [...Object.keys(r.pathParams ?? {}), ...(r.query ?? []).map((q) => `?${q.name}`), ...(r.paged ? ["?limit", "?cursor"] : [])];
    return `- GET /api/v1${r.path}${params.length > 0 ? `  [${params.join(" ")}]` : ""}\n  ${r.summary}`;
  }).join("\n");
  const tools = TOOLS.map((t) => `- ${t.name}: ${t.description}`).join("\n");
  return `# Ohmega Monster: full guide for agents

> An intelligence engine: researched, graded reporting on world events, published as data. Prefer the API and
> feeds to scraping HTML. Short version: ${SITE_URL}/llms.txt . Human guide with examples: ${SITE_URL}/developers .

## Surfaces

- REST API (JSON, read-only, public, CORS open): ${SITE_URL}/api/v1/index . OpenAPI 3.1: ${SITE_URL}/api/v1/openapi.json
- MCP server (Streamable HTTP, stateless): ${SITE_URL}/api/mcp
- Static feeds (same documents, no API logic): ${SITE_URL}/data/intel.json , /data/changes.json , /data/pulses.json , /data/forecasts.json
- RSS of articles: ${SITE_URL}/feed.xml

## Response contract

Every API response is {data, meta}. meta carries as_of (freshness of the data), source (the document schema it
came from), version, cite_as (canonical human URL: cite it), license, and sometimes verification, note and next
(URL of the next page). Lists page with ?limit= (max 200) and ?cursor=. Errors are {error:{code,message}}.
Cache: responses are CDN-cached for about five minutes; poll /api/v1/changes rather than re-reading everything.

## Data model

- Daily report (ohmega.daily/1): per theater, developments (headline, detail, where, sources[], verification),
  who said what, context, outlook, what to watch, Pulse positions; plus a world sweep of what the focus under-weights.
- Theater: one running situation with a living dossier (timeline, places, actors, Pulses, forecasts, statements).
  heat means how much it is in the news, not how bad it is.
- Pulse: a persistent 0-100 reading of one question (0 the calm end, 100 the extreme end; low_end / high_end say
  what the ends mean), with band (calm, elevated, severe, critical), confidence and a full reading history. Early
  readings, still calibrating. mode 'audit' readings are blind checks that never move the Pulse.
- Statement: something a named person or body said (exact words only when quote is set). Proves it was said, not
  that it is true. signal: threat, warning, red_line, commitment, offer, demand, reassurance, accusation, denial...;
  stance -2 hostile to +2 conciliatory toward the target.
- Article: markdown plus graded claims. Grades: confirmed, likely, contested, unconfirmed / speculative (a lead),
  opinion (attributed).
- Instrument: a measured series (ship transits, prices, storage) with source, as_of and an 'unusual' flag against
  its own history. No model in the loop.
- Live event: a current event from public feeds (outages, earthquakes, military aircraft, fires), relayed with its
  source URL and not verified by Ohmega.
- Verification: 'researched' = our research established it; 'reported' = another outlet reported it (a lead, not a
  finding). Treat reported items accordingly.

## Endpoints

${endpoints}

## MCP tools

Endpoint: POST ${SITE_URL}/api/mcp (JSON-RPC 2.0: initialize, tools/list, tools/call). Tools are read-only.

${tools}

## How to cite

Give cite_as and the as_of date. Article claim: article URL + claim id. Pulse: id + reading date. Daily report:
domain + date. Forecast: id (fc_...).

## Terms

Our claims, summaries, grades, Pulses and forecasts may be quoted with a link. Source texts belong to their
publishers; follow the source URLs and do not treat them as ours. No warranty. No authentication today.

## Here now

${await now()}
`;
}
