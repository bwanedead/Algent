// Filled land: closed rings stitched from the open coast polylines, clipped to the visible hemisphere (d3-geo clipAngle(90) + rejoin
// style). See the notes below. Pure TS, client-safe.

import { C, R, f1 } from "./project";
import { RAD, type Poly } from "./sphere";

// The coast data is a set of open polylines (the map's own seams were removed), so the fill is built from closed RINGS stitched at
// load: ends that coincide on the sphere join (lon +180 and -180 are the same point, so the antimeridian and Antarctica close
// themselves). Every ring is oriented with its land on the LEFT as seen from outside (counter-clockwise on screen); lakes are
// just more rings, and fill-rule evenodd turns them into holes. Per frame a ring is clipped against the horizon (depth 0) in the
// style of d3-geo's clipAngle(90) + rejoin: visible runs end exactly on the limb, exits are joined to the next entry going
// counter-clockwise ALONG THE LIMB ARC (never through the centre), so each path encloses land. Coast strokes use `paths` instead.
// <clip>

const TWO_PI = 2 * Math.PI;
const ARC_STEP = 7.5 * RAD; // limb arcs are sampled this finely (sagitta well under a pixel at 160 px)
const DISC = `M${C - R} ${C}A${R} ${R} 0 1 0 ${C + R} ${C}A${R} ${R} 0 1 0 ${C - R} ${C}Z`;

/** Solid angle left of the ring (mod 4pi, reduced to (-2pi, 2pi]): positive when the ring runs counter-clockwise round its small side. */
function leftArea(r: Poly): number {
  const n = r.length / 3;
  let cx = 0, cy = 0, cz = 0;
  for (let i = 0; i < r.length; i += 3) { cx += r[i]; cy += r[i + 1]; cz += r[i + 2]; }
  const h = Math.hypot(cx, cy, cz);
  if (h < 1e-6) { cx = r[0]; cy = r[1]; cz = r[2]; } else { cx /= h; cy /= h; cz /= h; }
  let s = 0;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const ax = r[i * 3], ay = r[i * 3 + 1], az = r[i * 3 + 2], bx = r[j * 3], by = r[j * 3 + 1], bz = r[j * 3 + 2];
    const triple = cx * (ay * bz - az * by) + cy * (az * bx - ax * bz) + cz * (ax * by - ay * bx);
    s += 2 * Math.atan2(triple, 1 + cx * ax + cy * ay + cz * az + ax * bx + ay * by + az * bz + bx * cx + by * cy + bz * cz);
  }
  s -= 4 * Math.PI * Math.round(s / (4 * Math.PI));
  return s;
}

/** Open polylines to closed, small-side-on-the-left rings (an unmatched chain keeps an implicit closing edge). */
export function buildRings(polys: Poly[]): Poly[] {
  const same = (a: ArrayLike<number>, ai: number, b: ArrayLike<number>, bi: number) =>
    (a[ai] - b[bi]) ** 2 + (a[ai + 1] - b[bi + 1]) ** 2 + (a[ai + 2] - b[bi + 2]) ** 2 < 1e-8;
  const used = new Array<boolean>(polys.length).fill(false);
  const out: Poly[] = [];
  for (let s = 0; s < polys.length; s++) {
    if (used[s]) continue;
    used[s] = true;
    const ch = Array.from(polys[s]);
    for (let guard = 0; guard < polys.length; guard++) {
      if (ch.length > 6 && same(ch, 0, ch, ch.length - 3)) break; // closed
      const t = ch.length - 3;
      let joined = false;
      for (let q = 0; q < polys.length && !joined; q++) {
        if (used[q]) continue;
        const p = polys[q], last = p.length - 3;
        if (same(ch, t, p, 0)) { for (let i = 3; i < p.length; i++) ch.push(p[i]); joined = true; }
        else if (same(ch, t, p, last)) { for (let i = last - 3; i >= 0; i -= 3) ch.push(p[i], p[i + 1], p[i + 2]); joined = true; }
        if (joined) used[q] = true;
      }
      if (!joined) break;
    }
    if (ch.length > 6 && same(ch, 0, ch, ch.length - 3)) ch.length -= 3; // drop the repeated closing vertex
    if (ch.length < 9) continue;
    let r = Float32Array.from(ch);
    const area = leftArea(r);
    if (Math.abs(area) < 2e-5) continue; // a speck under a third of a pixel at full size; its winding is meaningless anyway
    if (area < 0) { // wound the wrong way: reverse so the land is on the left
      const rev = new Float32Array(r.length);
      for (let i = 0, n = r.length / 3; i < n; i++) { const o = (n - 1 - i) * 3; rev[i * 3] = r[o]; rev[i * 3 + 1] = r[o + 1]; rev[i * 3 + 2] = r[o + 2]; }
      r = rev;
    }
    out.push(r);
  }
  return out;
}

// Scratch reused every frame: view-space coordinates of the ring being clipped, and its visible runs.
let sx = new Float64Array(512), sy = new Float64Array(512), sd = new Float64Array(512);
const rS: number[] = [], rE: number[] = [], rEx: number[] = [], rEy: number[] = [], rOx: number[] = [], rOy: number[] = [];
const rTa: number[] = [], rTo: number[] = [], rNext: number[] = [], rSeen: boolean[] = [], rTaken: boolean[] = [];

/** Counter-clockwise angle from limb angle `from` to `to`, in [0, 2pi); a hair short of a full turn counts as coincident. */
function limbGap(from: number, to: number): number {
  let g = (to - from) % TWO_PI;
  if (g < 0) g += TWO_PI;
  return g > TWO_PI - 1e-6 ? 0 : g;
}

/** SVG path data (evenodd) for the land inside the visible hemisphere; `m` as in `paths`. */
export function landPath(rings: Poly[], m: number[]): string {
  let out = "";
  for (const p of rings) {
    const n = p.length / 3;
    if (sx.length < n) { sx = new Float64Array(n * 2); sy = new Float64Array(n * 2); sd = new Float64Array(n * 2); }
    let nVis = 0;
    for (let i = 0; i < n; i++) {
      const vx = p[i * 3], vy = p[i * 3 + 1], vz = p[i * 3 + 2];
      sx[i] = m[0] * vx + m[1] * vy + m[2] * vz;
      sy[i] = m[3] * vx + m[4] * vy + m[5] * vz;
      sd[i] = m[6] * vx + m[7] * vy + m[8] * vz;
      if (sd[i] >= 0) nVis++;
    }
    if (nVis === n) { // wholly in view: as is (a clockwise ring has its land outside the loop: disc minus loop under evenodd)
      let a = 0;
      for (let i = 0; i < n; i++) {
        const j = i + 1 === n ? 0 : i + 1;
        a += sx[i] * sy[j] - sx[j] * sy[i];
        out += `${i ? "L" : "M"}${f1(C + R * sx[i])} ${f1(C - R * sy[i])}`;
      }
      out += a < -0.02 ? `Z${DISC}` : "Z"; // (a slim ring hugging the limb is foreshortened to a sliver whose sign is noise)
    } else if (nVis === 0) { // wholly behind: nothing, unless the ring circles the view axis land-side-in (land covers the whole visible half)
      let wind = 0, near = false;
      for (let i = 0; i < n; i++) {
        const j = (i + 1) % n;
        if (sx[i] * sx[i] + sy[i] * sy[i] < 1e-4) near = true; // through the back pole the azimuth is meaningless
        wind += Math.atan2(sx[i] * sy[j] - sy[i] * sx[j], sx[i] * sx[j] + sy[i] * sy[j]);
      }
      if (wind > Math.PI && !near) out += DISC;
    } else {
      out += clippedRing(n);
    }
  }
  return out;
}

const PT: number[] = [0, 0];
/** Where arc a->b (vertices of the ring in sx/sy/sd, one in view, one not) meets depth 0: a point on the unit circle, into PT. */
function crossing(a: number, b: number): void {
  const t = sd[a] / (sd[a] - sd[b]);
  const x = sx[a] + (sx[b] - sx[a]) * t, y = sy[a] + (sy[b] - sy[a]) * t, h = Math.hypot(x, y) || 1;
  PT[0] = x / h; PT[1] = y / h;
}

/** The ring in sx/sy/sd (some vertices in view, some not): cut into runs at the exact horizon crossings, rejoin along the limb. */
function clippedRing(n: number): string {
  let i0 = 0;
  while (!(sd[i0] >= 0 && sd[(i0 + n - 1) % n] < 0)) i0++;
  const pt: number[] = [0, 0];
  let nr = 0;
  for (let i = i0; i < i0 + n;) {
    let e = i;
    while (sd[(e + 1) % n] >= 0) e++;
    crossing((i + n - 1) % n, i % n); rEx[nr] = PT[0]; rEy[nr] = PT[1];
    crossing(e % n, (e + 1) % n); rOx[nr] = PT[0]; rOy[nr] = PT[1];
    rS[nr] = i; rE[nr] = e; rTa[nr] = Math.atan2(rEy[nr], rEx[nr]); rTo[nr] = Math.atan2(rOy[nr], rOx[nr]); rSeen[nr] = false;
    nr++;
    i = e + 1;
    while (sd[i % n] < 0) i++;
  }
  // After an exit, the next entry counter-clockwise round the limb. Matched smallest gap first and one-to-one, so a grazing run
  // (exit and re-entry at the same limb point) still pairs up correctly instead of two exits claiming one entry.
  for (let r = 0; r < nr; r++) { rNext[r] = -1; rTaken[r] = false; }
  for (let left = nr; left > 0; left--) {
    let best = Infinity, br = 0, bq = 0;
    for (let r = 0; r < nr; r++) {
      if (rNext[r] >= 0) continue;
      for (let q = 0; q < nr; q++) {
        if (rTaken[q]) continue;
        const g = limbGap(rTo[r], rTa[q]);
        if (g < best) { best = g; br = r; bq = q; }
      }
    }
    rNext[br] = bq; rTaken[bq] = true;
  }
  let out = "";
  for (let r0 = 0; r0 < nr; r0++) {
    if (rSeen[r0]) continue;
    let r = r0;
    out += `M${f1(C + R * rEx[r])} ${f1(C - R * rEy[r])}`;
    while (!rSeen[r]) {
      rSeen[r] = true;
      for (let k = rS[r]; k <= rE[r]; k++) out += `L${f1(C + R * sx[k % n])} ${f1(C - R * sy[k % n])}`;
      out += `L${f1(C + R * rOx[r])} ${f1(C - R * rOy[r])}`;
      const q = rNext[r];
      const g = limbGap(rTo[r], rTa[q]);
      const steps = Math.ceil(g / ARC_STEP);
      for (let k = 1; k < steps; k++) {
        const a = rTo[r] + (g * k) / steps;
        out += `L${f1(C + R * Math.cos(a))} ${f1(C - R * Math.sin(a))}`;
      }
      out += `L${f1(C + R * rEx[q])} ${f1(C - R * rEy[q])}`;
      r = q;
    }
    out += "Z";
  }
  return out;
}
// </clip>
