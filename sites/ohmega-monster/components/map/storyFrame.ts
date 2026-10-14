// Pure animation maths of a map story (MapStory.tsx; contract: backend agents/intel/mapstory_spec.py).
// `frameAt(timelines, pos, ...)` turns a continuous position along the story (0 = the first step, 1 = the second, 2.5 =
// half way from the third to the fourth) into the GeoJSON to draw: features appear, move, and disappear as `pos`
// passes the steps that introduce, replace or hide them. No DOM, no MapLibre.
//
// The rule: a step's changes animate while `pos` travels from step-1 to step (progress p = 0..1, eased), and are
// complete when `pos` reaches the step. So at an integer `pos` everything is at rest, and the first step's features are
// simply there. A feature's history is its list of events (show with a geometry, or hide) in step order:
//   - first show, or show after a hide ("intro"): points grow in, routes draw themselves, areas fade in, rings expand;
//   - show of an id already on the map ("move"): a point glides to the new place; any other shape switches at half way;
//   - hide: the feature fades out over its step.

import type { LonLat, MapFeature, MapStorySpec, MapTone } from "@/lib/visualSpecs";

import { collection, type Feature, type FeatureCollection } from "./geo";

export type Ev = { step: number; f: MapFeature | null }; // null = hide
export type Timelines = Map<string, Ev[]>;
export type Palette = Record<MapTone, string>;
export type Frame = { poly: FeatureCollection; line: FeatureCollection; pt: FeatureCollection; lbl: FeatureCollection };

export function buildTimelines(spec: MapStorySpec): Timelines {
  const tl: Timelines = new Map();
  const push = (id: string, ev: Ev) => tl.set(id, [...(tl.get(id) ?? []), ev]);
  spec.steps.forEach((s, i) => {
    for (const id of s.hide) if (tl.has(id)) push(id, { step: i, f: null });
    for (const f of s.show) push(f.id, { step: i, f });
  });
  return tl;
}

const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
export const ease = (p: number) => (p < 0.5 ? 2 * p * p : 1 - (-2 * p + 2) ** 2 / 2);
const lerp = (a: LonLat, b: LonLat, t: number): LonLat => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const cosLat = (lat: number) => Math.max(Math.cos((lat * Math.PI) / 180), 0.05);

/** A circle of `km` about `c` as a closed ring (lon/lat). */
export function circle(c: LonLat, km: number, n = 64): LonLat[] {
  const dLat = km / 111.32;
  const dLon = km / (111.32 * cosLat(c[1]));
  return Array.from({ length: n + 1 }, (_, i) => {
    const a = (2 * Math.PI * i) / n;
    return [c[0] + dLon * Math.cos(a), c[1] + dLat * Math.sin(a)] as LonLat;
  });
}

/** The first `frac` (0..1) of a path by length, ending exactly at the cut. Lengths are measured with the longitude
 *  squeezed by cos(latitude), so a drawn route grows evenly on the map. */
export function partial(path: LonLat[], frac: number): LonLat[] {
  if (frac >= 1) return path;
  const seg = path.slice(1).map((p, i) => Math.hypot((p[0] - path[i][0]) * cosLat(p[1]), p[1] - path[i][1]));
  const total = seg.reduce((a, b) => a + b, 0);
  let left = total * clamp01(frac);
  const out: LonLat[] = [path[0]];
  for (let i = 0; i < seg.length; i++) {
    if (left >= seg[i]) {
      out.push(path[i + 1]);
      left -= seg[i];
    } else {
      out.push(seg[i] > 0 ? lerp(path[i], path[i + 1], left / seg[i]) : path[i + 1]);
      break;
    }
  }
  return out;
}

/** A filled triangle at the end of a path, pointing along its last stretch; `size` is its length in degrees of latitude. */
export function arrowHead(path: LonLat[], size: number): LonLat[] | null {
  const tip = path[path.length - 1];
  let k = path.length - 2;
  while (k >= 0 && path[k][0] === tip[0] && path[k][1] === tip[1]) k--;
  if (k < 0) return null;
  const c = cosLat(tip[1]);
  const dx = (tip[0] - path[k][0]) * c;
  const dy = tip[1] - path[k][1];
  const len = Math.hypot(dx, dy);
  if (len === 0) return null;
  const ux = dx / len;
  const uy = dy / len;
  const wing = (sign: number): LonLat => {
    const a = sign * 0.45;
    const bx = -(ux * Math.cos(a) - uy * Math.sin(a)) * size;
    const by = -(ux * Math.sin(a) + uy * Math.cos(a)) * size;
    return [tip[0] + bx / c, tip[1] + by];
  };
  return [tip, wing(1), wing(-1), tip];
}

const bboxCentre = (ring: LonLat[]): LonLat => {
  const xs = ring.map((p) => p[0]);
  const ys = ring.map((p) => p[1]);
  return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
};

type Out = { poly: Feature[]; line: Feature[]; pt: Feature[]; lbl: Feature[] };
const feat = (geometry: Feature["geometry"], properties: Feature["properties"]): Feature => ({ type: "Feature", properties, geometry });

function emit(out: Out, f: MapFeature, o: { op: number; grow: number; from: MapFeature | null; t: number; pal: Palette; head: number }) {
  const color = o.pal[f.tone];
  const label = (at: LonLat) => {
    if (f.label) out.lbl.push(feat({ type: "Point", coordinates: at }, { text: f.label, op: o.op }));
  };
  if (f.type === "point") {
    const at = o.from?.type === "point" ? lerp(o.from.at, f.at, o.t) : f.at;
    out.pt.push(feat({ type: "Point", coordinates: at }, { op: o.op, color, r: 4 + 3 * o.grow }));
    label(at);
  } else if (f.type === "route") {
    const path = o.from?.type === "route" && o.t < 0.5 ? o.from.path : f.path;
    const drawn = partial(path, o.grow);
    out.line.push(feat({ type: "LineString", coordinates: drawn }, { op: o.op, color }));
    const head = f.arrow ? arrowHead(drawn, o.head) : null;
    if (head) out.poly.push(feat({ type: "Polygon", coordinates: [head] }, { op: o.op, color, fa: 1, kind: "head" }));
    label(drawn[drawn.length - 1]);
  } else if (f.type === "area") {
    const ring = o.from?.type === "area" && o.t < 0.5 ? o.from.ring : f.ring;
    const closed = ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1] ? ring : [...ring, ring[0]];
    out.poly.push(feat({ type: "Polygon", coordinates: [closed] }, { op: o.op * (0.4 + 0.6 * o.grow), color, fa: 0.28, kind: "area" }));
    label(bboxCentre(ring));
  } else {
    const at = o.from?.type === "range" ? lerp(o.from.at, f.at, o.t) : f.at;
    const km = f.radius_km * Math.max(o.grow, 0.02);
    out.poly.push(feat({ type: "Polygon", coordinates: [circle(at, km)] }, { op: o.op, color, fa: 0.08, kind: "range" }));
    label([at[0], at[1] + km / 111.32]);
  }
}

/** The drawing at position `pos`. `head` is the arrowhead length in degrees (a share of the frame, so it reads at the fitted zoom). */
export function frameAt(tl: Timelines, pos: number, pal: Palette, head: number): Frame {
  const out: Out = { poly: [], line: [], pt: [], lbl: [] };
  for (const evs of tl.values()) {
    let j = -1;
    evs.forEach((e, k) => {
      if (pos > e.step - 1) j = k; // an event has begun once pos has passed the step before it
    });
    if (j < 0) continue;
    const e = evs[j];
    const prev = evs[j - 1]?.f ?? null;
    const p = clamp01(pos - (e.step - 1));
    const k = ease(p);
    if (!e.f) {
      if (prev && p < 1) emit(out, prev, { op: 1 - k, grow: 1, from: null, t: 1, pal, head });
    } else if (!prev) {
      emit(out, e.f, { op: e.f.type === "route" ? 1 : k, grow: k, from: null, t: 1, pal, head });
    } else {
      emit(out, e.f, { op: 1, grow: 1, from: prev, t: k, pal, head });
    }
  }
  return { poly: collection(out.poly), line: collection(out.line), pt: collection(out.pt), lbl: collection(out.lbl) };
}
