import { tableDoc, TTL } from "@/lib/store";

import { asKind, KIND_ORDER, type EvidencePoint, type MaritimeEvent } from "./maritime-shared";

export * from "./maritime-shared";

// Server reads of the maritime behaviour products: published files (backend `maritime/publish.py`), no database. Everything degrades to "nothing": no
// published file yields an empty list and the layer / page simply show none (a failing bucket throws, lib/store.ts). Server-only: client components
// import lib/maritime-shared.ts instead.

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

type Raw = Record<string, unknown>;

function points(v: unknown): EvidencePoint[] {
  if (!Array.isArray(v)) return [];
  const out: EvidencePoint[] = [];
  for (const p of v) {
    if (Array.isArray(p) && typeof p[0] === "number" && typeof p[1] === "number" && typeof p[2] === "number") {
      out.push([p[0], p[1], p[2], typeof p[3] === "number" ? p[3] : -1, typeof p[4] === "string" ? p[4] : ""]);
    }
  }
  return out;
}

function toEvent(r: Raw): MaritimeEvent | null {
  const kind = asKind(r.kind);
  const mmsi = num(r.mmsi);
  if (!kind || mmsi === null || r.provenance !== "ohmega_derived" || !str(r.id) || !str(r.started_at)) return null;
  const state = r.state === "ended" || r.state === "unresolved" ? r.state : "ongoing";
  return {
    id: str(r.id),
    kind,
    mmsi,
    mmsi2: num(r.mmsi2),
    name: str(r.name),
    name2: str(r.name2),
    imo: str(r.imo),
    flag: str(r.flag),
    flag2: str(r.flag2),
    ship_class: str(r.ship_class),
    started_at: str(r.started_at),
    ended_at: str(r.ended_at) || null,
    last_seen: str(r.last_seen) || null,
    state,
    active: r.active === true,
    lat: num(r.lat),
    lon: num(r.lon),
    area: str(r.area),
    countries: strs(r.countries),
    confidence: Math.min(1, Math.max(0, num(r.confidence) ?? 0)),
    rationale: str(r.rationale),
    summary: str(r.summary),
    detail: typeof r.detail === "object" && r.detail !== null && !Array.isArray(r.detail) ? (r.detail as Record<string, unknown>) : {},
    evidence: points(r.evidence),
    provenance: "ohmega_derived",
    updated_at: str(r.updated_at),
  };
}

async function eventsOf(rel: string, revalidate: number): Promise<MaritimeEvent[]> {
  const doc = await tableDoc<{ events?: Raw[] }>(rel, revalidate);
  return (doc?.events ?? []).map(toEvent).filter((e): e is MaritimeEvent => e !== null);
}

/** The behaviour events of the last 30 days (those still going first, then newest start); [] when none are published. The analysis page
 *  reads this (`maritime/recent.json`, evidence trimmed to a short track). */
export async function maritimeEvents(limit = 1500): Promise<MaritimeEvent[]> {
  return (await eventsOf("maritime/recent.json", TTL.maritime)).slice(0, Math.min(Math.max(limit, 1), 3000));
}

/** What is going on NOW: still-going events and those ended in the last two days, evidence cut to the last few points
 *  (`maritime/live.json`, a fraction of the size of the full list). The /live map layer and the home strip read this. */
export async function maritimeLive(limit = 400): Promise<MaritimeEvent[]> {
  return (await eventsOf("maritime/live.json", TTL.live)).slice(0, Math.min(Math.max(limit, 1), 400));
}

/** Real totals for the page lead: every event kept (30 days), those still open, and per kind (`maritime/counts.json`, computed by the backend
 *  over all events, not over a capped list). */
export type MaritimeCounts = { total: number; ongoing: number; byKind: Record<string, number> };

export async function maritimeCounts(): Promise<MaritimeCounts | null> {
  const doc = await tableDoc<Partial<MaritimeCounts>>("maritime/counts.json", TTL.maritime);
  if (!doc || typeof doc.total !== "number" || typeof doc.ongoing !== "number") return null;
  const by = doc.byKind ?? {};
  return { total: doc.total, ongoing: doc.ongoing, byKind: Object.fromEntries(KIND_ORDER.map((k) => [k, by[k] ?? 0])) };
}

/** Events about one vessel, by IMO number, newest start first (`maritime/vessel/<imo>.json`; only vessels with events have a file).
 *  The partner ship of a pair is not indexed by MMSI any more: the IMO file of either ship carries the event. */
export async function maritimeForVessel(ids: { imo?: string; mmsi?: number }, limit = 100): Promise<MaritimeEvent[]> {
  if (!ids.imo || !/^\d{7}$/.test(ids.imo)) return [];
  const rows = await eventsOf(`maritime/vessel/${ids.imo}.json`, TTL.tables);
  return rows.sort((a, b) => b.started_at.localeCompare(a.started_at)).slice(0, limit);
}
