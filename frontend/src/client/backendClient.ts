/**
 * Thin client for talking to the Python backend.
 *
 * The transport is intentionally simple: plain HTTP with JSON. Replace or
 * augment with websockets, streaming, or Tauri commands later.
 */
const BASE_URL = "http://127.0.0.1:43145";

export type CommandRequest = {
  name: string;
  payload?: Record<string, unknown>;
  source?: string;
};

export type CommandResponse = Record<string, unknown>;

export type ProviderId = "openai" | "anthropic" | "gemini" | "xai";

export async function sendCommand(
  command: CommandRequest,
): Promise<CommandResponse> {
  // TODO: add error handling/retries once backend contract stabilizes.
  const res = await fetch(`${BASE_URL}/commands`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(command),
  });

  if (!res.ok) {
    return { status: "error", message: `HTTP ${res.status}` };
  }

  return (await res.json()) as CommandResponse;
}

export async function fetchHealth(): Promise<CommandResponse> {
  const res = await fetch(`${BASE_URL}/health`);
  if (!res.ok) {
    return { status: "error", message: `HTTP ${res.status}` };
  }
  return (await res.json()) as CommandResponse;
}

export async function saveApiKey(
  provider: ProviderId,
  apiKey: string,
): Promise<CommandResponse> {
  const res = await fetch(`${BASE_URL}/credentials`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ provider, api_key: apiKey }),
  });

  if (!res.ok) {
    return { status: "error", message: `HTTP ${res.status}` };
  }

  return (await res.json()) as CommandResponse;
}
