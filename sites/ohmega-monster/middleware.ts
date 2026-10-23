import { NextResponse, type NextRequest } from "next/server";

import { clientOf, surfaceOf, take, type Verdict } from "./lib/api/ratelimit";

// THE seam for API access control (docs/architecture/agent-api.md, "Keys and monetization"). Every /api/* request
// passes through `gate` before any handler runs. Today the API is public and read-only, with one control: a per-IP
// token bucket on the agent surfaces (/api/v1 and /api/mcp; lib/api/ratelimit.ts documents the limits and why). The site's
// own internal endpoints (/api/globe/*) are not limited.
// To add an API-key tier later, change ONLY this function: read `X-Api-Key` / `Authorization: Bearer ...`, look the
// key up (edge-safe store such as Edge Config / KV), and either return `NextResponse.json({error}, {status: 401|429})`
// or tag the request (e.g. an `x-ohmega-tier` header) for handlers and the CDN cache key. Keep this file free of
// node-only imports: it runs on the edge.
const EXPOSE = "Retry-After, X-RateLimit-Limit, X-RateLimit-Remaining";

function limitHeaders(v: Verdict): Record<string, string> {
  return { "x-ratelimit-limit": String(v.limit), "x-ratelimit-remaining": String(v.remaining), ...(v.allowed ? {} : { "retry-after": String(v.retryAfterSeconds) }) };
}

export function middleware(req: NextRequest): NextResponse {
  const surface = req.method === "OPTIONS" ? null : surfaceOf(req.nextUrl.pathname); // a CORS preflight costs nothing and must always answer
  if (!surface) return NextResponse.next();
  const verdict = take(surface, clientOf(req.headers), Date.now());
  if (!verdict.allowed) {
    return NextResponse.json(
      { error: { code: "rate_limited", message: `Too many requests: ${verdict.limit} a minute are allowed on ${surface.prefix}. Retry in ${verdict.retryAfterSeconds} s.` }, meta: { version: "v1" } },
      { status: 429, headers: { ...limitHeaders(verdict), "access-control-allow-origin": "*", "access-control-expose-headers": EXPOSE, "cache-control": "no-store" } },
    );
  }
  const res = NextResponse.next();
  for (const [k, v] of Object.entries(limitHeaders(verdict))) res.headers.set(k, v);
  return res;
}

export const config = { matcher: ["/api/:path*"] };
