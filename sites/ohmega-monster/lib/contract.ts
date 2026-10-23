import table from "./contracts.json";

// The site's side of the versioned contracts between the worker server and the site (docs/architecture/foundation.md, "Contracts between server and site").
//
// Every published document family has a schema id and a MAJOR version, declared once on the server (the product registry) and generated into
// lib/contracts.json. A document carries `"schema": "<id>/<major>"`; one without is a legacy v1. This module is the single gate every reader passes
// through (`publishedDoc` in lib/store.ts, the live snapshot readers): a document whose major this build does not know is NOT parsed, so it can never be
// mis-rendered; the reader sees "not published" (null), the gate remembers why (`updatePending()`), and the page can say an update is pending.
//
// Rollout of a breaking change (the rule is in foundation.md): the site first learns the new major (the server lists it in `accepts`), then the server flips.
// Additive changes never bump the major. Client-safe: no node imports.

type Row = { schema: string; version: number; accepts: number[]; paths: string[]; product: string };
type Compiled = { row: Row; rx: RegExp; rank: [number, number] };

const compile = (glob: string): RegExp => new RegExp(`^${glob.split(/(\*\*|\*)/).map((s) => (s === "**" ? ".+" : s === "*" ? "[^/]+" : s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))).join("")}$`);

const COMPILED: Compiled[] = (table as { contracts: Row[] }).contracts.flatMap((row) =>
  row.paths.map((glob): Compiled => ({ row, rx: compile(glob), rank: [glob.split("*").length - 1, -glob.length] })),
);

/** A logical document path: no leading slash, no `docs/` prefix, no `.gz`. */
export const normalPath = (rel: string): string => rel.replace(/^\/+/, "").replace(/\.gz$/, "").replace(/^docs\//, "");

/** The contract covering a document path; the most specific pattern wins (`theaters/index.json` over `theaters/*.json`). */
export function contractFor(rel: string): Row | null {
  const p = normalPath(rel);
  let best: Compiled | null = null;
  for (const c of COMPILED) {
    if (c.rx.test(p) && (best === null || c.rank[0] < best.rank[0] || (c.rank[0] === best.rank[0] && c.rank[1] < best.rank[1]))) best = c;
  }
  return best ? best.row : null;
}

export type Verdict = { ok: true; major: number | null } | { ok: false; reason: string };

/** `"ohmega.daily/2"` -> `{ id, major }`; null for anything else. */
export function parseStamp(stamp: unknown): { id: string; major: number } | null {
  const m = typeof stamp === "string" ? /^(ohmega\.[\w.-]+)\/(\d+)$/.exec(stamp) : null;
  return m ? { id: m[1], major: Number(m[2]) } : null;
}

/** Judge a fetched document against its family's contract. Only objects carry a stamp; an array, a path with no contract and a document with no `schema`
 *  (published before stamps existed: a v1) pass when v1 is still accepted. A different family's stamp or an unknown major does not. */
export function checkDoc(rel: string, doc: unknown): Verdict {
  const row = contractFor(rel);
  if (row === null || typeof doc !== "object" || doc === null || Array.isArray(doc)) return { ok: true, major: null };
  const raw = (doc as { schema?: unknown }).schema;
  if (raw === undefined) return row.accepts.includes(1) ? { ok: true, major: 1 } : { ok: false, reason: `${rel}: unstamped document, but ${row.schema} is past v1` };
  const got = parseStamp(raw);
  if (got === null) return { ok: false, reason: `${rel}: unreadable schema ${JSON.stringify(raw)}` };
  if (got.id !== row.schema) return { ok: false, reason: `${rel}: schema ${got.id}, this path is ${row.schema}` };
  if (!row.accepts.includes(got.major)) return { ok: false, reason: `${rel}: ${got.id}/${got.major} is newer or older than this site reads (${row.accepts.map((v) => `/${v}`).join(", ")})` };
  return { ok: true, major: got.major };
}

// What was refused since this server instance started: lets a page say "update pending" instead of pretending nothing is published.
const pending = new Map<string, string>();

/** Refuse a document: remember why (once per path; logged once) and return null for the caller to return. */
export function refuse(rel: string, reason: string): null {
  const key = normalPath(rel);
  if (!pending.has(key)) {
    pending.set(key, reason);
    console.warn(`[contract] update pending: ${reason}`);
  }
  return null;
}

/** The reasons documents were refused (empty when every document read so far matched a major this build understands). */
export const updatePending = (): string[] => Array.from(pending.values());

/** Gate a fetched document: the document itself, or null (and a remembered reason) when its major is unknown. */
export function gate<T>(rel: string, doc: T): T | null {
  const v = checkDoc(rel, doc);
  return v.ok ? doc : refuse(rel, v.reason);
}
