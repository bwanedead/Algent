import { dbRows } from "@/lib/store";

import { asStatus, asType, type GeoAsset, type GeoEvent, type GeoLogRow, type GridDoc } from "./geoledger-shared";

export * from "./geoledger-shared";

// Server reads of the geospatial asset ledger (migration 009: `geo_assets`, `geo_asset_events`, anon read-only).
// Everything degrades to "nothing": no database, an empty table or a failed request yields empty lists, and the map
// simply draws no infrastructure layer. Server-only: client components import lib/geoledger-shared.ts instead.

const ASSET_COLS = "id,name,aliases,type,country,lat,lon,loc_precision,capacity_mw,fuel,attrs,source,licence,provenance,status,status_on,status_by,events,merged_into";
const EVENT_COLS = "id,asset_id,occurred_on,occurred_at,status,claimant,confidence,sources,provenance,observed_at,note,via";
const ID = /^[\w.-]+$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Most places a theater map is sent: the ones with a status first, then the largest of the rest. */
export const MAP_EVENT_ASSETS = 400;
export const MAP_STATIC_ASSETS = 500;

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

type Raw = Record<string, unknown>;

function toAsset(r: Raw): GeoAsset | null {
  const id = str(r.id);
  if (!ID.test(id)) return null;
  const prec = str(r.loc_precision);
  return {
    id,
    name: str(r.name),
    aliases: strs(r.aliases),
    type: asType(r.type),
    country: str(r.country),
    lat: num(r.lat),
    lon: num(r.lon),
    loc_precision: prec === "exact" || prec === "city_level" || prec === "unplaced" ? prec : "approximate",
    capacity_mw: num(r.capacity_mw),
    fuel: str(r.fuel),
    attrs: typeof r.attrs === "object" && r.attrs !== null && !Array.isArray(r.attrs) ? (r.attrs as Record<string, unknown>) : {},
    source: str(r.source),
    licence: str(r.licence),
    provenance: r.provenance === "ohmega_derived" ? "ohmega_derived" : "aggregated",
    status: asStatus(r.status),
    status_on: DAY.test(str(r.status_on)) ? str(r.status_on) : null,
    status_by: str(r.status_by) || null,
    events: Math.max(0, Math.floor(num(r.events) ?? 0)),
    merged_into: str(r.merged_into) || null,
  };
}

function toEvent(r: Raw): GeoEvent | null {
  const status = asStatus(r.status);
  if (!status || !ID.test(str(r.id)) || !DAY.test(str(r.occurred_on))) return null;
  const conf = str(r.confidence);
  return {
    id: str(r.id),
    asset_id: str(r.asset_id),
    occurred_on: str(r.occurred_on),
    occurred_at: str(r.occurred_at),
    status,
    claimant: str(r.claimant),
    confidence: conf === "low" || conf === "high" ? conf : "medium",
    sources: strs(r.sources).filter((u) => /^https?:\/\//.test(u)),
    provenance: r.provenance === "ohmega_derived" ? "ohmega_derived" : "aggregated",
    observed_at: str(r.observed_at),
    note: str(r.note),
    via: str(r.via),
  };
}

export type AssetFilter = {
  bbox?: [number, number, number, number];
  type?: string;
  country?: string;
  status?: string;
  /** true: only places with at least one event on record. */
  hasEvents?: boolean;
  limit?: number;
};

function filterQuery(f: AssetFilter): string {
  const q: string[] = [`select=${ASSET_COLS}`, "merged_into=is.null"];            // a merged duplicate is its target now
  if (f.bbox) {
    const [w, s, e, n] = f.bbox;
    q.push(`lat=gte.${s}`, `lat=lte.${n}`, `lon=gte.${w}`, `lon=lte.${e}`);
  }
  if (f.type) q.push(`type=eq.${encodeURIComponent(f.type)}`);
  if (f.country) q.push(`country=eq.${encodeURIComponent(f.country)}`);
  if (f.status) q.push(`status=eq.${encodeURIComponent(f.status)}`);
  if (f.hasEvents === true) q.push("events=gt.0");
  if (f.hasEvents === false) q.push("events=eq.0");
  q.push("order=events.desc,capacity_mw.desc.nullslast,id.asc", `limit=${Math.min(Math.max(f.limit ?? 200, 1), 2000)}`);
  return q.join("&");
}

/** Places matching a filter (an API read). [] without a database. */
export async function queryAssets(f: AssetFilter): Promise<GeoAsset[]> {
  return (await dbRows<Raw>("geo_assets", filterQuery(f))).map(toAsset).filter((a): a is GeoAsset => a !== null);
}

export async function getAsset(id: string): Promise<GeoAsset | null> {
  if (!ID.test(id)) return null;
  const rows = await dbRows<Raw>("geo_assets", `select=${ASSET_COLS}&id=eq.${encodeURIComponent(id)}&limit=1`);
  return rows.length > 0 ? toAsset(rows[0]) : null;
}

/** Every event of one place, oldest first. */
export async function assetHistory(id: string): Promise<GeoEvent[]> {
  if (!ID.test(id)) return [];
  const rows = await dbRows<Raw>("geo_asset_events", `select=${EVENT_COLS}&asset_id=eq.${encodeURIComponent(id)}&order=occurred_on.asc,observed_at.asc&limit=500`);
  return rows.map(toEvent).filter((e): e is GeoEvent => e !== null);
}

/**
 * The grid-impact rollup of one country (table `geo_grid`, migration 010, written by the backend), or null: no database, no row,
 * or a row that is not the document we know. The document is trusted only in shape (windows present), never in kind.
 */
export async function getGrid(iso: string): Promise<GridDoc | null> {
  const code = iso.toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return null;
  const rows = await dbRows<Raw>("geo_grid", `select=iso,as_of,doc&iso=eq.${code}&limit=1`);
  const doc = rows[0]?.doc as GridDoc | undefined;
  if (!doc || typeof doc !== "object" || !doc.windows || !doc.windows["30"] || !doc.windows["7"] || !doc.installed) return null;
  return { ...doc, iso: code, provenance: "ohmega_derived" };
}

/** The country most of these places are in ("" when none): where a theater map's struck power plants are. */
export function dominantCountry(assets: GeoAsset[]): string {
  const n = new Map<string, number>();
  for (const a of assets) if (a.type === "power_plant" && a.country) n.set(a.country, (n.get(a.country) ?? 0) + 1);
  return [...n.entries()].sort((x, y) => y[1] - x[1])[0]?.[0] ?? "";
}

/** Events of the given places in a window, newest first. */
export async function eventsFor(ids: string[], since: string, until: string, limit = 300): Promise<GeoEvent[]> {
  const safe = ids.filter((i) => ID.test(i)).slice(0, 400);
  if (safe.length === 0 || !DAY.test(since) || !DAY.test(until)) return [];
  const rows = await dbRows<Raw>(
    "geo_asset_events",
    `select=${EVENT_COLS}&asset_id=in.(${safe.join(",")})&occurred_on=gte.${since}&occurred_on=lte.${until}&order=occurred_on.desc,observed_at.desc&limit=${limit}`,
  );
  return rows.map(toEvent).filter((e): e is GeoEvent => e !== null);
}

export type TheaterInfra = { assets: GeoAsset[]; log: GeoLogRow[]; /** Grid-impact rollup of the country the frame's struck power plants are mostly in. */ grid: GridDoc | null };

const addDays = (day: string, n: number): string => new Date(Date.parse(`${day}T00:00:00Z`) + n * 86400000).toISOString().slice(0, 10);

/**
 * What a theater map and its "Strike & status log" show: the places in the map's frame that have a status on record,
 * plus the largest places without one, and the week's events (ending on the report's day) at those places.
 * Empty when there is no database or no frame.
 */
export async function theaterInfra(bbox: number[] | undefined, day: string): Promise<TheaterInfra> {
  if (!bbox || bbox.length !== 4 || !DAY.test(day) || !bbox.every((x) => Number.isFinite(x))) return { assets: [], log: [], grid: null };
  const frame = bbox as [number, number, number, number];
  const [hit, rest] = await Promise.all([
    queryAssets({ bbox: frame, hasEvents: true, limit: MAP_EVENT_ASSETS }),
    queryAssets({ bbox: frame, hasEvents: false, limit: MAP_STATIC_ASSETS }),
  ]);
  const assets = [...hit, ...rest];
  const byId = new Map(assets.map((a) => [a.id, a] as const));
  const events = await eventsFor(hit.map((a) => a.id), addDays(day, -6), day);
  const log: GeoLogRow[] = events.flatMap((e) => {
    const a = byId.get(e.asset_id);
    return a ? [{ ...e, name: a.name, type: a.type, country: a.country }] : [];
  });
  return { assets, log, grid: await getGrid(dominantCountry(hit)) };
}
