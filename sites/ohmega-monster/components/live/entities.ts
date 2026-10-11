// The moving things on /live: ships and aircraft decoded from the compact snapshot rows, their classes and colours, the
// filters the layer panel offers, and dead reckoning (where an object is NOW, from its last report). Pure and client-safe:
// imports only types from lib/live-shared.

import type { AircraftDoc, VesselsDoc } from "@/lib/live-shared";

export type Kind = "ship" | "air";

export type Entity = {
  kind: Kind;
  id: number;
  lon: number;
  lat: number;
  hdg: number; // degrees, -1 unknown
  spd: number; // knots, -1 unknown
  cls: number;
  ts: number; // last report, unix seconds
  name: string; // ship name or aircraft callsign
  dest: string;
  flag: string; // ISO-2 (ships)
  nf: number; // ships: 1 military, 2 dark, 4 tanker stopped in a strait
  type: string; // aircraft type code
  alt: number; // aircraft feet, -1 unknown, 0 on the ground
};

export const MOVING_KN = 0.5;

export const SHIP_CLASSES = [
  { key: "tanker", label: "Tankers", color: "#e3a13b" },
  { key: "cargo", label: "Cargo", color: "#3fb0a8" },
  { key: "passenger", label: "Passenger", color: "#5aa9e6" },
  { key: "fishing", label: "Fishing", color: "#7cc36b" },
  { key: "military", label: "Military and law enforcement", color: "#e06666" },
  { key: "other", label: "Other", color: "#9aa5ab" },
] as const;

export const AIR_KINDS = [
  { key: "military", label: "Military", color: "#8b6fd6" },
  { key: "civil", label: "Civil", color: "#8fa3b5" },
] as const;

export const AIR_ROLE = ["Civil", "Military", "Tanker", "Surveillance", "Airlift", "Fighter or bomber"];
export const SHIP_NOTABLE = [
  [1, "military or law enforcement"],
  [2, "gone dark: was moving, then stopped broadcasting"],
  [4, "tanker stopped inside a chokepoint lane"],
] as const;

const num = (v: string | number | undefined, d = -1) => (typeof v === "number" ? v : d);
const str = (v: string | number | undefined) => (typeof v === "string" ? v : "");

export function decodeVessels(doc: VesselsDoc | null): Entity[] {
  return (doc?.rows ?? []).map((r) => ({
    kind: "ship" as const, id: num(r[0], 0), lon: num(r[1], 0), lat: num(r[2], 0), hdg: num(r[3]), spd: num(r[4]), cls: num(r[5], 5), ts: num(r[6], 0),
    name: str(r[7]), dest: str(r[8]), flag: str(r[9]), nf: num(r[10], 0), type: "", alt: -1,
  }));
}

export function decodeAircraft(doc: AircraftDoc | null): Entity[] {
  return (doc?.rows ?? []).map((r) => ({
    kind: "air" as const, id: num(r[0], 0), lon: num(r[1], 0), lat: num(r[2], 0), hdg: num(r[3]), spd: num(r[4]), cls: num(r[5], 0), ts: num(r[6], 0),
    name: str(r[7]), dest: "", flag: "", nf: 0, type: str(r[8]), alt: num(r[9]),
  }));
}

export const colorOf = (e: Entity): string => (e.kind === "ship" ? SHIP_CLASSES[e.cls]?.color ?? "#9aa5ab" : e.cls === 0 ? AIR_KINDS[1].color : AIR_KINDS[0].color);
export const iconOf = (e: Entity): string => (e.kind === "ship" ? `lt-ship-${Math.min(e.cls, 5)}` : e.cls === 0 ? "lt-air-civil" : "lt-air-mil");
export const isNotable = (e: Entity): boolean => (e.kind === "ship" ? e.nf > 0 : e.cls > 0);

// ---- filters --------------------------------------------------------------------------------------------------------

export type EntityFilter = {
  /** Sublayers switched off: "tanker", "cargo", ... for ships; "military" / "civil" for aircraft. */
  off: Set<string>;
  flag: string; // ISO-2 or ""
  speed: "all" | "moving" | "stopped";
  notable: boolean;
  q: string; // name, MMSI or callsign fragment
};

export const NO_FILTER: EntityFilter = { off: new Set(), flag: "", speed: "all", notable: false, q: "" };

export function passes(e: Entity, f: EntityFilter): boolean {
  const sub = e.kind === "ship" ? SHIP_CLASSES[e.cls]?.key ?? "other" : e.cls === 0 ? "civil" : "military";
  if (f.off.has(sub)) return false;
  if (f.flag && e.flag !== f.flag) return false;
  if (f.speed !== "all" && e.spd >= 0) {
    const moving = e.kind === "air" ? e.alt !== 0 : e.spd >= MOVING_KN;
    if ((f.speed === "moving") !== moving) return false;
  }
  if (f.notable && !isNotable(e)) return false;
  if (f.q) {
    const q = f.q.toLowerCase();
    if (!(e.name.toLowerCase().includes(q) || String(e.id).includes(q))) return false;
  }
  return true;
}

// ---- dead reckoning ------------------------------------------------------------------------------------------------------

const KN_MS = 0.514444;
const M_PER_DEG = 111320;
const MAX_REACH_S = 900; // never extrapolate further than a quarter hour from the last report

/** Where the object probably is at `nowSec`: its last report carried forward along its heading at its speed. */
export function reckon(e: Entity, nowSec: number): [number, number] {
  if (e.hdg < 0 || e.spd < (e.kind === "ship" ? MOVING_KN : 1)) return [e.lon, e.lat];
  const dt = Math.min(Math.max(nowSec - e.ts, 0), MAX_REACH_S);
  const d = e.spd * KN_MS * dt;
  const h = (e.hdg * Math.PI) / 180;
  const lat = e.lat + (d * Math.cos(h)) / M_PER_DEG;
  const lon = e.lon + (d * Math.sin(h)) / (M_PER_DEG * Math.max(0.2, Math.cos((e.lat * Math.PI) / 180)));
  return [lon, lat];
}

export function seenAgo(e: Entity, nowSec: number): string {
  const s = Math.max(0, Math.round(nowSec - e.ts));
  return s < 90 ? "seconds ago" : s < 5400 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
}

const regionName = (() => {
  try {
    const dn = new Intl.DisplayNames(["en"], { type: "region" });
    return (iso: string) => {
      try {
        return dn.of(iso) ?? iso;
      } catch {
        return iso;
      }
    };
  } catch {
    return (iso: string) => iso;
  }
})();
export { regionName };

/** The popup/detail text of an object: the title and plain lines. */
export function describe(e: Entity, nowSec: number): { kind: string; title: string; lines: string[] } {
  const spd = e.spd >= 0 ? `${e.spd.toFixed(e.spd < 10 ? 1 : 0)} kn` : "speed not broadcast";
  const hdg = e.hdg >= 0 ? `heading ${Math.round(e.hdg)}°` : "heading not broadcast";
  if (e.kind === "ship") {
    const cls = SHIP_CLASSES[e.cls]?.label ?? "Vessel";
    const lines = [`${spd}, ${hdg}`];
    if (e.dest) lines.push(`Destination: ${e.dest}`);
    if (e.flag) lines.push(`Flag: ${regionName(e.flag)}`);
    for (const [bit, text] of SHIP_NOTABLE) if (e.nf & bit) lines.push(`Notable: ${text}`);
    lines.push(`Last heard ${seenAgo(e, nowSec)}`);
    return { kind: cls, title: e.name || `Vessel ${e.id}`, lines };
  }
  const role = AIR_ROLE[e.cls] ?? "Aircraft";
  const alt = e.alt === 0 ? "on the ground" : e.alt > 0 ? `${e.alt.toLocaleString("en-GB")} ft` : "altitude not broadcast";
  return { kind: e.cls === 0 ? "Civil aircraft" : `Military aircraft, ${role.toLowerCase()}`, title: e.name || "Aircraft (no callsign)",
    lines: [`${e.type ? `Type ${e.type}, ` : ""}${alt}`, `${spd}, ${hdg}`, `Last heard ${seenAgo(e, nowSec)}`] };
}
