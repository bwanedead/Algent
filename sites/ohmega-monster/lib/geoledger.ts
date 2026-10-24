import { tableDoc, TTL } from "@/lib/store";

import { asStatus, asType, type GeoAsset, type GeoEvent, type GeoLogRow, type GridDoc } from "./geoledger-shared";

export * from "./geoledger-shared";

// Server reads of the geospatial asset ledger, from published files (backend `geoledger/site_docs.py`), no database:
//   geo/countries.json         which countries have a file and the box their places lie in
//   geo/c/<ISO>.json           the places of one country that have a status, plus its largest places without one
//   geo/events-assets.json     every place with a status event, most events first
//   geo/a/<id>.json            one place and its whole history (only places with events have one)
//   geo/events/<YYYY-MM>.json  every event dated in a month
//   geo/grid/<ISO>.json        the grid-impact rollup of one country
// Everything degrades to "nothing": an unpublished file yields empty lists, and the map simply draws no infrastructure layer
// (a failing bucket throws, lib/store.ts). Server-only: client components import lib/geoledger-shared.ts instead.

const ID = /^[\w.-]+$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

/** Most places a theater map is sent: the ones with a status first, then the largest of the rest. */
export const MAP_EVENT_ASSETS = 400;
export const MAP_STATIC_ASSETS = 500;

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

type Raw = Record<string, unknown>;

export function toAsset(r: Raw): GeoAsset | null {
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

export function toEvent(r: Raw): GeoEvent | null {
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

type CountryIndex = { iso: string; n: number; n_events: number; bbox: [number, number, number, number] | null };
/** Most country files one bbox query will fetch (a theater frame spans one to three countries). */
const MAX_COUNTRY_FILES = 8;

const assetsOf = async (rel: string): Promise<GeoAsset[]> =>
  ((await tableDoc<{ assets?: Raw[] }>(rel, TTL.tables))?.assets ?? []).map(toAsset).filter((a): a is GeoAsset => a !== null);

const overlaps = (a: [number, number, number, number], b: [number, number, number, number]): boolean => a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];

/** The published files a filter needs: one country's, the countries whose places lie in the frame, or the places that have events. */
async function candidates(f: AssetFilter): Promise<GeoAsset[]> {
  if (f.country) return assetsOf(`geo/c/${f.country.toUpperCase()}.json`);
  if (f.bbox) {
    const frame = f.bbox;
    const index = (await tableDoc<{ countries?: CountryIndex[] }>("geo/countries.json", TTL.tables))?.countries ?? [];
    const isos = index.filter((c) => c.bbox && overlaps(c.bbox, frame)).sort((a, b) => b.n_events - a.n_events).slice(0, MAX_COUNTRY_FILES).map((c) => c.iso);
    return (await Promise.all(isos.map((iso) => assetsOf(`geo/c/${iso}.json`)))).flat();
  }
  return f.hasEvents === false ? [] : assetsOf("geo/events-assets.json");
}

/** Places matching a filter (an API read, a map frame). [] when nothing is published. A query with neither a frame nor a country only
 *  sees the places that have events (the full ledger is not published as one file). */
export async function queryAssets(f: AssetFilter): Promise<GeoAsset[]> {
  const rows = (await candidates(f)).filter((a) => {
    if (a.merged_into) return false; // a merged duplicate is its target now
    if (f.bbox) {
      const [w, s, e, n] = f.bbox;
      if (a.lat === null || a.lon === null || a.lat < s || a.lat > n || a.lon < w || a.lon > e) return false;
    }
    if (f.type && a.type !== f.type) return false;
    if (f.country && a.country !== f.country.toUpperCase()) return false;
    if (f.status && a.status !== f.status) return false;
    if (f.hasEvents === true && a.events <= 0) return false;
    if (f.hasEvents === false && a.events > 0) return false;
    return true;
  });
  rows.sort((a, b) => b.events - a.events || (b.capacity_mw ?? -1) - (a.capacity_mw ?? -1) || a.id.localeCompare(b.id));
  return rows.slice(0, Math.min(Math.max(f.limit ?? 200, 1), 2000));
}

/** One place and its history (`geo/a/<id>.json`); only places with a status event, and merged spellings, have one. */
async function placeDoc(id: string): Promise<{ asset: GeoAsset | null; events: GeoEvent[] } | null> {
  if (!ID.test(id)) return null;
  const doc = await tableDoc<{ asset?: Raw; events?: Raw[] }>(`geo/a/${id}.json`, TTL.tables);
  if (!doc?.asset) return null;
  return { asset: toAsset(doc.asset), events: (doc.events ?? []).map(toEvent).filter((e): e is GeoEvent => e !== null) };
}

export async function getAsset(id: string): Promise<GeoAsset | null> {
  return (await placeDoc(id))?.asset ?? null;
}

/** Every event of one place, oldest first. */
export async function assetHistory(id: string): Promise<GeoEvent[]> {
  const events = (await placeDoc(id))?.events ?? [];
  return events.sort((a, b) => a.occurred_on.localeCompare(b.occurred_on) || a.observed_at.localeCompare(b.observed_at)).slice(0, 500);
}

/**
 * The grid-impact rollup of one country (`geo/grid/<ISO>.json`, written by the backend), or null: not published, or a document that is
 * not the one we know. The document is trusted only in shape (windows present), never in kind.
 */
export async function getGrid(iso: string): Promise<GridDoc | null> {
  const code = iso.toUpperCase();
  if (!/^[A-Z]{2}$/.test(code)) return null;
  return gridFromDoc(code, await tableDoc<GridDoc>(`geo/grid/${code}.json`, TTL.tables));
}

/** The grid rollup of a country from a document that carries it (the published file, or a country view's copy of it): trusted only in shape. */
export function gridFromDoc(iso: string, doc: unknown): GridDoc | null {
  const g = doc as GridDoc | null;
  if (!g || typeof g !== "object" || !g.windows || !g.windows["30"] || !g.windows["7"] || !g.installed) return null;
  return { ...g, iso, provenance: "ohmega_derived" };
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
  const wanted = new Set(safe);
  const months: string[] = []; // every YYYY-MM the window touches: one small file each
  for (let d = new Date(`${since.slice(0, 7)}-01T00:00:00Z`); d.toISOString().slice(0, 7) <= until.slice(0, 7) && months.length < 24; d = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1))) {
    months.push(d.toISOString().slice(0, 7));
  }
  const files = await Promise.all(months.map((m) => tableDoc<{ events?: Raw[] }>(`geo/events/${m}.json`, TTL.tables)));
  return files
    .flatMap((doc) => doc?.events ?? [])
    .map(toEvent)
    .filter((e): e is GeoEvent => e !== null && wanted.has(e.asset_id) && e.occurred_on >= since && e.occurred_on <= until)
    .sort((a, b) => b.occurred_on.localeCompare(a.occurred_on) || b.observed_at.localeCompare(a.observed_at))
    .slice(0, limit);
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
