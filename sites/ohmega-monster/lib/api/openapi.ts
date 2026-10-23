import { SITE_URL } from "@/lib/site";

import { API_VERSION, LICENSE } from "./envelope";
import { pagingParams, ROUTES, type QueryParam, type Route } from "./router";

// The OpenAPI 3.1 document for /api/v1, built from the route table (lib/api/router.ts) so the spec and the
// dispatcher cannot drift. The envelope and error schemas are written out here. Served at /api/v1/openapi.json.

const envelope = {
  type: "object",
  required: ["data", "meta"],
  properties: {
    data: { description: "The endpoint's payload. Its shape follows the published document named in meta.source." },
    meta: {
      type: "object",
      required: ["as_of", "source", "version", "cite_as", "license"],
      properties: {
        as_of: { type: ["string", "null"], description: "Freshness of the underlying data (ISO date or instant)." },
        source: { type: "string", description: "Schema or table the data came from, e.g. ohmega.daily/1." },
        version: { type: "string", example: API_VERSION },
        cite_as: { type: "string", format: "uri", description: "Canonical human URL to cite." },
        license: { type: "string" },
        verification: { type: "string", description: "Present when the whole response has one verification level; items carry their own otherwise." },
        note: { type: "string", description: "A caveat to keep when you repeat the data." },
        provenance: { type: "object", description: "Corpus-backed endpoints: the products and documents the server-built view was derived from. Records inside also carry their own product, origin and source URLs." },
        basis: { type: "array", items: { type: "string" }, description: "Corpus-backed endpoints: the kinds of number in the data, in the stats-registry vocabulary (official, our_count, our_derived, model, reported ...)." },
        next: { type: "string", format: "uri", description: "URL of the next page, when there is one." },
      },
    },
  },
};

const errorBody = {
  type: "object",
  required: ["error", "meta"],
  properties: {
    error: { type: "object", required: ["code", "message"], properties: { code: { type: "string", enum: ["bad_request", "not_found", "internal"] }, message: { type: "string" } } },
    meta: { type: "object", properties: { version: { type: "string" } } },
  },
};

const queryParam = (p: QueryParam) => ({
  name: p.name,
  in: "query",
  required: false,
  description: p.description,
  schema: { type: "string", ...(p.enum ? { enum: [...p.enum] } : {}) },
  ...(p.example ? { example: p.example } : {}),
});

function operation(r: Route) {
  const path = Object.entries(r.pathParams ?? {}).map(([name, p]) => ({
    name,
    in: "path",
    required: true,
    description: p.description,
    schema: { type: "string" },
    example: p.example,
  }));
  const query = [...(r.query ?? []), ...(r.paged ? pagingParams() : [])].map(queryParam);
  return {
    get: {
      operationId: r.path.replace(/[{}]/g, "").split("/").filter(Boolean).join("_"),
      summary: r.summary,
      parameters: [...path, ...query],
      responses: {
        "200": { description: "The envelope: {data, meta}.", content: { "application/json": { schema: { $ref: "#/components/schemas/Envelope" } } } },
        "400": { description: "A parameter is malformed.", content: { "application/json": { schema: { $ref: "#/components/schemas/Error" } } } },
        "404": { description: "Nothing published under that id.", content: { "application/json": { schema: { $ref: "#/components/schemas/Error" } } } },
      },
    },
  };
}

export function openApiDocument(): Record<string, unknown> {
  return {
    openapi: "3.1.0",
    info: {
      title: "Ohmega Monster agent API",
      version: "1.0.0",
      summary: "Read-only JSON over the claim/profile corpus behind ohmega.monster.",
      description:
        "Daily intelligence reports, theater dossiers, Pulses (0-100 readings with history), articles with graded claims, on-the-record statements, actor profiles, measured series and live events. Every response is {data, meta} with as_of, cite_as, source and license; list endpoints page with limit and cursor. Public, no authentication. A remote MCP server exposes the same operations at /api/mcp. Human guide: /developers.",
      license: { name: "Quote with a link", url: `${SITE_URL}/developers#terms` },
      "x-terms": LICENSE,
    },
    servers: [{ url: `${SITE_URL}/api/v1` }],
    externalDocs: { description: "Developer guide, MCP setup, examples", url: `${SITE_URL}/developers` },
    paths: Object.fromEntries(ROUTES.map((r) => [r.path, operation(r)])),
    components: { schemas: { Envelope: envelope, Error: errorBody } },
  };
}
