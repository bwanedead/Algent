"use client";

// The site's loading indicator: Earth as a small line-art globe, spinning about its TRUE axis but seen from an unfamiliar angle
// (upside down, on a steep diagonal, from below the south pole ...). One angle is picked per instance from PERSPECTIVES, or set
// with the `perspective` prop (an index, or your own { elev, roll }).
//
//   - Pure SVG, our own orthographic projection (no d3). Coastlines are thin strokes in the theme's accent, a faint graticule turns
//     with the planet, the far side is drawn very faintly (or not at all when small), and a quiet limb + terminator wash gives depth.
//   - Coastline data: /geo/land-lite.json (~19 KB, built by analytics_workspace/scripts/make_land_lite.py from Natural Earth 110m),
//     fetched lazily once per page; a 330-point inline outline draws instantly meanwhile.
//   - Frames are written straight to the SVG paths from requestAnimationFrame (about 30 fps, stopped off screen), not through React.
//   - prefers-reduced-motion: one still frame. Accessible: role="status" with a label (default "Loading"), or `decorative` for none.
//   - VIEWS is the systematic set (straight, 45-degree quadrants, ecliptic with precession). `cycle` walks through it with hard cuts (no glide;
//     the equatorial plane flashes for under a second after each cut: red axis to lon 0, green to 90E); `view` pins one by id. The legacy `perspective` prop and random PERSPECTIVES pick still work.
// Client-safe: imports nothing from the server side.

import { useEffect, useId, useRef, useState } from "react";

import "./globe-spinner.css";

/** Where the camera sits: `elev` is the latitude under the viewer (90 = straight down on the north pole, -90 = from below the
 *  south pole), `roll` turns the picture in its own plane (180 = upside down). The globe always spins about its own axis. */
export type Perspective = { elev: number; roll: number };

export const PERSPECTIVES: readonly Perspective[] = [
  { elev: -72, roll: 0 }, //   from beneath the south pole
  { elev: 14, roll: 180 }, //  upside down
  { elev: 24, roll: -62 }, //  steep diagonal
  { elev: -38, roll: 128 }, // tipped over, southern sky
  { elev: 6, roll: 90 }, //    on its side: the axis runs left to right
  { elev: -52, roll: -34 }, // low and leaning
  { elev: 64, roll: 156 }, //  over the north pole, inverted
];

/** One named camera. Fixed views are (elev, roll); the ecliptic view has the camera fixed in the ecliptic frame, Earth's axis tilted
 *  23.44 degrees from the ecliptic normal and sweeping a cone (precession, stylised to one sweep per `precession` ms). */
export type ViewDef = { id: string; label: string; elev?: number; roll?: number; ecliptic?: boolean };

const quad = (hemi: "N" | "S"): ViewDef[] =>
  [0, 90, 180, 270].map((roll) => ({ id: `${hemi.toLowerCase()}45-${roll}`, label: `${hemi} 45° · ${roll}°`, elev: hemi === "N" ? 45 : -45, roll }));

// Spinning about the axis makes camera azimuth irrelevant (it only shifts which longitude faces us), so the four "azimuths" of a
// 45-degree view are four rolls of the picture: the axis leans up, left, down, right.
/** The systematic set, in a pleasing cycling order (each neighbour is a modest turn from the last). */
export const VIEWS: readonly ViewDef[] = [
  { id: "north-up", label: "North up", elev: 0, roll: 0 },
  ...quad("N"),
  { id: "above-north", label: "From above the North Pole", elev: 90, roll: 0 },
  { id: "ecliptic", label: "Ecliptic · tilt and precession", ecliptic: true },
  { id: "south-up", label: "South up", elev: 0, roll: 180 },
  ...quad("S"),
  { id: "below-south", label: "From below the South Pole", elev: -90, roll: 0 },
];

type Props = {
  /** Cycle through VIEWS with hard cuts, flashing the equatorial plane after each. */
  cycle?: boolean;
  /** Pin one of VIEWS by id (ignored when `cycle`). */
  view?: string;
  /** With `cycle`/`view`: a tiny faint caption naming the current view. */
  showLabel?: boolean;
  /** Purely decorative: aria-hidden, no status role. */
  decorative?: boolean;
  /** Milliseconds each view is held while cycling (default 30000; the ecliptic view holds longer, capped at 60 s). */
  hold?: number;
  /** Milliseconds per precession sweep in the ecliptic view (default 40000). */
  precession?: number;
  /** Pixels, clamped to 24-160. */
  size?: number;
  perspective?: number | Perspective;
  /** Accessible name (default "Loading"). */
  label?: string;
  /** Visible words under the globe; also the accessible name when given. */
  caption?: string;
  className?: string;
  /** Milliseconds per full turn. */
  period?: number;
};

// ---- data: polylines as unit vectors ------------------------------------------------------------------------------------------

type Poly = Float32Array; // x, y, z triples on the unit sphere; z is toward the north pole
const RAD = Math.PI / 180;
const STEP = 3 * RAD; // longest straight piece before a segment is subdivided along the sphere

// Inline outline (Eurasia + Africa, the Americas, Australia), tolerance 8 degrees: enough to read as Earth on the first frame.
const COARSE: number[][] = [
  [180, 69, 104, 78, 72, 66, 19, 70, 6, 59, 29, 60, 8, 57, -9, 37, 42, 42, 26, 40, 34, 31, -6, 36, -18, 15, 8, 5, 26, -34, 51, 11, 32, 30, 44, 13, 60, 22, 48, 30, 66, 25, 78, 8, 91, 23, 104, 1, 100, 13, 122, 28, 118, 39, 129, 35, 135, 55, 164, 63, 157, 51, 180, 65],
  [-123, 49, -147, 61, -165, 54, -157, 71, -94, 72, -81, 69, -92, 57, -56, 53, -80, 25, -97, 27, -82, 9, -35, -6, -68, -52, -78, 8, -112, 25, -123, 49],
  [126, -32, 115, -34, 114, -22, 132, -11, 154, -28, 146, -39, 126, -32],
];

const vec = (lon: number, lat: number): [number, number, number] => {
  const a = lon * RAD, b = lat * RAD, c = Math.cos(b);
  return [c * Math.cos(a), c * Math.sin(a), Math.sin(b)];
};

/** [lon, lat, lon, lat, ...] lines to unit-vector polylines, long segments subdivided so they bend with the sphere. */
function toPolys(lines: number[][]): Poly[] {
  return lines.map((l) => {
    const out: number[] = [];
    let prev: [number, number, number] | null = null;
    for (let i = 0; i + 1 < l.length; i += 2) {
      const v = vec(l[i], l[i + 1]);
      if (prev) {
        const ang = Math.acos(Math.min(1, Math.max(-1, prev[0] * v[0] + prev[1] * v[1] + prev[2] * v[2])));
        const n = Math.ceil(ang / STEP);
        for (let k = 1; k < n; k++) {
          const t = k / n;
          const x = prev[0] + (v[0] - prev[0]) * t, y = prev[1] + (v[1] - prev[1]) * t, z = prev[2] + (v[2] - prev[2]) * t;
          const h = Math.hypot(x, y, z) || 1;
          out.push(x / h, y / h, z / h);
        }
      }
      out.push(v[0], v[1], v[2]);
      prev = v;
    }
    return Float32Array.from(out);
  });
}

function graticule(): Poly[] {
  const lines: number[][] = [];
  for (let lat = -60; lat <= 60; lat += 30) {
    const l: number[] = [];
    for (let lon = -180; lon <= 180; lon += 10) l.push(lon, lat);
    lines.push(l);
  }
  for (let lon = -180; lon < 180; lon += 30) {
    const l: number[] = [];
    for (let lat = -90; lat <= 90; lat += 10) l.push(lon, lat);
    lines.push(l);
  }
  return toPolys(lines);
}

const GRAT = graticule();
const COARSE_POLYS = toPolys(COARSE);
let landPolys: Poly[] | null = null;
let landPending: Promise<Poly[] | null> | null = null;

/** The detailed coastline, fetched once per page; null if it cannot be had (the inline outline stays). */
function loadLand(): Promise<Poly[] | null> {
  if (landPolys) return Promise.resolve(landPolys);
  landPending ??= fetch("/geo/land-lite.json")
    .then((r) => (r.ok ? r.json() : null))
    .then((d: { lines?: number[][] } | null) => (landPolys = d?.lines?.length ? toPolys(d.lines) : null))
    .catch(() => null);
  return landPending;
}

// ---- drawing ------------------------------------------------------------------------------------------------------------------

const C = 50; // viewBox centre
const R = 44; // globe radius in viewBox units
const f1 = (v: number) => Math.round(v * 10) / 10;

/** Project every polyline with the 3x3 matrix `m` (rows: screen x, screen y, depth) and return SVG path data for the visible
 *  half and for the hidden half. Runs are cut where they cross the horizon (depth 0). */
function paths(polys: Poly[], m: number[], wantBack: boolean): { front: string; back: string } {
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

// ---- cameras: 3x3 rows (screen x, screen y, depth) acting on the polar-axis frame ---------------------------------------------

type Mat = number[];

/** Camera over latitude `elev` at lon 0, picture rolled by `roll` (before the spin is applied). */
function fixedView(elev: number, roll: number): Mat {
  const ce = Math.cos(elev * RAD), se = Math.sin(elev * RAD), cr = Math.cos(roll * RAD), sr = Math.sin(roll * RAD);
  const X = [0, 1, 0], Y = [-se, 0, ce], D = [ce, 0, se];
  return [...[0, 1, 2].map((k) => cr * X[k] - sr * Y[k]), ...[0, 1, 2].map((k) => sr * X[k] + cr * Y[k]), ...D];
}

const TILT = 23.44 * RAD; // obliquity of the ecliptic
const ECL_CAM = 24 * RAD; // how far above the ecliptic plane the camera sits, so its ring reads as an ellipse
const ECL_COS = Math.cos(ECL_CAM), ECL_SIN = Math.sin(ECL_CAM);

/** Ecliptic frame fixed on screen (x right, ecliptic normal leaning up), axis tilted TILT from the normal at azimuth `phi`. */
function eclipticView(phi: number): Mat {
  const ct = Math.cos(TILT), st = Math.sin(TILT), cp = Math.cos(phi), sp = Math.sin(phi);
  const xb = [ct * cp, ct * sp, -st], yb = [-sp, cp, 0], zb = [st * cp, st * sp, ct]; // body axes in ecliptic coordinates
  const ex = [1, 0, 0], ey = [0, ECL_SIN, -ECL_COS], ez = [0, ECL_COS, ECL_SIN]; // ecliptic axes in screen coordinates
  const toScreen = (b: number[]) => [0, 1, 2].map((r) => ex[r] * b[0] + ey[r] * b[1] + ez[r] * b[2]);
  const cx = toScreen(xb), cy = toScreen(yb), cz = toScreen(zb); // columns of the view matrix
  return [cx[0], cy[0], cz[0], cx[1], cy[1], cz[1], cx[2], cy[2], cz[2]];
}

/** Spin about the polar axis by `theta` first, then the camera `v`. */
function spun(v: Mat, theta: number): Mat {
  const c = Math.cos(theta), s = Math.sin(theta);
  const out: number[] = [];
  for (let r = 0; r < 3; r++) out.push(v[r * 3] * c + v[r * 3 + 1] * s, -v[r * 3] * s + v[r * 3 + 1] * c, v[r * 3 + 2]);
  return out;
}

const ECL_HOLD = 2.2; // the ecliptic view stays this many times longer, to show a good part of the precession
const ECL_MAX = 60000; // ...but never more than this many ms
const FLASH_MS = 900; // the equatorial-plane flash right after each cut

const viewMat = (d: ViewDef, clock: number, precession: number): Mat =>
  d.ecliptic ? eclipticView((clock / precession) * 2 * Math.PI) : fixedView(d.elev ?? 0, d.roll ?? 0);

/** Where the camera is at `clock` ms: a view matrix, how "ecliptic" it is (0 or 1, drives the ring and axis), which view's name
 *  to show, and `since` = ms since the last hard cut (Infinity when not cycling). Stateless: the whole schedule is a function of
 *  the clock, so a paused tab resumes seamlessly. Views switch instantly, with no glide. */
/** A deterministic shuffle of 0..n-1 for one pass of the cycle (mulberry32 seeded by seed + pass). */
function passOrder(n: number, seed: number, pass: number): number[] {
  let t = (seed ^ Math.imul(pass + 1, 0x9e3779b1)) >>> 0;
  const rnd = () => {
    t = (t + 0x6d2b79f5) >>> 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
  const o = Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [o[i], o[j]] = [o[j], o[i]];
  }
  return o;
}

/** Random order, every view once per pass, never the same view twice in a row across a pass boundary. */
function orderFor(n: number, seed: number, pass: number): number[] {
  const o = passOrder(n, seed, pass);
  if (pass > 0 && n > 1) {
    const prev = passOrder(n, seed, pass - 1);
    if (o[0] === prev[n - 1]) [o[0], o[1]] = [o[1], o[0]];
  }
  return o;
}

function cameraAt(views: readonly ViewDef[], clock: number, hold: number, precession: number, seed = 0): { v: Mat; ecl: number; label: number; since: number } {
  if (views.length === 1) return { v: viewMat(views[0], clock, precession), ecl: views[0].ecliptic ? 1 : 0, label: 0, since: Infinity };
  const dur = views.map((d) => (d.ecliptic ? Math.max(hold, Math.min(hold * ECL_HOLD, ECL_MAX)) : hold));
  const total = dur.reduce((a, b) => a + b, 0);
  const pass = Math.floor(clock / total);
  const order = orderFor(views.length, seed, pass);
  let p = clock - pass * total, k = 0;
  while (p >= dur[order[k]]) p -= dur[order[k++]];
  const i = order[k];
  return { v: viewMat(views[i], clock, precession), ecl: views[i].ecliptic ? 1 : 0, label: i, since: p };
}

const reduceMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const clamp = (n: number) => Math.min(160, Math.max(24, n));

// Equatorial-plane flash (body frame, so the axes turn with the planet): red towards lon 0, green towards lon 90E, plus rings and radials.
const sc = (m: number[], bx: number, by: number, r: number) => [C + R * r * (m[0] * bx + m[1] * by), C - R * r * (m[3] * bx + m[4] * by), r * (m[6] * bx + m[7] * by)];

function flashPaths(m: number[]): { front: string; back: string } {
  let front = "", back = "";
  const add = (p: number[], q: number[]) => {
    const s = `M${f1(p[0])} ${f1(p[1])}L${f1(q[0])} ${f1(q[1])}`;
    if (p[2] + q[2] >= 0) front += s; else back += s;
  };
  for (const r of [1 / 3, 2 / 3, 1]) {
    for (let k = 0; k < 72; k++) {
      const a = k * 5 * RAD, b = (k + 1) * 5 * RAD;
      add(sc(m, Math.cos(a), Math.sin(a), r), sc(m, Math.cos(b), Math.sin(b), r));
    }
  }
  for (let k = 1; k < 12; k++) {
    if (k % 3 === 0) continue; // the axes themselves are drawn separately
    const a = k * 30 * RAD;
    add(sc(m, Math.cos(a), Math.sin(a), 0), sc(m, Math.cos(a), Math.sin(a), 1));
  }
  return { front, back };
}

// Ecliptic ring: fixed in the picture (the camera is fixed in the ecliptic frame). Back half is masked where the globe covers it.
const RING = 49, RING_Y = RING * ECL_SIN;
const RING_BACK = `M${C - RING} ${C}A${RING} ${RING_Y} 0 0 1 ${C + RING} ${C}`;
const RING_FRONT = `M${C + RING} ${C}A${RING} ${RING_Y} 0 0 1 ${C - RING} ${C}`;

export default function GlobeSpinner({
  size = 64, perspective, label = "Loading", caption, className = "", period = 16000,
  cycle = false, view, showLabel = false, decorative = false, hold = 30000, precession = 40000,
}: Props) {
  const px = clamp(size);
  const id = useId();
  const [pick, setPick] = useState(0);
  const seed = useRef(Math.floor(Math.random() * 2 ** 31));   // per-mount random view order (only used in the animation loop)
  const [land, setLand] = useState<Poly[]>(COARSE_POLYS);
  const host = useRef<HTMLSpanElement>(null);
  const coast = useRef<SVGPathElement>(null);
  const far = useRef<SVGPathElement>(null);
  const grid = useRef<SVGPathElement>(null);
  const axis = useRef<SVGLineElement>(null);
  const tag = useRef<HTMLSpanElement>(null);
  const flash = useRef<SVGGElement>(null);
  const flFront = useRef<SVGPathElement>(null);
  const flBack = useRef<SVGPathElement>(null);
  const flAxes = useRef<(SVGLineElement | null)[]>([]);

  const pinned = perspective === undefined && !cycle ? VIEWS.find((v) => v.id === view) : undefined;
  const legacy = !cycle && !pinned;

  // A random legacy angle per instance, chosen after mount so server and client markup agree.
  useEffect(() => {
    if (legacy && perspective === undefined) setPick(Math.floor(Math.random() * PERSPECTIVES.length));
  }, [legacy, perspective]);

  useEffect(() => {
    let dead = false;
    if (px >= 40) void loadLand().then((p) => { if (!dead && p) setLand(p); });
    return () => { dead = true; };
  }, [px]);

  const legacyView: Perspective = typeof perspective === "object" ? perspective : PERSPECTIVES[(typeof perspective === "number" ? perspective : pick) % PERSPECTIVES.length];
  const { elev, roll } = legacyView;
  const hasEcl = cycle || !!pinned?.ecliptic;
  const labelled = showLabel && !legacy;

  useEffect(() => {
    const views: readonly ViewDef[] = cycle ? VIEWS : pinned ? [pinned] : [{ id: "legacy", label: "", elev, roll }];
    const showGrid = px >= 40, showFar = px >= 56;
    let shown = -1;
    let flashing = false;
    const paint = (clock: number, allowFlash = true) => {
      const cam = cameraAt(views, clock, hold, precession, seed.current);
      const m = spun(cam.v, 0.6 + (clock / period) * 2 * Math.PI);
      const l = paths(land, m, showFar);
      coast.current?.setAttribute("d", l.front);
      far.current?.setAttribute("d", l.back);
      if (showGrid) grid.current?.setAttribute("d", paths(GRAT, m, false).front);
      if (hasEcl) {
        host.current?.style.setProperty("--ecl", String(Math.round(cam.ecl * 100) / 100));
        const a = axis.current;
        if (a) { // the rotation axis (view matrix column 2), poking out of both poles
          const ax = cam.v[2], ay = cam.v[5], k = 1.14;
          a.setAttribute("x1", String(f1(C - R * k * ax))); a.setAttribute("y1", String(f1(C + R * k * ay)));
          a.setAttribute("x2", String(f1(C + R * k * ax))); a.setAttribute("y2", String(f1(C - R * k * ay)));
        }
      }
      const fl = flash.current;
      if (fl) {
        const k = allowFlash && cam.since < FLASH_MS ? (1 - cam.since / FLASH_MS) ** 2 : 0; // ease-out
        if (k > 0.01) {
          flashing = true;
          fl.style.display = "";
          fl.setAttribute("opacity", k.toFixed(2));
          const fp = flashPaths(m);
          flFront.current?.setAttribute("d", fp.front);
          flBack.current?.setAttribute("d", fp.back);
          flAxes.current.forEach((ln, i) => { // 0 red +, 1 green +, 2 red -, 3 green -
            if (!ln) return;
            const bx = i % 2 === 0 ? 1 : 0, by = 1 - bx, e = sc(m, bx, by, i < 2 ? 1.12 : -1.12);
            ln.setAttribute("x1", String(C)); ln.setAttribute("y1", String(C));
            ln.setAttribute("x2", String(f1(e[0]))); ln.setAttribute("y2", String(f1(e[1])));
            ln.setAttribute("opacity", e[2] >= 0 ? "1" : "0.4");
          });
        } else if (flashing) {
          flashing = false;
          fl.style.display = "none";
        }
      }
      if (tag.current && cam.label !== shown) { shown = cam.label; tag.current.textContent = views[cam.label].label; }
    };
    if (reduceMotion()) {
      paint(0, false);
      return;
    }
    let raf = 0, last = 0, clock = 0, seen = true;
    const tick = (t: number) => {
      raf = requestAnimationFrame(tick);
      if (!seen || document.hidden) { last = 0; return; } // paused: the clock does not advance, so resuming is seamless
      if (!last) { last = t; return; }
      if (t - last < 33) return;
      clock += Math.min(t - last, 100);
      last = t;
      paint(clock);
    };
    paint(0);
    raf = requestAnimationFrame(tick);
    const io = typeof IntersectionObserver !== "undefined" && host.current ? new IntersectionObserver((e) => { seen = e.some((x) => x.isIntersecting); }) : null;
    if (io && host.current) io.observe(host.current);
    return () => {
      cancelAnimationFrame(raf);
      io?.disconnect();
    };
  }, [land, cycle, pinned, elev, roll, px, period, hold, precession, hasEcl]);

  const sw = px < 48 ? 1.1 : 1; // css px, constant across sizes (non-scaling strokes)
  const a11y = decorative ? { "aria-hidden": true as const } : { role: "status", "aria-label": caption || label };
  return (
    <span ref={host} className={`globe-spinner ${caption || labelled ? "has-caption" : ""} ${className}`.trim()} {...a11y}>
      <svg width={px} height={px} viewBox="0 0 100 100" aria-hidden="true" focusable="false">
        <defs>
          <radialGradient id={`${id}-w`} cx="34%" cy="30%" r="80%">
            <stop offset="0%" className="gs-lit" stopOpacity="0.16" />
            <stop offset="60%" className="gs-lit" stopOpacity="0.04" />
            <stop offset="100%" className="gs-lit" stopOpacity="0" />
          </radialGradient>
          <radialGradient id={`${id}-l`} cx="50%" cy="50%" r="50%">
            <stop offset="86%" className="gs-limb" stopOpacity="0" />
            <stop offset="100%" className="gs-limb" stopOpacity="0.28" />
          </radialGradient>
          {hasEcl && (
            <mask id={`${id}-m`} maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100">
              <rect width="100" height="100" fill="white" />
              <circle cx={C} cy={C} r={R} fill="black" />
            </mask>
          )}
        </defs>
        {hasEcl && <path d={RING_BACK} className="gs-ecl" fill="none" strokeWidth={0.8} strokeDasharray="2 3" vectorEffect="non-scaling-stroke" mask={`url(#${id}-m)`} />}
        <circle cx={C} cy={C} r={R} fill={`url(#${id}-w)`} />
        <circle cx={C} cy={C} r={R} className="gs-ocean" />
        <path ref={grid} className="gs-grid" fill="none" strokeWidth={0.8} vectorEffect="non-scaling-stroke" />
        <path ref={far} className="gs-far" fill="none" strokeWidth={0.8} vectorEffect="non-scaling-stroke" />
        <path ref={coast} className="gs-coast" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        <circle cx={C} cy={C} r={R} fill={`url(#${id}-l)`} />
        <circle cx={C} cy={C} r={R} className="gs-rim" fill="none" strokeWidth={sw} vectorEffect="non-scaling-stroke" />
        {cycle && (
          <g ref={flash} style={{ display: "none" }} aria-hidden="true">
            <path ref={flBack} className="gs-fl-grid gs-fl-back" fill="none" strokeWidth={0.7} vectorEffect="non-scaling-stroke" />
            <path ref={flFront} className="gs-fl-grid gs-fl-front" fill="none" strokeWidth={0.7} vectorEffect="non-scaling-stroke" />
            {[0, 1, 2, 3].map((i) => (
              <line key={i} ref={(el) => { flAxes.current[i] = el; }} className={i % 2 === 0 ? "gs-fl-red" : "gs-fl-green"} strokeWidth={1.4} strokeLinecap="round" strokeDasharray={i < 2 ? undefined : "2 2.5"} vectorEffect="non-scaling-stroke" />
            ))}
          </g>
        )}
        {hasEcl && <line ref={axis} className="gs-axis" strokeWidth={0.8} strokeLinecap="round" vectorEffect="non-scaling-stroke" />}
        {hasEcl && <path d={RING_FRONT} className="gs-ecl gs-ecl-front" fill="none" strokeWidth={0.8} strokeDasharray="2 3" vectorEffect="non-scaling-stroke" />}
      </svg>
      {caption && <span className="globe-caption">{caption}</span>}
      {labelled && <span ref={tag} className="globe-view-label" aria-hidden="true" />}
    </span>
  );
}
