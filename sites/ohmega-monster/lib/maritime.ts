import { dbCount, dbRows } from "@/lib/store";

import { asKind, KIND_ORDER, type EvidencePoint, type MaritimeEvent } from "./maritime-shared";

export * from "./maritime-shared";

// Server reads of the maritime behaviour table (migration 013: `maritime_events`, anon read-only). Everything degrades to "nothing": no
// database, an empty table or a failed request yields an empty list and the layer / page simply show none. Server-only: client components
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

/** The current behaviour events (those still going first, then recently ended, strongest first); [] without a database. */
export async function maritimeEvents(limit = 1500): Promise<MaritimeEvent[]> {
  const rows = await dbRows<Raw>("maritime_events", `select=*&order=active.desc,started_at.desc&limit=${Math.min(Math.max(limit, 1), 3000)}`);
  return rows.map(toEvent).filter((e): e is MaritimeEvent => e !== null);
}

/** Real totals for the page lead: every event in the table, those still open, and per kind (a list fetch is capped, a count is not). */
export type MaritimeCounts = { total: number; ongoing: number; byKind: Record<string, number> };

export async function maritimeCounts(): Promise<MaritimeCounts | null> {
  const [total, ongoing, ...kinds] = await Promise.all([
    dbCount("maritime_events"),
    dbCount("maritime_events", "ended_at=is.null"),
    ...KIND_ORDER.map((k) => dbCount("maritime_events", `kind=eq.${k}`)),
  ]);
  if (total === null || ongoing === null) return null;
  return { total, ongoing, byKind: Object.fromEntries(KIND_ORDER.map((k, i) => [k, kinds[i] ?? 0])) };
}

/** Events about one vessel, by IMO number or MMSI, newest first. */
export async function maritimeForVessel(ids: { imo?: string; mmsi?: number }, limit = 100): Promise<MaritimeEvent[]> {
  const q: string[] = [];
  if (ids.imo && /^\d{7}$/.test(ids.imo)) q.push(`imo.eq.${ids.imo}`);
  if (ids.mmsi && Number.isInteger(ids.mmsi)) q.push(`mmsi.eq.${ids.mmsi}`, `mmsi2.eq.${ids.mmsi}`);
  if (q.length === 0) return [];
  const rows = await dbRows<Raw>("maritime_events", `select=*&or=(${q.join(",")})&order=started_at.desc&limit=${limit}`);
  return rows.map(toEvent).filter((e): e is MaritimeEvent => e !== null);
}
