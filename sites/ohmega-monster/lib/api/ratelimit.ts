// Per-IP rate limiting for the agent endpoints (/api/v1, /api/mcp): a token bucket per client, held in memory by each edge instance.
// Edge-safe: no node imports (it runs in middleware.ts). Docs: docs/architecture/agent-api.md, "Rate limits".
//
// WHY: the agent API is public and read-only, so a single scraper or a looping agent could push Vercel bandwidth and function time (and, for uncached
// reads, the R2 Class B budget) for everyone. The limit is a seam, not a wall: it is generous for a person or a well-behaved agent and stops a loop.
//
// HOW: each client IP has a bucket of `burst` tokens that refills at `perMinute / 60` tokens a second; a request costs one token. An empty bucket
// answers 429 with Retry-After. The two surfaces have separate buckets (an MCP session makes many small calls; the REST API is cached at the CDN).
//
// LIMITS (per client IP, per edge instance):
//   /api/v1   burst 40, 120 requests a minute sustained
//   /api/mcp  burst 30,  60 requests a minute sustained
// State is per instance: Vercel may run several, so the effective ceiling is that many times higher until the limiter moves to shared storage (Edge Config
// / KV at this same seam - the `take` function below is the only thing that would change). The CDN does not hide a request from this check: middleware
// runs before the cache, so cached reads count too, which is the point (they cost bandwidth).

export type Surface = { prefix: string; burst: number; perMinute: number };

export const SURFACES: Surface[] = [
  { prefix: "/api/mcp", burst: 30, perMinute: 60 },
  { prefix: "/api/v1", burst: 40, perMinute: 120 },
];

/** Most client buckets one instance remembers; the least recently seen are dropped first, so a flood of addresses cannot grow memory without bound. */
const MAX_CLIENTS = 5000;

type Bucket = { tokens: number; at: number };
const buckets = new Map<string, Bucket>();

export type Verdict = { allowed: boolean; limit: number; remaining: number; retryAfterSeconds: number };

/** The surface a path belongs to, or null when it is not limited (the site's own internal endpoints, such as /api/globe, are not). */
export function surfaceOf(pathname: string): Surface | null {
  return SURFACES.find((s) => pathname === s.prefix || pathname.startsWith(`${s.prefix}/`)) ?? null;
}

/** Spend one token of `client`'s bucket on `surface` at time `now` (ms). Pure apart from the in-memory map. */
export function take(surface: Surface, client: string, now: number): Verdict {
  const key = `${surface.prefix}|${client}`;
  const rate = surface.perMinute / 60_000; // tokens per millisecond
  const prev = buckets.get(key);
  const tokens = Math.min(surface.burst, (prev?.tokens ?? surface.burst) + (prev ? (now - prev.at) * rate : 0));
  buckets.delete(key); // re-insert last: Map order is recency order
  if (tokens < 1) {
    buckets.set(key, { tokens, at: now });
    prune();
    return { allowed: false, limit: surface.perMinute, remaining: 0, retryAfterSeconds: Math.max(1, Math.ceil((1 - tokens) / rate / 1000)) };
  }
  buckets.set(key, { tokens: tokens - 1, at: now });
  prune();
  return { allowed: true, limit: surface.perMinute, remaining: Math.floor(tokens - 1), retryAfterSeconds: 0 };
}

function prune(): void {
  while (buckets.size > MAX_CLIENTS) {
    const oldest = buckets.keys().next();
    if (oldest.done) return;
    buckets.delete(oldest.value);
  }
}

/** The client address as the platform reports it (Vercel sets x-forwarded-for; the first entry is the client). "unknown" shares one bucket. */
export function clientOf(headers: { get(name: string): string | null }): string {
  const fwd = headers.get("x-forwarded-for");
  const first = fwd ? fwd.split(",")[0].trim() : "";
  return first || headers.get("x-real-ip")?.trim() || "unknown";
}

/** Test seam: forget every bucket. */
export function reset(): void {
  buckets.clear();
}
