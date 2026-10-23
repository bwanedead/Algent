import { SITE_URL } from "@/lib/site";

import { ApiError, type ApiResult } from "./util";

// The response contract of /api/v1: one envelope, one set of headers, in one place.
//   { data, meta: { as_of, source, version, cite_as, license, verification?, note?, provenance?, basis?, next? } }
// Errors: { error: { code, message }, meta: { version } }. Docs: docs/architecture/agent-api.md.

export const API_VERSION = "v1";
export const LICENSE =
  "Ohmega claims, summaries, grades, Pulses and forecasts may be quoted with a link to cite_as. Source texts belong to their publishers; follow the source URLs. No warranty: readings are our assessment as of as_of, not guarantees.";

export const CORS: Record<string, string> = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, HEAD, OPTIONS",
  "access-control-allow-headers": "Content-Type, Authorization, X-Api-Key",
  "access-control-max-age": "86400",
};

/** CDN-cacheable: the data changes a few times a day and the site itself revalidates every 300 s. */
export const CACHE_OK = "public, s-maxage=300, stale-while-revalidate=3600";
const CACHE_MISS = "public, s-maxage=60";

const JSON_TYPE = "application/json; charset=utf-8";

export function preflight(): Response {
  return new Response(null, { status: 204, headers: CORS });
}

/** `?cursor=` swapped into the request's own URL: a ready-to-fetch link to the next page. */
function nextUrl(req: Request, cursor: string | null | undefined): string | undefined {
  if (!cursor) return undefined;
  const u = new URL(req.url);
  u.searchParams.set("cursor", cursor);
  return `${SITE_URL}${u.pathname}${u.search}`;
}

export function respond(req: Request, r: ApiResult): Response {
  const meta: Record<string, unknown> = {
    as_of: r.as_of || null,
    source: r.source,
    version: API_VERSION,
    cite_as: r.cite_as,
    license: LICENSE,
    ...(r.verification ? { verification: r.verification } : {}),
    ...(r.note ? { note: r.note } : {}),
    ...(r.provenance ? { provenance: r.provenance } : {}),
    ...(r.basis && r.basis.length > 0 ? { basis: r.basis } : {}),
  };
  const next = nextUrl(req, r.next_cursor);
  if (next) meta.next = next;
  return new Response(JSON.stringify({ data: r.data, meta }), {
    headers: { "content-type": JSON_TYPE, "cache-control": CACHE_OK, ...CORS },
  });
}

export function fail(e: unknown): Response {
  const err = e instanceof ApiError ? e : new ApiError(500, "internal", "unexpected error");
  return new Response(JSON.stringify({ error: { code: err.code, message: err.message }, meta: { version: API_VERSION } }), {
    status: err.status,
    headers: { "content-type": JSON_TYPE, "cache-control": err.status === 404 ? CACHE_MISS : "no-store", ...CORS },
  });
}

/** A plain JSON body (the OpenAPI document) with the same CORS and caching. */
export function jsonResponse(body: unknown, cache: string = CACHE_OK): Response {
  return new Response(JSON.stringify(body), { headers: { "content-type": JSON_TYPE, "cache-control": cache, ...CORS } });
}
