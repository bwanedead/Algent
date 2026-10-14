// The live events of a theater strip as layers on the theater's map, drawn exactly as /live draws the same kinds (same colours,
// same halo dots, same radius rule as liveLayers.ts: quakes scale with magnitude, outages are the plain 4 px halo dot, notable
// fires the red ringed dot). Kinds /live has no point look for (military aircraft regions, plain fires) take the colour the
// live pages already give them. Ids are `live:<event id>` so a "Show me" request can find the feature. Client-safe.

import { collection, pointFeature, type Feature } from "@/components/map/geo";
import type { LayerSpec } from "@/components/map/mapLayers";
import { KIND_LABEL } from "@/lib/live-shared";

import type { Item } from "./liveItems";
import { COLOR } from "./liveLayers";

const AIRCRAFT = "#8b6fd6"; // the aircraft colour of /live (TrackLayers group colour, the legend)
const FIRE_NOTE = "#ff3d1f"; // /live's notable-fire dot
const MAX_DETAIL = 320;

export const liveFeatureId = (eventId: string) => `live:${eventId}`;

const look = (it: Item): { group: string; color: string; r: number } => {
  switch (it.layer) {
    case "quake": return { group: "live-quake", color: COLOR.quake, r: 2.5 + it.size * 1.6 };
    case "fire": return { group: "live-fire", color: FIRE_NOTE, r: 4.5 };
    case "aircraft": return { group: "live-aircraft", color: AIRCRAFT, r: 4 };
    default: return { group: "live-outage", color: COLOR.outage, r: 4 };
  }
};

export function eventLayers(items: Item[]): LayerSpec[] {
  const byGroup = new Map<string, { color: string; features: Feature[] }>();
  for (const it of items) {
    if (it.lat === null || it.lon === null || it.layer === "gates") continue;
    const { group, color, r } = look(it);
    const detail = it.detail.length > MAX_DETAIL ? `${it.detail.slice(0, MAX_DETAIL - 1).trimEnd()}…` : it.detail;
    const f = pointFeature([it.lon, it.lat], { id: liveFeatureId(it.id), title: it.title, layer: it.layer, major: it.major, text: detail, when: it.when, source: it.source, url: it.url, r });
    const g = byGroup.get(group) ?? { color, features: [] };
    g.features.push(f);
    byGroup.set(group, g);
  }
  return Array.from(byGroup, ([group, g]): LayerSpec => ({
    group, kind: "dots", halo: true, color: g.color, data: collection(g.features),
    popup: (p) => ({ kind: `Live: ${KIND_LABEL[p.layer as keyof typeof KIND_LABEL] ?? "event"}`, title: String(p.title), when: String(p.when ?? ""), text: String(p.text ?? ""), source: String(p.source ?? ""), url: String(p.url ?? "") }),
  }));
}
