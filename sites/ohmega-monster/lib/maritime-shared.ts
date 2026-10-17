// Maritime behaviour events, as data: the `maritime_events` row (backend `maritime/`, migration 013) and the pure helpers the /intel/maritime page,
// the /live "Shadow fleet" layer and the vessel place pages share. No I/O and no node imports, so a client component may import this file.
// The server-side reads live in lib/maritime.ts.
//
// Every event is Ohmega's own derivation from the AIS it hears (provenance `ohmega_derived`): a pattern seen, never a finding of intent.

export type MaritimeKind = "ais_gap" | "sts" | "identity" | "sanctioned" | "loiter";
export type MaritimeState = "ongoing" | "ended" | "unresolved";

/** One evidence point: [unix seconds, lat, lon, speed in knots (-1 unknown), note]. */
export type EvidencePoint = [number, number, number, number, string];

export type MaritimeEvent = {
  id: string;
  kind: MaritimeKind;
  mmsi: number;
  mmsi2: number | null;
  name: string;
  name2: string;
  imo: string;
  flag: string; // ISO2, from the MMSI's country prefix
  flag2: string;
  ship_class: string;
  started_at: string;
  ended_at: string | null; // null: still going
  last_seen: string | null;
  state: MaritimeState;
  active: boolean;
  lat: number | null;
  lon: number | null;
  area: string; // the named area it lies in; "" = open ocean outside every named area
  countries: string[];
  confidence: number; // 0..1
  rationale: string;
  summary: string;
  detail: Record<string, unknown>;
  evidence: EvidencePoint[];
  provenance: "ohmega_derived";
  updated_at: string;
};

export const KIND_ORDER: MaritimeKind[] = ["sanctioned", "ais_gap", "sts", "identity", "loiter"];

export const KIND_LABEL: Record<MaritimeKind, string> = {
  ais_gap: "AIS gap",
  sts: "Ship-to-ship",
  identity: "Identity change",
  sanctioned: "Sanctioned vessel seen",
  loiter: "Loitering",
};

/** What each kind means, and what it does not (shown in the key and the API note). */
export const KIND_MEANING: Record<MaritimeKind, string> = {
  ais_gap: "went silent for hours where other ships kept being heard; receiver loss, ports and our own outages are screened out",
  sts: "two ships, at least one a tanker, alongside at near-zero speed for hours in open water; ports and waiting crowds are screened out",
  identity: "a rename, an alternating name, a changed or invalid IMO number, or one IMO under several flag states",
  sanctioned: "matches a sanctions designation by IMO number, or by exact name plus flag state",
  loiter: "a long slow dwell inside a chokepoint or an undersea cable / pipeline corridor (cable zones are approximate proxies)",
};

/** Map colours per kind (map data colours are map-local, like the other /live layers). The words carry the meaning; colour only echoes it. */
export const KIND_COLOR: Record<MaritimeKind, string> = {
  sanctioned: "#c2410c",
  ais_gap: "#7c3aed",
  sts: "#0e7490",
  identity: "#a16207",
  loiter: "#be185d",
};

export const SHADOW_COLOR = "#7c3aed";

/** The /live layer shows events still going or ended within this many days (a reader budget: older ones stay on /intel/maritime). */
export const SHADOW_DAYS = 7;

/** Events for the /live "Shadow fleet" layer: still going, or ended within SHADOW_DAYS, with a position. */
export function shadowEvents(rows: MaritimeEvent[], nowMs: number): MaritimeEvent[] {
  const cut = nowMs - SHADOW_DAYS * 86400_000;
  return rows.filter((e) => e.lat !== null && e.lon !== null && (e.ended_at === null || Date.parse(e.ended_at) >= cut));
}

export const kindLabel = (k: string): string => KIND_LABEL[k as MaritimeKind] ?? k;

/** "high" / "medium" / "low" for a 0..1 confidence (words for a reader; the number is shown beside it). */
export const confidenceWord = (c: number): string => (c >= 0.7 ? "high" : c >= 0.4 ? "medium" : "low");

export const asKind = (v: unknown): MaritimeKind | null => (typeof v === "string" && (KIND_ORDER as string[]).includes(v) ? (v as MaritimeKind) : null);

/** The vessel(s) of an event as one label: "NORDIC STAR" or "NORDIC STAR + SEA FALCON". */
export const vesselLabel = (e: Pick<MaritimeEvent, "name" | "name2" | "mmsi" | "mmsi2">): string => {
  const a = e.name || `MMSI ${e.mmsi}`;
  return e.mmsi2 ? `${a} + ${e.name2 || `MMSI ${e.mmsi2}`}` : a;
};

const MS = 3600_000;
/** "3.2 h", "2.1 d": a duration between two ISO instants (to `now` when still going). */
export function durationText(startIso: string, endIso: string | null, nowMs: number): string {
  const a = Date.parse(startIso);
  const b = endIso ? Date.parse(endIso) : nowMs;
  if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return "";
  const h = (b - a) / MS;
  return h < 48 ? `${h.toFixed(1)} h` : `${(h / 24).toFixed(1)} d`;
}

export const pct = (c: number): string => `${Math.round(c * 100)}%`;

/** A coordinate pair as text: "26.41 N 56.40 E". */
export function latLon(lat: number | null, lon: number | null): string {
  if (lat === null || lon === null) return "";
  return `${Math.abs(lat).toFixed(2)} ${lat >= 0 ? "N" : "S"} ${Math.abs(lon).toFixed(2)} ${lon >= 0 ? "E" : "W"}`;
}

/** One evidence point as a plain line: "2026-10-17 08:00 UTC · 11.2 kn · 26.41 N 56.40 E · last heard". */
export function evidenceLine(p: EvidencePoint): string {
  const [ts, lat, lon, kn, note] = p;
  const when = new Date(ts * 1000).toISOString().slice(0, 16).replace("T", " ");
  return [`${when} UTC`, kn >= 0 ? `${kn.toFixed(1)} kn` : "", latLon(lat, lon), note].filter(Boolean).join(" · ");
}

/** The track of an event as [lon, lat] pairs, oldest first (drawn as a thin line on /live; needs two points). */
export function trackOf(e: Pick<MaritimeEvent, "evidence">): [number, number][] {
  return e.evidence.filter((p) => Number.isFinite(p[1]) && Number.isFinite(p[2])).map((p) => [p[2], p[1]] as [number, number]);
}

export type Count = { key: string; n: number };

/** Tally by a key, most first (ties by key); events with no key are left out. */
export function tally(rows: MaritimeEvent[], key: (e: MaritimeEvent) => string | string[]): Count[] {
  const m = new Map<string, number>();
  for (const e of rows) {
    const k = key(e);
    for (const x of Array.isArray(k) ? k : [k]) if (x) m.set(x, (m.get(x) ?? 0) + 1);
  }
  return Array.from(m.entries()).map(([k, n]) => ({ key: k, n })).sort((a, b) => b.n - a.n || a.key.localeCompare(b.key));
}

/** Flag states of an event (both vessels of a pair), without blanks. */
export const flagsOf = (e: MaritimeEvent): string[] => Array.from(new Set([e.flag, e.flag2].filter(Boolean)));

/** The IMO number of a vessel place (`og-xx-vessel-imo9074729`, or an `imo` attribute): "" when it has none. */
export function imoOf(asset: { id: string; attrs: Record<string, unknown> }): string {
  const fromId = /-imo(\d{7})$/.exec(asset.id)?.[1];
  const attr = String(asset.attrs.imo ?? "");
  return fromId ?? (/^\d{7}$/.test(attr) ? attr : "");
}

/** The compact fields a /live popup and the vessel page need, beyond the row itself. */
export function identityLine(e: MaritimeEvent): string {
  const bits = [e.name || `MMSI ${e.mmsi}`, e.imo ? `IMO ${e.imo}` : "", `MMSI ${e.mmsi}`, e.flag ? `flag ${e.flag}` : "", e.ship_class];
  return bits.filter(Boolean).join(" · ");
}
