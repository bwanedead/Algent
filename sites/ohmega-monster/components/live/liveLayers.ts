// /live items as interactive map layers: outages as country fills (a point where no country polygon matches), quakes as
// sized circles, military aircraft as clustered circles, fires as heat points, chokepoints as their counting line
// labelled with the day's count. The country polygons come from the backend's `live/world.json` (unprojected).

import type { LiveWorld } from "@/lib/live-shared";
import { collection, pointFeature, ringFeatures, pathRings, type Bounds, type Feature, type LngLat } from "@/components/map/geo";
import type { LayerSpec } from "@/components/map/mapLayers";

import type { Item, Layer } from "./liveItems";

const COLOR = { outage: "#c0392b", quake: "#d98a00", aircraft: "#6b4bb8", fire: "#e0561b", ships: "#0f8f99" } as const;

/** The map groups each toggle controls (an outage can draw as a fill and, unmatched, as a point). */
export const GROUPS: Record<Layer, string[]> = { outage: ["outage", "outage-pt"], quake: ["quake"], aircraft: ["aircraft"], fire: ["fire"], ships: ["ships"] };

export const WORLD_BOUNDS: Bounds = [-170, -50, 180, 78];

const props = (it: Item) => ({ id: it.id, title: it.title, layer: it.layer, major: it.major });

export function liveLayers(items: Item[], world: LiveWorld | null): LayerSpec[] {
  const byName = new Map<string, LngLat[][]>();
  if (world) for (const c of world.countries) byName.set(c.name.toLowerCase(), pathRings(c.d, world));

  const outageAreas: Feature[] = [];
  const outagePts: Feature[] = [];
  const quakes: Feature[] = [];
  const planes: Feature[] = [];
  const fires: Feature[] = [];
  const ships: Feature[] = [];
  const gates = new Map((world?.gates ?? []).map((g) => [g.region, g]));

  for (const it of items) {
    const at: LngLat | null = it.lat !== null && it.lon !== null ? [it.lon, it.lat] : null;
    switch (it.layer) {
      case "outage": {
        const rings = it.countries.flatMap((c) => byName.get(c.toLowerCase()) ?? []);
        if (rings.length > 0) outageAreas.push(...ringFeatures(rings, props(it)));
        else if (at) outagePts.push(pointFeature(at, { ...props(it), r: 8 }));
        break;
      }
      case "quake":
        if (at) quakes.push(pointFeature(at, { ...props(it), r: 4 + it.size * 4 }));
        break;
      case "aircraft":
        if (at) planes.push(pointFeature(at, { ...props(it), r: 6 }));
        break;
      case "fire":
        if (at) fires.push(pointFeature(at, { ...props(it), w: it.size * 2 }));
        break;
      case "ships": {
        const g = it.region ? gates.get(it.region) : undefined;
        if (g) ships.push({ type: "Feature", properties: props(it), geometry: { type: "LineString", coordinates: [[g.a[1], g.a[0]], [g.b[1], g.b[0]]] } });
        if (at) ships.push(pointFeature(at, { ...props(it), badge: it.badge ?? "" }));
        break;
      }
    }
  }

  const specs: LayerSpec[] = [];
  if (outageAreas.length) specs.push({ group: "outage", kind: "area", color: COLOR.outage, data: collection(outageAreas) });
  if (outagePts.length) specs.push({ group: "outage-pt", kind: "dots", color: COLOR.outage, data: collection(outagePts) });
  if (fires.length) specs.push({ group: "fire", kind: "heat", color: COLOR.fire, data: collection(fires) });
  if (ships.length) specs.push({ group: "ships", kind: "line", color: COLOR.ships, labelProp: "badge", data: collection(ships) });
  if (planes.length) specs.push({ group: "aircraft", kind: "dots", cluster: true, color: COLOR.aircraft, data: collection(planes) });
  if (quakes.length) specs.push({ group: "quake", kind: "dots", color: COLOR.quake, data: collection(quakes) });
  return specs;
}
