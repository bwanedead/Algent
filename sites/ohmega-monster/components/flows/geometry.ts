// Great-circle paths on the unit sphere for the flow layer. A path is a run of unit vectors with the cumulative arc length (radians)
// at each, so a particle at "distance s along the lane" is one binary search and a lerp. The vectors use the globe's convention
// (lib/globe/view.ts projectPoint: x = cos(lat)cos(lon), y = cos(lat)sin(lon), z = sin(lat)), so the globe's 3x3 view matrix
// projects them directly. Pure TS, client-safe, no allocation per frame.

import { RAD } from "@/lib/globe/sphere";

export type Vec = [number, number, number];

export type Path = {
  /** Flat x,y,z per sample. */
  v: Float32Array;
  /** Arc length from the start (radians) at each sample. */
  cum: Float32Array;
  /** Total arc length (radians). */
  total: number;
  n: number;
};

const EARTH_KM = 6371;
export const kmOf = (rad: number): number => rad * EARTH_KM;

export function toVec(lat: number, lon: number): Vec {
  const b = lat * RAD, a = lon * RAD, c = Math.cos(b);
  return [c * Math.cos(a), c * Math.sin(a), Math.sin(b)];
}

const dot = (a: Vec, b: Vec): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

/** Spherical interpolation between two unit vectors (`t` 0..1) for a leg of angle `omega`. */
function slerp(a: Vec, b: Vec, omega: number, t: number, out: Vec): void {
  if (omega < 1e-6) { out[0] = a[0]; out[1] = a[1]; out[2] = a[2]; return; }
  const so = Math.sin(omega), ka = Math.sin((1 - t) * omega) / so, kb = Math.sin(t * omega) / so;
  out[0] = ka * a[0] + kb * b[0];
  out[1] = ka * a[1] + kb * b[1];
  out[2] = ka * a[2] + kb * b[2];
}

/** A smooth path through the [lat, lon] points, great-circle between neighbours, sampled about every `stepDeg` degrees. `lift` raises
 *  the middle of each whole path off the surface (an arc: 0 for lanes on the sea, ~0.1 for trade arcs); the radius is folded into the vector. */
export function buildPath(points: ReadonlyArray<readonly [number, number]>, stepDeg = 1.5, lift = 0): Path {
  const legs = points.map(([la, lo]) => toVec(la, lo));
  const xs: number[] = [], cs: number[] = [];
  const tmp: Vec = [0, 0, 0];
  let acc = 0;
  for (let i = 0; i + 1 < legs.length; i++) {
    const omega = Math.acos(Math.max(-1, Math.min(1, dot(legs[i], legs[i + 1]))));
    const steps = Math.max(1, Math.ceil((omega / RAD) / stepDeg));
    for (let k = i === 0 ? 0 : 1; k <= steps; k++) {
      slerp(legs[i], legs[i + 1], omega, k / steps, tmp);
      xs.push(tmp[0], tmp[1], tmp[2]);
      cs.push(acc + (omega * k) / steps);
    }
    acc += omega;
  }
  const n = cs.length;
  const v = new Float32Array(xs);
  if (lift > 0 && acc > 0) { // raise by a half sine of the path's own progress, scaled by how long it is (a short hop stays low)
    for (let i = 0; i < n; i++) {
      const r = 1 + lift * Math.min(1, acc / 1.2) * Math.sin(Math.PI * (cs[i] / acc));
      v[i * 3] *= r; v[i * 3 + 1] *= r; v[i * 3 + 2] *= r;
    }
  }
  return { v, cum: new Float32Array(cs), total: acc, n };
}

/** The sample index whose cumulative length is the last one <= s (0..n-2). */
function indexAt(p: Path, s: number): number {
  let lo = 0, hi = p.n - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (p.cum[mid] <= s) lo = mid; else hi = mid;
  }
  return lo;
}

/** The vector at distance `s` (radians, clamped) along the path, written into `out`. */
export function pointAt(p: Path, s: number, out: Vec): void {
  if (p.n < 2) { out[0] = p.v[0] ?? 0; out[1] = p.v[1] ?? 0; out[2] = p.v[2] ?? 0; return; }
  const i = indexAt(p, Math.max(0, Math.min(p.total, s)));
  const span = p.cum[i + 1] - p.cum[i];
  const f = span > 0 ? Math.max(0, Math.min(1, (s - p.cum[i]) / span)) : 0;
  const a = i * 3, b = a + 3;
  out[0] = p.v[a] + (p.v[b] - p.v[a]) * f;
  out[1] = p.v[a + 1] + (p.v[b + 1] - p.v[a + 1]) * f;
  out[2] = p.v[a + 2] + (p.v[b + 2] - p.v[a + 2]) * f;
}

/** Deterministic pseudo-random 0..1 from an integer (so a particle keeps its place between frames and between renders). */
export function hash01(n: number): number {
  let x = (n | 0) + 0x6d2b79f5;
  x = Math.imul(x ^ (x >>> 15), x | 1);
  x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
  return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
}
