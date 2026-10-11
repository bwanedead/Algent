import { preflight } from "@/lib/api/envelope";
import { handleApi } from "@/lib/api/handler";

// /api/v1 itself answers with the index (same document as /api/v1/index).
export const dynamic = "force-dynamic";

export async function GET(req: Request): Promise<Response> {
  return handleApi(req, ["index"]);
}

export function OPTIONS(): Response {
  return preflight();
}
