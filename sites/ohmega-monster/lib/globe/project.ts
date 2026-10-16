// Orthographic projection into the 100x100 viewBox: polylines to SVG path data split at the horizon. Pure TS, client-safe.

import type { Poly } from "./sphere";

export const C = 50; // viewBox centre
export const R = 44; // globe radius in viewBox units
export const f1 = (v: number) => Math.round(v * 10) / 10;

/** Project every polyline with the 3x3 matrix `m` (rows: screen x, screen y, depth) and return SVG path data for the visible
 *  half and for the hidden half. Runs are cut where they cross the horizon (depth 0). */
export function paths(polys: Poly[], m: number[], wantBack: boolean): { front: string; back: string } {
  let front = "", back = "";
  for (const p of polys) {
    let px = 0, py = 0, pd = 0;
    let fOpen = false, bOpen = false;
    for (let i = 0; i + 2 < p.length; i += 3) {
      const vx = p[i], vy = p[i + 1], vz = p[i + 2];
      const x = m[0] * vx + m[1] * vy + m[2] * vz;
      const y = m[3] * vx + m[4] * vy + m[5] * vz;
      const d = m[6] * vx + m[7] * vy + m[8] * vz;
      if (i === 0) {
        px = x; py = y; pd = d;
        continue;
      }
      let ax = px, ay = py; // start of the piece being added
      if (pd >= 0 !== d >= 0) {
        // crosses the limb: finish the previous side at the horizon, start the other from there
        const t = pd / (pd - d);
        let hx = px + (x - px) * t, hy = py + (y - py) * t;
        const h = Math.hypot(hx, hy) || 1;
        hx /= h; hy /= h;
        if (pd >= 0) { front += `${fOpen ? "" : `M${f1(C + R * ax)} ${f1(C - R * ay)}`}L${f1(C + R * hx)} ${f1(C - R * hy)}`; fOpen = false; }
        else if (wantBack) { back += `${bOpen ? "" : `M${f1(C + R * ax)} ${f1(C - R * ay)}`}L${f1(C + R * hx)} ${f1(C - R * hy)}`; bOpen = false; }
        ax = hx; ay = hy;
      }
      if (d >= 0) {
        front += `${fOpen ? "" : `M${f1(C + R * ax)} ${f1(C - R * ay)}`}L${f1(C + R * x)} ${f1(C - R * y)}`;
        fOpen = true; bOpen = false;
      } else if (wantBack) {
        back += `${bOpen ? "" : `M${f1(C + R * ax)} ${f1(C - R * ay)}`}L${f1(C + R * x)} ${f1(C - R * y)}`;
        bOpen = true; fOpen = false;
      } else {
        fOpen = false;
      }
      px = x; py = y; pd = d;
    }
  }
  return { front, back };
}
