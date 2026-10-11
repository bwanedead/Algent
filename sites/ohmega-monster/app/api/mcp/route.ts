import { SITE_URL } from "@/lib/site";
import { handleMessage, internalError, invalidRequest, parseError, SUPPORTED_VERSIONS, type RpcResponse } from "@/lib/api/mcp";

// Remote MCP server (Streamable HTTP, stateless, JSON replies): POST /api/mcp. Protocol and tools live in
// lib/api/mcp.ts and lib/api/mcp-tools.ts. How to connect a client: /developers#mcp.
export const dynamic = "force-dynamic";

const HEADERS: Record<string, string> = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "POST, GET, DELETE, OPTIONS",
  "access-control-allow-headers": "Content-Type, Accept, Authorization, X-Api-Key, Mcp-Session-Id, MCP-Protocol-Version, Last-Event-ID",
  "access-control-expose-headers": "Mcp-Session-Id",
  "access-control-max-age": "86400",
};

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store", ...HEADERS } });

export async function POST(req: Request): Promise<Response> {
  const version = req.headers.get("mcp-protocol-version");
  if (version && !(SUPPORTED_VERSIONS as readonly string[]).includes(version)) {
    return json(invalidRequest(`Unsupported MCP-Protocol-Version: ${version}`), 400);
  }
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return json(parseError(), 400);
  }
  try {
    if (Array.isArray(body)) {
      if (body.length === 0) return json(invalidRequest("Invalid Request: empty batch"), 400);
      const replies = (await Promise.all(body.map(handleMessage))).filter((r): r is RpcResponse => r !== null);
      return replies.length > 0 ? json(replies) : new Response(null, { status: 202, headers: HEADERS });
    }
    const reply = await handleMessage(body);
    if (reply === null) return new Response(null, { status: 202, headers: HEADERS });
    // A malformed request object is a client error; everything else (including JSON-RPC errors for a known id) is 200.
    return json(reply, "error" in reply && reply.id === null ? 400 : 200);
  } catch {
    return json(internalError(), 500);
  }
}

// No server-initiated stream and no sessions: the spec lets a server answer 405 to GET (SSE) and DELETE (end session).
const NOT_ALLOWED = (): Response =>
  new Response(JSON.stringify({ error: `This MCP endpoint accepts POST (JSON-RPC 2.0). See ${SITE_URL}/developers#mcp` }), {
    status: 405,
    headers: { allow: "POST, OPTIONS", "content-type": "application/json", ...HEADERS },
  });

export const GET = NOT_ALLOWED;
export const DELETE = NOT_ALLOWED;

export function OPTIONS(): Response {
  return new Response(null, { status: 204, headers: HEADERS });
}
