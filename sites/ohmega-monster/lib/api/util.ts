import { SITE_URL } from "@/lib/site";
import { intelDoc } from "@/lib/store";

// Small shared helpers for the agent API (docs/architecture/agent-api.md). Server-side only (reads lib/store.ts).

export type Obj = Record<string, unknown>;
export const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
export const str = (v: unknown): string => (typeof v === "string" ? v : typeof v === "number" ? String(v) : "");
export const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
export const objs = (v: unknown): Obj[] => arr(v).filter(isObj);

/** Request arguments as ops see them: path params and query merged, all optional strings. */
export type Args = Record<string, string | undefined>;

/** What every op hands back; the REST layer wraps it in the envelope, the MCP layer prints it. */
export type ApiResult = {
  data: unknown;
  /** Freshness of the underlying data ("" / null when the data carries none). */
  as_of: string | null;
  /** Canonical human URL (absolute). */
  cite_as: string;
  /** The published document schema or table the data came from, e.g. "ohmega.daily/1". */
  source: string;
  /** Set only when the whole response has one verification level. Items carry their own otherwise. */
  verification?: string;
  /** Caveat the consumer must keep (e.g. "said, not true"). */
  note?: string;
  /** Opaque cursor for the next page, when there is one. */
  next_cursor?: string | null;
  /** Which products and documents the data was derived from (a server-built view's provenance block). */
  provenance?: unknown;
  /** The kinds of number the data holds, in the stats-registry vocabulary (official, our_count, our_derived, model, reported ...), when it holds any. */
  basis?: string[];
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}
export const notFound = (what: string) => new ApiError(404, "not_found", `${what} not found`);
export const badRequest = (msg: string) => new ApiError(400, "bad_request", msg);

/** Absolute URL on the site for a site-relative path (absolute URLs pass through). */
export const abs = (p: string): string => (/^https?:\/\//.test(p) ? p : `${SITE_URL}${p.startsWith("/") ? "" : "/"}${p}`);

/** A published JSON document as an object, or null. */
export async function docObj(path: string): Promise<Obj | null> {
  const d = await intelDoc(path);
  return isObj(d) ? d : null;
}

export const ID_RE = /^[\w.-]+$/;
export const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const SINCE_RE = /^\d{4}-\d{2}-\d{2}([T ][\d:.]+Z?)?$/;

export function idParam(name: string, v: string | undefined): string {
  if (!v || !ID_RE.test(v) || v.includes("..")) throw badRequest(`${name} must be an id (letters, digits, - _ .)`);
  return v;
}

/** A `since` filter: YYYY-MM-DD or an ISO instant. "" when absent. */
export function sinceParam(v: string | undefined): string {
  if (!v) return "";
  if (!SINCE_RE.test(v)) throw badRequest("since must be YYYY-MM-DD or an ISO 8601 instant");
  return v;
}

export function enumParam<T extends string>(name: string, v: string | undefined, allowed: readonly T[]): T | "" {
  if (!v) return "";
  if (!(allowed as readonly string[]).includes(v)) throw badRequest(`${name} must be one of: ${allowed.join(", ")}`);
  return v as T;
}

export const lower = (v: string | undefined): string => (v ?? "").trim().toLowerCase();

// ---- pagination: opaque offset cursor, bounded page size --------------------------------------------

export const DEFAULT_LIMIT = 50;
export const MAX_LIMIT = 200;

export function limitParam(v: string | number | undefined, def = DEFAULT_LIMIT, max = MAX_LIMIT): number {
  if (v === undefined || v === "") return def;
  const n = Number(v);
  if (!Number.isInteger(n) || n < 1) throw badRequest("limit must be a positive integer");
  return Math.min(n, max);
}

export type Paged<T> = { items: T[]; next_cursor: string | null; total: number };

export function paginate<T>(all: T[], limit: number, cursor: string | undefined): Paged<T> {
  const start = cursor && /^\d+$/.test(cursor) ? Number(cursor) : 0;
  const items = all.slice(start, start + limit);
  return { items, next_cursor: start + limit < all.length ? String(start + limit) : null, total: all.length };
}

/** The newest of several timestamps / dates (string compare is correct for ISO forms); null when none. */
export const newest = (...xs: (string | null | undefined)[]): string | null => xs.filter((x): x is string => !!x).sort().pop() ?? null;
