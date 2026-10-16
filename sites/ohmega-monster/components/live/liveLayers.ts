// /live events as interactive map layers, in a restrained palette: outages are soft country fills (a small dot where no country
// polygon matches), quakes small circles with a thin halo scaled by magnitude, fires a heat surface from the world grid that
// resolves into small dots (notable fires get a ringed dot), chokepoints a thin dashed counting line with a short live label.
// Ships and aircraft are drawn by TrackLayers.ts. Country polygons come from the backend's `live/world.json` (unprojected).

import { ANOMALY_COLOR, type FiresDoc, type GateNow, type LiveAnomaly, type LiveWorld } from "@/lib/live-shared";
import { collection, pointFeature, ringFeatures, pathRings, type Bounds, type Feature, type LngLat } from "@/components/map/geo";
import type { LayerSpec } from "@/components/map/mapLayers";

import type { Item, Layer } from "./liveItems";

export const COLOR = { outage: "#c4574a", quake: "#d9a521", fire: "#ea6a22", gates: "#2a8f9c" } as const;

/** The map groups each toggle controls (an outage can draw as a fill and, unmatched, as a point). Aircraft regions are list-only. */
export const GROUPS: Record<Layer | "anomalies", string[]> = { outage: ["outage", "outage-pt"], quake: ["quake"], aircraft: [], fire: ["fire", "fire-note"], gates: ["gates"], anomalies: ["anomalies"] };

/** Places flagged as outside their learned normal (backend `live/memory`): a thin ring per still-going anomaly, warm above normal and cool below, a touch
 *  larger when more confident. Drawn over the other layers without changing them; the popup says what it is and what it is not. */
export function anomalyRings(anoms: LiveAnomaly[]): LayerSpec | null {
  const features = anoms
    .filter((a) => a.active && a.lat !== null && a.lon !== null)
    .map((a) => pointFeature([a.lon as number, a.lat as number], { id: `anomaly:${a.id}`, title: a.sentence, col: ANOMALY_COLOR[a.direction], r: 8 + Math.round(6 * a.confidence), conf: Math.round(a.confidence * 100), learn: a.learning }));
  if (features.length === 0) return null;
  return {
    group: "anomalies", kind: "rings", color: ANOMALY_COLOR.above, data: collection(features),
    popup: (p) => ({
      kind: "Unusual · Ohmega analysis",
      title: String(p.title),
      text: `Counted by Ohmega from public live feeds and compared with its own learned normal for this place and hour of the week (confidence ${p.conf}%${p.learn ? ", young baseline" : ""}). It shows the pattern departs from normal, not why: a closed port, a rerouting and a sensor gap we could not screen out look alike.`,
      source: "Ohmega, from live ship, aircraft and satellite feeds",
    }),
  };
}

export const WORLD_BOUNDS: Bounds = [-170, -50, 180, 78];

const props = (it: Item) => ({ id: it.id, title: it.title, layer: it.layer, major: it.major });

export function liveLayers(items: Item[], world: LiveWorld | null, fires: FiresDoc | null, gates: Record<string, GateNow> | undefined): LayerSpec[] {
  const byName = new Map<string, LngLat[][]>();
  if (world) for (const c of world.countries) byName.set(c.name.toLowerCase(), pathRings(c.d, world));

  const outageAreas: Feature[] = [];
  const outagePts: Feature[] = [];
  const quakes: Feature[] = [];
  const notableFires: Feature[] = [];
  const gateFeatures: Feature[] = [];

  for (const it of items) {
    const at: LngLat | null = it.lat !== null && it.lon !== null ? [it.lon, it.lat] : null;
    switch (it.layer) {
      case "outage": {
        const rings = it.countries.flatMap((c) => byName.get(c.toLowerCase()) ?? []);
        if (rings.length > 0) outageAreas.push(...ringFeatures(rings, props(it)));
        else if (at) outagePts.push(pointFeature(at, { ...props(it), r: 4 }));
        break;
      }
      case "quake":
        if (at) quakes.push(pointFeature(at, { ...props(it), r: 2.5 + it.size * 1.6 }));
        break;
      case "fire":
        if (at && it.notable) notableFires.push(pointFeature(at, { ...props(it), r: 4.5 }));
        break;
      default:
        break;
    }
  }

  const lines = new Map((world?.gates ?? []).map((g) => [g.region, g]));
  for (const [slug, g] of Object.entries(gates ?? {})) {
    const line = lines.get(slug);
    const id = `gate:${slug}`;
    if (line) gateFeatures.push({ type: "Feature", properties: { id, title: g.label }, geometry: { type: "LineString", coordinates: [[line.a[1], line.a[0]], [line.b[1], line.b[0]]] } });
    const short = g.label.replace(/^(Strait of|Strait|Canal) /, "");
    const badge = typeof g.in_strait === "number" ? `${short} · ${g.in_strait} now` : short;
    gateFeatures.push(pointFeature([g.lon, g.lat], { id, title: g.label, badge }));
  }

  const specs: LayerSpec[] = [];
  if (outageAreas.length) specs.push({ group: "outage", kind: "area", soft: true, color: COLOR.outage, data: collection(outageAreas) });
  if (outagePts.length) specs.push({ group: "outage-pt", kind: "dots", halo: true, color: COLOR.outage, data: collection(outagePts) });
  if (fires && fires.cells.length) {
    const cells = fires.cells.map(([lon, lat, n, frp]) =>
      pointFeature([lon, lat], { w: Math.round(Math.min(1, 0.18 + Math.log2(n + 1) / 7 + Math.min(frp, 300) / 900) * 100) / 100, f: frp, n }));
    specs.push({
      group: "fire", kind: "heat", color: COLOR.fire, data: collection(cells),
      popup: (p) => (p.f !== undefined ? { kind: "Satellite heat", title: `${p.n} heat reading${p.n === 1 ? "" : "s"} in a ~27 km cell`, text: `Strongest ${p.f} MW in the last day. A wildfire, an industrial flare or a strike can look the same.`, source: "NASA FIRMS (VIIRS)", url: "https://firms.modaps.eosdis.nasa.gov/map/" } : null),
    });
  }
  if (notableFires.length) specs.push({ group: "fire-note", kind: "dots", halo: true, color: "#ff3d1f", data: collection(notableFires) });
  if (gateFeatures.length) specs.push({ group: "gates", kind: "line", color: COLOR.gates, labelProp: "badge", data: collection(gateFeatures) });
  if (quakes.length) specs.push({ group: "quake", kind: "dots", halo: true, color: COLOR.quake, data: collection(quakes) });
  return specs;
}
