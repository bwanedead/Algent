// The infrastructure layer of a theater map: the geoledger's places (power plants, substations, refineries, ports, bases...)
// as small discs, each wearing its type's letter and coloured by its latest status (backend `geoledger/`, lib/geoledger-shared.ts).
// Pure and client-safe: types and helpers from lib/geoledger-shared only, never lib/geoledger (server).
//
// Reading the map: warm red = hit (lighter orange when it is only a party's CLAIM, red when damage is REPORTED, deep red when
// CONFIRMED or destroyed), green = restored, blue = seized or designated, grey = nothing on record. A status fades as it ages
// (FADE_DAYS); a place that merely exists never fades. Tapping a place opens its card: type, capacity, latest status, history.

import {
  capacityLabel, freshness, historyLine, statusTone, STATUS_LABEL, TONE, TYPE_GLYPH, TYPE_LABEL,
  type GeoAsset, type GeoLogRow,
} from "@/lib/geoledger-shared";

import { collection, pointFeature, type Feature } from "./geo";
import type { LayerSpec } from "./mapLayers";

const QUIET = 0.55; // a place with no status on record: present, not shouting
const R_STATUS = 8;
const R_QUIET = 5.5;
const HISTORY_LINES = 6;
const host = (u: string): string => {
  try {
    return new URL(u).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
};

/** What the key under the map explains, in the order it reads. */
export const ASSET_KEY: { color: string; label: string }[] = [
  { color: TONE.claimed, label: "claimed struck (a party's claim only)" },
  { color: TONE.reported, label: "damage reported" },
  { color: TONE.confirmed, label: "damage confirmed or destroyed" },
  { color: TONE.restored, label: "restored" },
  { color: TONE.neutral, label: "nothing on record" },
];

/** `links: false` on a place's own page, where a link to itself would be noise. */
export function assetLayer(assets: GeoAsset[], log: GeoLogRow[], now: Date = new Date(), links = true): LayerSpec | null {
  const history = new Map<string, GeoLogRow[]>();
  for (const e of log) history.set(e.asset_id, [...(history.get(e.asset_id) ?? []), e]);

  const placed = assets.filter((a) => a.lat !== null && a.lon !== null);
  if (placed.length === 0) return null;
  const features: Feature[] = [...placed]
    .sort((a, b) => a.events - b.events) // places with a status draw last: on top
    .map((a) => {
      const week = history.get(a.id) ?? [];
      const hit = a.status !== null;
      return pointFeature([a.lon as number, a.lat as number], {
        id: `as-${a.id}`,
        page: links ? `/intel/places/${a.id}` : "",
        ev: a.events,
        g: TYPE_GLYPH[a.type],
        col: hit ? statusTone(a.status) : TONE.neutral,
        op: hit ? freshness(a.status, a.status_on, now) : QUIET,
        r: a.events > 0 ? R_STATUS : R_QUIET,
        name: a.name,
        kind: [TYPE_LABEL[a.type], capacityLabel(a)].filter(Boolean).join(" · "),
        when: a.status ? `${STATUS_LABEL[a.status]}${a.status_by ? ` · ${a.status_by}` : ""}${a.status_on ? ` · ${a.status_on}` : ""}` : "",
        hist: week.slice(0, HISTORY_LINES).map((e) => historyLine(e) + (e.sources[0] ? ` — ${host(e.sources[0])}` : "")).join("\n"),
        more: Math.max(0, a.events - Math.min(week.length, HISTORY_LINES)),
        url: week[0]?.sources[0] ?? "",
        credit: [a.source, a.licence].filter(Boolean).join(", "),
        derived: a.provenance === "ohmega_derived",
        spot: a.loc_precision === "approximate" || a.loc_precision === "city_level" ? a.loc_precision : "",
      });
    });

  return {
    group: "infra",
    kind: "assets",
    color: TONE.neutral,
    labelProp: "g",
    data: collection(features),
    popup: (p) => {
      const lines = String(p.hist ?? "").split("\n").filter(Boolean);
      const more = Number(p.more ?? 0);
      if (more > 0) lines.push(`${more} earlier status${more === 1 ? "" : "es"} on record`);
      if (p.derived) lines.push("Place found by our own reading of the reports; position approximate.");
      else if (p.spot === "city_level") lines.push("Position is the town's, not the site's.");
      return {
        kind: String(p.kind ?? ""),
        title: String(p.name ?? ""),
        when: String(p.when ?? "") || "No status on record",
        lines,
        url: String(p.url ?? ""),
        href: String(p.page ?? ""),
        source: p.url ? `Latest status source (${host(String(p.url))})` : String(p.credit ?? ""),
      };
    },
  };
}
