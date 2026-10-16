import { ASSET_STATUSES, ASSET_TYPES, assetHistory, getAsset, getGrid, queryAssets, STATUS_LABEL, type GeoAsset } from "@/lib/geoledger";

import { apiUrl } from "./ops-desk";
import { abs, badRequest, enumParam, idParam, limitParam, newest, notFound, paginate, type ApiResult, type Args } from "./util";

// Ops over the geospatial asset ledger (backend `geoledger/`, docs/architecture/geoledger.md): places that exist (power
// plants, substations, refineries, ports, bases...) and the dated, sourced statements made about their state.
// A status is somebody's word: every event names its claimant, and `claimed_struck` is never a confirmation.

const NOTE =
  "A status is somebody's word. claimed_struck = a party says it hit it; reported_damaged = damage reported by the owner, authorities or media; confirmed_damaged = confirmed by the operator, a neutral authority or imagery. " +
  "Every event names its claimant and sources. Positions are approximate unless precision says exact. Places: WRI Global Power Plant Database (CC BY 4.0) and OpenStreetMap contributors (ODbL); places and events found by Ohmega's own reading carry provenance=ohmega_derived.";

const CITE = "/geopolitics";

function bboxParam(v: string | undefined): [number, number, number, number] | undefined {
  if (!v) return undefined;
  const p = v.split(",").map((x) => Number(x.trim()));
  if (p.length !== 4 || p.some((x) => !Number.isFinite(x))) throw badRequest("bbox must be west,south,east,north in degrees");
  const [w, s, e, n] = p;
  if (s < -90 || n > 90 || w < -180 || e > 180 || s >= n || w >= e) throw badRequest("bbox must be west,south,east,north with west<east, south<north, within the world");
  return [w, s, e, n];
}

function row(a: GeoAsset) {
  return {
    id: a.id,
    name: a.name,
    aliases: a.aliases,
    type: a.type,
    country: a.country || null,
    lat: a.lat,
    lon: a.lon,
    precision: a.loc_precision,
    capacity_mw: a.capacity_mw,
    fuel: a.fuel || null,
    attrs: a.attrs,
    latest_status: a.status
      ? { status: a.status, label: STATUS_LABEL[a.status], on: a.status_on, claimant: a.status_by, events_on_record: a.events }
      : null,
    provenance: a.provenance,
    source: a.source,
    licence: a.licence,
    cite_as: abs(CITE),
    api_url: apiUrl(`/assets/${a.id}`),
  };
}

export async function assetsOp(a: Args): Promise<ApiResult> {
  const type = enumParam("type", a.type, ASSET_TYPES);
  const status = enumParam("status", a.status, ASSET_STATUSES);
  const bbox = bboxParam(a.bbox);
  const country = (a.country ?? "").trim().toUpperCase();
  if (country && !/^[A-Z]{2}$/.test(country)) throw badRequest("country must be an ISO 3166-1 alpha-2 code");
  const hasEvents = a.has_events === "true" ? true : a.has_events === "false" ? false : undefined;
  if (a.has_events && hasEvents === undefined) throw badRequest("has_events must be true or false");
  if (!bbox && !type && !country && !status && hasEvents === undefined) throw badRequest("give at least one filter (bbox, type, country, status or has_events): the ledger holds tens of thousands of places");
  const rows = await queryAssets({ bbox, type, country, status, hasEvents, limit: 2000 });
  const p = paginate(rows.map(row), limitParam(a.limit), a.cursor);
  return {
    data: { assets: p.items, total: p.total, types: ASSET_TYPES, statuses: ASSET_STATUSES },
    as_of: newest(...rows.map((r) => r.status_on)),
    cite_as: abs(CITE),
    source: "geo_assets",
    next_cursor: p.next_cursor,
    note: NOTE,
  };
}

export async function gridOp(a: Args): Promise<ApiResult> {
  const iso = (a.iso ?? "").trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(iso)) throw badRequest("iso must be an ISO 3166-1 alpha-2 code, e.g. UA");
  const g = await getGrid(iso);
  if (!g) throw notFound(`grid-impact rollup for ${iso} (published only for countries with power-plant status events in the last 30 days)`);
  return {
    data: {
      iso: g.iso,
      provenance: g.provenance,
      method: g.method,
      summary: g.line || null,
      installed: g.installed,
      windows: g.windows,
      series: g.series,
      last_event_on: g.last_event_on || null,
      caveats: g.caveats,
    },
    as_of: g.as_of,
    cite_as: abs(`/intel/actors/${iso}`),
    source: "geo_grid",
    note:
      "Ohmega analysis (provenance ohmega_derived): installed capacity from the WRI Global Power Plant Database (CC BY 4.0) and OpenStreetMap contributors (ODbL), crossed with the dated status events of /assets. " +
      "claimed = a party says it struck; reported = damage reported by owner, authorities or media; confirmed = confirmed damaged or destroyed; restored = latest word is restored. " +
      "Claimed and confirmed overlap and must not be added. share = MW / installed MW the ledger knows. Capacity is nameplate, not output; a status is not an outage duration.",
  };
}

export async function assetOp(a: Args): Promise<ApiResult> {
  const id = idParam("id", a.id);
  const asset = await getAsset(id);
  if (!asset) throw notFound(`asset ${id}`);
  const history = await assetHistory(id);
  return {
    data: {
      ...row(asset),
      history: history.map((e) => ({
        id: e.id,
        date: e.occurred_on,
        time: e.occurred_at || null,
        status: e.status,
        label: STATUS_LABEL[e.status],
        claimant: e.claimant,
        confidence: e.confidence,
        sources: e.sources,
        provenance: e.provenance,
        note: e.note || null,
        recorded_at: e.observed_at,
      })),
    },
    as_of: newest(asset.status_on, ...history.map((e) => e.occurred_on)),
    cite_as: abs(CITE),
    source: "geo_assets+geo_asset_events",
    note: NOTE,
  };
}
