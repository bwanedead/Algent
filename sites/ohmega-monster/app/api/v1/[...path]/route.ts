import { preflight } from "@/lib/api/envelope";
import { handleApi } from "@/lib/api/handler";

// The versioned read-only agent API: /api/v1/<endpoint>. One catch-all; the route table is lib/api/router.ts and the
// spec is /api/v1/openapi.json. Computed per request, cached at the CDN by the s-maxage header (lib/api/envelope.ts);
// the underlying reads use the site's 300 s data cache. Contract: docs/architecture/agent-api.md.
export const dynamic = "force-dynamic";

export async function GET(req: Request, { params }: { params: { path: string[] } }): Promise<Response> {
  return handleApi(req, params.path ?? []);
}

export function OPTIONS(): Response {
  return preflight();
}
