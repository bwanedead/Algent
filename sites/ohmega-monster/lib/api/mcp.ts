import { SITE_URL } from "@/lib/site";

import { runTool, toArgs, TOOLS } from "./mcp-tools";
import { ApiError, isObj, str } from "./util";

// A minimal, stateless MCP server over Streamable HTTP (JSON-RPC 2.0), no SDK. Implements the server side of
// `initialize`, `ping`, `tools/list` and `tools/call` against the 2025-06-18 spec, and negotiates down to
// 2025-03-26 and 2024-11-05. Every reply is one application/json response (no SSE stream, no sessions), which the
// transport allows: POST only; GET and DELETE answer 405. The route is app/api/mcp/route.ts.

export const SUPPORTED_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"] as const;
const LATEST = SUPPORTED_VERSIONS[0];

const SERVER_INFO = { name: "ohmega-monster", title: "Ohmega Monster", version: "1.0.0" };
const INSTRUCTIONS =
  `Read-only access to Ohmega Monster's intelligence corpus: daily reports, theater dossiers, Pulses (0-100 readings), statements on the record, measured series and live events. ` +
  `Start with get_daily (newest report), list_pulses or search. Every result carries as_of and cite_as: cite cite_as and the as_of date when you use it. ` +
  `Items marked verification 'reported' are leads from other outlets, not findings. Statements prove something was said, not that it is true. ` +
  `API docs: ${SITE_URL}/developers`;

// JSON-RPC error codes
const PARSE_ERROR = -32700;
const INVALID_REQUEST = -32600;
const METHOD_NOT_FOUND = -32601;
const INVALID_PARAMS = -32602;
const INTERNAL_ERROR = -32603;

type Id = string | number | null;
export type RpcResponse = { jsonrpc: "2.0"; id: Id } & ({ result: unknown } | { error: { code: number; message: string } });

const ok = (id: Id, result: unknown): RpcResponse => ({ jsonrpc: "2.0", id, result });
const err = (id: Id, code: number, message: string): RpcResponse => ({ jsonrpc: "2.0", id, error: { code, message } });

/** One JSON-RPC message in, one response out; null for notifications and client responses (nothing to send). */
export async function handleMessage(msg: unknown): Promise<RpcResponse | null> {
  if (!isObj(msg) || msg.jsonrpc !== "2.0") return err(null, INVALID_REQUEST, "Invalid Request: expected a JSON-RPC 2.0 object");
  const hasId = typeof msg.id === "string" || typeof msg.id === "number";
  const id: Id = hasId ? (msg.id as string | number) : null;
  const method = msg.method;
  if (typeof method !== "string") {
    // A response from the client (result/error, no method) is acknowledged by saying nothing.
    return "result" in msg || "error" in msg ? null : err(id, INVALID_REQUEST, "Invalid Request: method is required");
  }
  if (!hasId) return null; // a notification (e.g. notifications/initialized): accepted, no reply
  const params = isObj(msg.params) ? msg.params : {};

  switch (method) {
    case "initialize": {
      const asked = str(params.protocolVersion);
      const version = (SUPPORTED_VERSIONS as readonly string[]).includes(asked) ? asked : LATEST;
      return ok(id, { protocolVersion: version, capabilities: { tools: { listChanged: false } }, serverInfo: SERVER_INFO, instructions: INSTRUCTIONS });
    }
    case "ping":
      return ok(id, {});
    case "tools/list":
      return ok(id, {
        tools: TOOLS.map((t) => ({
          name: t.name,
          title: t.title,
          description: t.description,
          inputSchema: t.inputSchema,
          annotations: { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false },
        })),
      });
    case "tools/call": {
      const tool = TOOLS.find((t) => t.name === str(params.name));
      if (!tool) return err(id, INVALID_PARAMS, `Unknown tool: ${str(params.name) || "(missing name)"}`);
      try {
        const text = await runTool(tool, toArgs(params.arguments));
        return ok(id, { content: [{ type: "text", text }], isError: false });
      } catch (e) {
        // A tool failure is a tool result with isError (the model can read and recover), not a protocol error.
        const message = e instanceof ApiError ? e.message : "The tool failed unexpectedly.";
        return ok(id, { content: [{ type: "text", text: message }], isError: true });
      }
    }
    default:
      return err(id, METHOD_NOT_FOUND, `Method not found: ${method}`);
  }
}

export const parseError = (): RpcResponse => err(null, PARSE_ERROR, "Parse error: body is not valid JSON");
export const internalError = (): RpcResponse => err(null, INTERNAL_ERROR, "Internal error");
export const invalidRequest = (message: string): RpcResponse => err(null, INVALID_REQUEST, message);
