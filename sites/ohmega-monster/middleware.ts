import { NextResponse, type NextRequest } from "next/server";

// THE seam for API access control (docs/architecture/agent-api.md, "Keys and monetization"). Every /api/* request
// passes through `gate` before any handler runs. Today it lets everything through: the API is public and read-only.
// To add an API-key tier later, change ONLY this function: read `X-Api-Key` / `Authorization: Bearer ...`, look the
// key up (edge-safe store such as Edge Config / KV), and either return `NextResponse.json({error}, {status: 401|429})`
// or tag the request (e.g. an `x-ohmega-tier` header) for handlers and the CDN cache key. Keep this file free of
// node-only imports: it runs on the edge.
function gate(_req: NextRequest): NextResponse | null {
  return null; // null = proceed
}

export function middleware(req: NextRequest): NextResponse {
  return gate(req) ?? NextResponse.next();
}

export const config = { matcher: ["/api/:path*"] };
