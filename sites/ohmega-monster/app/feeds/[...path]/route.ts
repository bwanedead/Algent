import { intelDoc } from "@/lib/store";

// The agent feeds, served from the database at the same public URLs the static files used to have (next.config
// rewrites /data/* to this route BEFORE the filesystem check, so a stale committed public/data file can never shadow
// the live document):
// /data/index.json, /data/articles/<slug>.json, /data/intel.json, /data/pulses.json, /data/changes.json,
// /data/forecasts.json, /data/daily/<domain>/<date>.json, /data/briefs/<slug>.json, /data/theaters/<id>.json,
// /data/actors/<ISO2>.json, /data/record.json … Each is the document `data/<path>` in
// published_intel_documents (lib/store.ts falls back to public/data/<path> during the transition).
// Contract: docs/architecture/published-content.md; the feed shapes are documented in public/llms.txt.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

const SEGMENT = /^[\w.-]+$/;

/** The document path for a request, or null when it could not name a feed (traversal, non-JSON, odd characters). */
function feedPath(segments: string[]): string | null {
  if (segments.length === 0 || !segments.every((s) => SEGMENT.test(s) && !s.includes(".."))) return null;
  return segments[segments.length - 1].endsWith(".json") ? `data/${segments.join("/")}` : null;
}

export async function GET(_req: Request, { params }: { params: { path: string[] } }): Promise<Response> {
  const rel = feedPath(params.path ?? []);
  const body = rel ? await intelDoc(rel) : null;
  if (body === null || body === undefined) {
    return new Response(JSON.stringify({ error: "not found" }), { status: 404, headers: { "content-type": "application/json" } });
  }
  return new Response(`${JSON.stringify(body, null, 2)}\n`, {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, s-maxage=300, stale-while-revalidate=3600",
    },
  });
}
