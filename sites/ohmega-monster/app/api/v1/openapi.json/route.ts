import { jsonResponse, preflight } from "@/lib/api/envelope";
import { openApiDocument } from "@/lib/api/openapi";

// The OpenAPI 3.1 spec of /api/v1, generated from the route table (lib/api/router.ts).
export const dynamic = "force-static";

export function GET(): Response {
  return jsonResponse(openApiDocument(), "public, s-maxage=3600, stale-while-revalidate=86400");
}

export function OPTIONS(): Response {
  return preflight();
}
