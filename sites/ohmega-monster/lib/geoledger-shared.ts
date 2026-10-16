// Client-safe types and pure helpers of the geospatial asset ledger (backend `geoledger/`, migration 009,
// docs/architecture/geoledger.md). No server imports: client components (the theater map) import from here; the
// database reads live in lib/geoledger.ts.
//
// A status is always somebody's word. The map's colours keep a party's CLAIM (lighter orange) apart from damage
// REPORTED by the owner or media (red) and damage CONFIRMED by an operator, neutral authority or imagery (deep red).

export type AssetType =
  | "power_plant" | "substation" | "refinery" | "fuel_depot" | "port" | "bridge" | "airbase" | "military_base"
  | "dam" | "rail_hub" | "vessel" | "entity" | "other";

export type AssetStatus =
  | "operational" | "claimed_struck" | "reported_damaged" | "confirmed_damaged" | "destroyed" | "restored"
  | "unknown" | "seized" | "designated";

export type GeoAsset = {
  id: string;
  name: string;
  aliases: string[];
  type: AssetType;
  country: string;
  lat: number | null;
  lon: number | null;
  loc_precision: "exact" | "approximate" | "city_level" | "unplaced";
  capacity_mw: number | null;
  fuel: string;
  attrs: Record<string, unknown>;
  source: string;
  licence: string;
  provenance: "aggregated" | "ohmega_derived";
  /** Latest status (derived by the publisher from the events); null = nothing on record about it. */
  status: AssetStatus | null;
  status_on: string | null;
  status_by: string | null;
  events: number;
  /** Set when `newsroom geo merge` joined this spelling of a place into another; readers show the target. */
  merged_into: string | null;
};

export type GeoEvent = {
  id: string;
  asset_id: string;
  occurred_on: string;
  occurred_at: string;
  status: AssetStatus;
  claimant: string;
  confidence: "low" | "medium" | "high";
  sources: string[];
  provenance: "aggregated" | "ohmega_derived";
  observed_at: string;
  note: string;
  via: string;
};

/** An event with the little of its asset a log line needs. */
export type GeoLogRow = GeoEvent & { name: string; type: AssetType; country: string };

export const STATUS_LABEL: Record<AssetStatus, string> = {
  operational: "Operating",
  claimed_struck: "Claimed struck",
  reported_damaged: "Damage reported",
  confirmed_damaged: "Damage confirmed",
  destroyed: "Destroyed",
  restored: "Restored",
  unknown: "Status unknown",
  seized: "Seized",
  designated: "Designated",
};

/** What each status means to a reader, in the key: who is saying it, how firmly. */
export const STATUS_MEANING: Record<AssetStatus, string> = {
  operational: "stated to be running",
  claimed_struck: "a party says it hit it; nobody else has said so",
  reported_damaged: "damage reported by the owner, authorities or media",
  confirmed_damaged: "damage confirmed by the operator, a neutral authority or imagery",
  destroyed: "described as destroyed",
  restored: "back in operation",
  unknown: "named, outcome not stated",
  seized: "taken by a party",
  designated: "put on a list by a party",
};

export const TYPE_LABEL: Record<AssetType, string> = {
  power_plant: "Power plant", substation: "Substation", refinery: "Refinery", fuel_depot: "Fuel depot", port: "Port",
  bridge: "Bridge", airbase: "Airbase", military_base: "Military base", dam: "Dam", rail_hub: "Rail hub",
  vessel: "Vessel", entity: "Entity", other: "Site",
};

/** One letter on the map per type (readable on a small mark, no icon font to load). */
export const TYPE_GLYPH: Record<AssetType, string> = {
  power_plant: "P", substation: "S", refinery: "R", fuel_depot: "F", port: "H", bridge: "B", airbase: "A",
  military_base: "M", dam: "D", rail_hub: "T", vessel: "V", entity: "E", other: "·",
};

/** Colour families: warm = hit (lighter when only claimed), green = restored, grey = nothing on record or running. */
export const TONE = {
  claimed: "#e08a3c",
  reported: "#d6451a",
  confirmed: "#a31621",
  restored: "#2f8f5b",
  taken: "#3b6ea8",
  neutral: "#6b7280",
} as const;

export function statusTone(s: AssetStatus | null): string {
  switch (s) {
    case "claimed_struck": return TONE.claimed;
    case "reported_damaged": return TONE.reported;
    case "confirmed_damaged":
    case "destroyed": return TONE.confirmed;
    case "restored": return TONE.restored;
    case "seized":
    case "designated": return TONE.taken;
    default: return TONE.neutral;
  }
}

/** A status that describes something that happened (and so grows stale), as opposed to plain existence. */
export const isDynamic = (s: AssetStatus | null): boolean => s !== null && s !== "operational" && s !== "unknown";

/** A dynamic status fades to this opacity as it ages; a place that merely exists never fades. */
export const FADE_DAYS = 30;
export const FADE_FLOOR = 0.35;

export function freshness(status: AssetStatus | null, on: string | null, now: Date = new Date()): number {
  if (!isDynamic(status) || !on) return 1;
  const age = (now.getTime() - Date.parse(`${on}T12:00:00Z`)) / 86400000;
  if (!Number.isFinite(age) || age <= 0) return 1;
  return Math.max(FADE_FLOOR, 1 - (1 - FADE_FLOOR) * Math.min(1, age / FADE_DAYS));
}

export function capacityLabel(a: Pick<GeoAsset, "capacity_mw" | "fuel">): string {
  const mw = a.capacity_mw;
  const cap = mw === null ? "" : mw >= 1000 ? `${(mw / 1000).toFixed(mw >= 10000 ? 0 : 1)} GW` : `${Math.round(mw)} MW`;
  return [cap, a.fuel.toLowerCase()].filter(Boolean).join(" ");
}

/** "2026-10-03 · Claimed struck · Russian MoD" */
export const historyLine = (e: Pick<GeoEvent, "occurred_on" | "status" | "claimant" | "confidence">): string =>
  `${e.occurred_on} · ${STATUS_LABEL[e.status] ?? e.status} · ${e.claimant}${e.confidence === "low" ? " (low confidence)" : ""}`;

const STATUSES = Object.keys(STATUS_LABEL) as AssetStatus[];
const TYPES = Object.keys(TYPE_LABEL) as AssetType[];
export const asStatus = (v: unknown): AssetStatus | null => (typeof v === "string" && (STATUSES as string[]).includes(v) ? (v as AssetStatus) : null);
export const asType = (v: unknown): AssetType => (typeof v === "string" && (TYPES as string[]).includes(v) ? (v as AssetType) : "other");
export const ASSET_TYPES: readonly AssetType[] = TYPES;
export const ASSET_STATUSES: readonly AssetStatus[] = STATUSES;

// ---- Grid impact (backend `geoledger/grid.py`, table `geo_grid`): Ohmega's own rollup of how much of a country's installed
// generating capacity has been CLAIMED struck, REPORTED damaged, CONFIRMED damaged or destroyed, and RESTORED. Claimed and
// confirmed overlap and are never added; capacity is nameplate, not output. Provenance: ohmega_derived.

export const GRID_FUELS = ["thermal", "hydro", "nuclear", "renewables", "other"] as const;
export type GridFuel = (typeof GRID_FUELS)[number];
export const FUEL_LABEL: Record<GridFuel, string> = { thermal: "Thermal & CHP", hydro: "Hydro", nuclear: "Nuclear", renewables: "Renewables", other: "Other" };
export type GridStance = "claimed" | "reported" | "confirmed" | "restored";
export type FuelMw = Record<GridFuel, number>;
export type GridTally = { plants: number; mw: number; share: number | null; no_capacity: number; by_fuel: FuelMw };
export type GridAffected = {
  id: string; name: string; fuel: string; fuel_class: GridFuel; mw: number | null; stances: GridStance[]; bucket: GridStance | "";
  latest_status: string; latest_on: string; claimants: string[];
};
export type GridWindow = Record<GridStance, GridTally> & {
  days: number; buckets: Record<GridStance, FuelMw>; plants_affected: number; affected: GridAffected[];
};
export type GridDoc = {
  iso: string; as_of: string; provenance: "ohmega_derived"; method: string; line: string; last_event_on: string; caveats: string[];
  installed: { mw: number; by_fuel: FuelMw; plants: number; plants_with_capacity: number };
  windows: Record<string, GridWindow>;
  series: { day: string; claimed_mw: number; confirmed_mw: number; claimed_share: number | null; confirmed_share: number | null }[];
};

export const mwLabel = (mw: number): string => (mw >= 1000 ? `${(mw / 1000).toFixed(mw >= 10000 ? 0 : 1)} GW` : `${Math.round(mw)} MW`);
export const pctLabel = (share: number | null): string => {
  if (share === null) return "n/a";
  const p = share * 100;
  return p > 0 && p < 1 ? "<1%" : p >= 10 ? `${Math.round(p)}%` : `${p.toFixed(1).replace(/\.0$/, "")}%`;
};

/** Whole days between a YYYY-MM-DD and `now` (never negative); null when the day is missing. */
export function ageDays(day: string, now: Date = new Date()): number | null {
  const t = Date.parse(`${day}T12:00:00Z`);
  return Number.isFinite(t) ? Math.max(0, Math.floor((now.getTime() - t) / 86400000)) : null;
}
