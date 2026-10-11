// A daily/dossier `TheaterMap` (the backend's frame spec) as interactive layers: numbered development marks that match
// the development list, disputed/occupied areas as polygons, and chokepoint readings. Pure and client-safe: `import type`
// only from lib/daily (which reaches server-only modules), never a value import.

import type { DailyDevelopment, TheaterMap } from "@/lib/daily";

import { boundsOf, collection, pathRings, pointFeature, ringFeatures, unproject, type Bounds, type Feature, type LngLat } from "./geo";
import type { LayerSpec } from "./mapLayers";
import type { MapItem } from "./LiveMap";
import { mapIndexBase } from "./numbering";

const MARK = "#c2410c"; // vermilion: reads on the cream basemap and the dark one
const DISPUTED = "#7a4fa3"; // plum, used for nothing else, as in the static map
const GATE = "#0f8f99";
const MAX_DETAIL = 320;

const clip = (s: string) => (s.length > MAX_DETAIL ? `${s.slice(0, MAX_DETAIL - 1).trimEnd()}…` : s);

export type TheaterLayers = { layers: LayerSpec[]; items: MapItem[]; bounds: Bounds };

export function theaterLayers(map: TheaterMap, developments: DailyDevelopment[]): TheaterLayers {
  const base = mapIndexBase(map, developments.length);
  const at = (p: { x: number | null; y: number | null; lon: number | null; lat: number | null }): LngLat | null =>
    p.lon !== null && p.lat !== null ? [p.lon, p.lat] : p.x !== null && p.y !== null ? unproject(map, p.x, p.y) : null;

  const items: MapItem[] = [];
  const marks: Feature[] = [];
  map.points.forEach((p, i) => {
    const lngLat = at(p);
    if (!lngLat) return;
    const di = p.n === null ? -1 : p.n - base;
    const dev = di >= 0 && di < developments.length ? developments[di] : null;
    const num = dev ? di + 1 : p.n ?? i + 1;
    const id = `p${i}`;
    marks.push(pointFeature(lngLat, { id, num, place: p.label, headline: dev ? dev.headline : p.label, detail: dev ? dev.detail : "", when: p.date, verification: p.verification, di }));
    items.push({ id, label: `${num}. ${dev ? dev.headline : p.label}` });
  });

  const areas: Feature[] = map.disputed.flatMap((a, i) => {
    const rings = a.rings.length > 0 ? a.rings.map((poly) => poly.map((r) => r as LngLat[])) : pathRings(a.d, map).map((r) => [r]);
    const props = { id: `d${i}`, name: a.name, note: a.note, status: a.status, source: a.source };
    return rings.map((coords): Feature => ({ type: "Feature", properties: props, geometry: { type: "Polygon", coordinates: coords } }));
  });

  const gates: Feature[] = map.annotations.flatMap((a, i) => {
    const lngLat = at(a);
    return lngLat ? [pointFeature(lngLat, { id: `c${i}`, title: a.title, lines: a.lines.join("\n"), source: a.source, r: 7 })] : [];
  });

  const layers: LayerSpec[] = [];
  if (areas.length > 0) {
    layers.push({
      group: "disputed", kind: "area", color: DISPUTED, dashed: true, data: collection(areas),
      popup: (p) => ({ kind: "Disputed or occupied territory", title: String(p.name), text: String(p.note ?? ""), source: typeof p.source === "string" && p.source ? "Status source" : "Natural Earth", url: typeof p.source === "string" ? p.source : "" }),
    });
  }
  if (gates.length > 0) {
    layers.push({
      group: "gates", kind: "dots", color: GATE, data: collection(gates),
      popup: (p) => ({ kind: "Shipping chokepoint", title: String(p.title), lines: String(p.lines ?? "").split("\n").filter(Boolean), source: String(p.source ?? "") }),
    });
  }
  layers.push({
    group: "marks", kind: "numbered", color: MARK, labelProp: "num", data: collection(marks),
    popup: (p) => ({
      kind: String(p.place || "Reported place"),
      title: `${p.num}. ${p.headline}`,
      when: [p.when, p.verification === "researched" ? "researched" : "reported"].filter(Boolean).join(" · "),
      text: clip(String(p.detail ?? "")),
    }),
  });

  const frame = map.bbox.length === 4 ? (map.bbox as Bounds) : boundsOf(marks.map((m) => (m.geometry.type === "Point" ? m.geometry.coordinates : [0, 0])));
  return { layers, items, bounds: frame ?? [-180, -60, 180, 80] };
}
