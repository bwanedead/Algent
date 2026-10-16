// Pure geometry and state of a native flow map (NativeFlow.tsx; contract: backend agents/intel/flow_spec.py). Arcs between places,
// their widths from the stated amounts, which routes are running / cut / rerouted at a given disruption step, and the GeoJSON of
// one animation frame (arcs, particles moving along them, places, cut marks). No DOM, no MapLibre.

import type { FlowRoute, FlowSpec, LonLat, MapTone } from "@/lib/visualSpecs";

import { collection, pointFeature, type Feature, type FeatureCollection } from "./geo";
import type { Palette } from "./storyFrame";

export type RouteState = "run" | "cut" | "alt" | "hidden";

const cosLat = (lat: number) => Math.max(Math.cos((lat * Math.PI) / 180), 0.05);

/** A curve from a to b bowed to the left of travel (so a pair of opposite flows do not overlap), as lon/lat points. */
export function arc(a: LonLat, b: LonLat, n = 36): LonLat[] {
  const dx = (b[0] - a[0]) * cosLat((a[1] + b[1]) / 2);
  const dy = b[1] - a[1];
  const k = 0.2;
  const c: LonLat = [(a[0] + b[0]) / 2 - (dy * k) / cosLat((a[1] + b[1]) / 2), (a[1] + b[1]) / 2 + dx * k];
  return Array.from({ length: n + 1 }, (_, i) => {
    const t = i / n;
    const u = 1 - t;
    return [u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]] as LonLat;
  });
}

/** The whole route of a flow: arcs source -> via... -> target, joined. */
export function routeOf(spec: FlowSpec, f: FlowRoute): LonLat[] {
  const at = new Map(spec.places.map((p): [string, LonLat] => [p.id, p.at]));
  const stops = [f.source, ...f.via, f.target].map((id) => at.get(id)).filter((p): p is LonLat => !!p);
  return stops.slice(1).flatMap((p, i) => arc(stops[i], p).slice(i === 0 ? 0 : 1));
}

/** Cumulative length (degrees, longitude squeezed by latitude) along a polyline, for placing particles evenly. */
export function cumulative(path: LonLat[]): number[] {
  const out = [0];
  for (let i = 1; i < path.length; i++) out.push(out[i - 1] + Math.hypot((path[i][0] - path[i - 1][0]) * cosLat(path[i][1]), path[i][1] - path[i - 1][1]));
  return out;
}

/** The point `frac` (0..1) of the way along a polyline whose cumulative lengths are `cum`. */
export function pointAt(path: LonLat[], cum: number[], frac: number): LonLat {
  const total = cum[cum.length - 1];
  const want = Math.min(1, Math.max(0, frac)) * total;
  let i = 1;
  while (i < cum.length - 1 && cum[i] < want) i++;
  const span = cum[i] - cum[i - 1] || 1;
  const t = (want - cum[i - 1]) / span;
  return [path[i - 1][0] + (path[i][0] - path[i - 1][0]) * t, path[i - 1][1] + (path[i][1] - path[i - 1][1]) * t];
}

/** Line width in px per flow: in proportion to the amount among flows sharing a unit; a mid width where no figure is stated. */
export function widths(spec: FlowSpec): Map<string, number> {
  const out = new Map(spec.flows.map((f): [string, number] => [f.id, 2.5]));
  const byUnit = new Map<string, FlowRoute[]>();
  for (const f of spec.flows) if (f.amount > 0) byUnit.set(f.unit.toLowerCase(), [...(byUnit.get(f.unit.toLowerCase()) ?? []), f]);
  byUnit.forEach((fs) => {
    const top = Math.max(...fs.map((f) => f.amount));
    for (const f of fs) out.set(f.id, fs.length > 1 ? Math.round((1.5 + (8 * f.amount) / top) * 10) / 10 : 5);
  });
  return out;
}

/** What every flow is doing once the first `step` disruptions have happened. A flow is cut if it, or a place on its route, is
 *  broken; a flow named as a reroute is hidden until a disruption that lists it is on. */
export function states(spec: FlowSpec, step: number): Map<string, RouteState> {
  const on = spec.disruptions.slice(0, step);
  const broken = new Set(on.flatMap((d) => d.breaks));
  const alt = new Set(on.flatMap((d) => d.reroutes));
  const anyAlt = new Set(spec.disruptions.flatMap((d) => d.reroutes));
  return new Map(
    spec.flows.map((f): [string, RouteState] => {
      const cut = broken.has(f.id) || [f.source, f.target, ...f.via].some((p) => broken.has(p));
      return [f.id, alt.has(f.id) && !cut ? "alt" : cut ? "cut" : anyAlt.has(f.id) ? "hidden" : "run"];
    }),
  );
}

/** One colour tone per commodity, in order of first appearance (never the reserved cut / reroute tones). */
export function commodityTones(spec: FlowSpec): Map<string, MapTone> {
  const tones: MapTone[] = ["cool", "accent", "warn", "ink"];
  const out = new Map<string, MapTone>();
  for (const f of spec.flows) {
    const k = f.commodity.toLowerCase();
    if (!out.has(k)) out.set(k, tones[out.size % tones.length]);
  }
  return out;
}

export type FlowFrame = { line: FeatureCollection; pt: FeatureCollection; dots: FeatureCollection; lbl: FeatureCollection; cut: FeatureCollection };

/** The GeoJSON of the frame at time `ms`. `still` freezes the particles (reduced motion); `sel` is the selected flow id. */
export function frameAt(spec: FlowSpec, step: number, ms: number, sel: string | null, pal: Palette, still: boolean): FlowFrame {
  const st = states(spec, step);
  const w = widths(spec);
  const tone = commodityTones(spec);
  const lines: Feature[] = [];
  const dots: Feature[] = [];
  const cuts: Feature[] = [];
  for (const f of spec.flows) {
    const s = st.get(f.id) ?? "run";
    if (s === "hidden") continue;
    const path = routeOf(spec, f);
    if (path.length < 2) continue;
    const cum = cumulative(path);
    const color = s === "cut" ? pal.hot : s === "alt" ? pal.good : pal[tone.get(f.commodity.toLowerCase()) ?? "cool"];
    const width = w.get(f.id) ?? 2.5;
    const dim = sel !== null && sel !== f.id;
    lines.push({ type: "Feature", properties: { id: f.id, color, w: width + (sel === f.id ? 1.5 : 0), state: s, op: dim ? 0.3 : s === "cut" ? 0.85 : 0.5 }, geometry: { type: "LineString", coordinates: path } });
    if (s === "cut") {
      cuts.push(pointFeature(pointAt(path, cum, 0.5), { id: f.id, color, op: dim ? 0.4 : 1 }));
      continue;
    }
    const n = 3 + Math.round(width / 2);
    for (let i = 0; i < n; i++) {
      const phase = still ? (i + 0.5) / n : (i / n + ms / 5200 + (f.id.length % 7) / 7) % 1;
      dots.push(pointFeature(pointAt(path, cum, phase), { id: f.id, color, r: 1.8 + width * 0.32 + (still && i === n - 1 ? 1.2 : 0), op: dim ? 0.35 : 1 }));
    }
  }
  const broken = new Set(spec.disruptions.slice(0, step).flatMap((d) => d.breaks));
  const pt = spec.places.map((p) => pointFeature(p.at, { id: p.id, color: broken.has(p.id) ? pal.hot : pal.ink, r: p.role === "chokepoint" ? 6 : 4.5 }));
  const lbl = spec.places.map((p) => pointFeature(p.at, { id: p.id, text: p.name }));
  return { line: collection(lines), pt: collection(pt), dots: collection(dots), lbl: collection(lbl), cut: collection(cuts) };
}
