// Interactive-view maths for the globe: a "centre on (lon, lat), north up" camera, and the inverse projection that turns a point on
// screen back into a longitude/latitude (for drag, zoom-to-cursor, tap-to-centre and hit tests). Pure TS, client-safe.

import { fixedView, spun, type Mat } from "./camera";
import { RAD } from "./sphere";

export const MAX_LAT = 85; // north-up views stop short of the poles so "up" never flips

/** The view matrix with (lon, lat) at the centre of the disc and north up. */
export function centredView(lon: number, lat: number): Mat {
  return spun(fixedView(lat, 0), -lon * RAD);
}

/** The body-frame point sitting at the middle of the disc for matrix `m` (works for any camera, rolled or not). */
export function centreOf(m: Mat): { lon: number; lat: number } {
  return { lon: Math.atan2(m[7], m[6]) / RAD, lat: Math.asin(Math.max(-1, Math.min(1, m[8]))) / RAD };
}

/** Screen position -> geography. (nx, ny) are in units of the globe radius from the disc centre, y up. Null off the disc. */
export function unproject(m: Mat, nx: number, ny: number): { lon: number; lat: number } | null {
  const r2 = nx * nx + ny * ny;
  if (r2 > 1) return null;
  const d = Math.sqrt(1 - r2);
  // m is orthonormal, so its transpose is its inverse.
  const x = m[0] * nx + m[3] * ny + m[6] * d;
  const y = m[1] * nx + m[4] * ny + m[7] * d;
  const z = m[2] * nx + m[5] * ny + m[8] * d;
  return { lon: Math.atan2(y, x) / RAD, lat: Math.asin(Math.max(-1, Math.min(1, z))) / RAD };
}

/** Geography -> screen (unit-radius coordinates, y up) plus depth (>= 0 means on the visible side). */
export function projectPoint(m: Mat, lon: number, lat: number): { x: number; y: number; d: number } {
  const a = lon * RAD, b = lat * RAD, c = Math.cos(b);
  const vx = c * Math.cos(a), vy = c * Math.sin(a), vz = Math.sin(b);
  return {
    x: m[0] * vx + m[1] * vy + m[2] * vz,
    y: m[3] * vx + m[4] * vy + m[5] * vz,
    d: m[6] * vx + m[7] * vy + m[8] * vz,
  };
}

/** Wrap a longitude into [-180, 180). */
export const wrapLon = (lon: number): number => ((((lon + 180) % 360) + 360) % 360) - 180;
