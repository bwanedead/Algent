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
//   - prefers-reduced-motion: one still frame. Accessible: role="status" with a label (default "Loading").
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

type Props = {
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

/** Rows for: spin about the polar axis by `theta`, look from latitude `elev` over lon 0, then roll the picture by `roll`. */
function matrix(theta: number, elev: number, roll: number): number[] {
  const ct = Math.cos(theta), st = Math.sin(theta);
  const ce = Math.cos(elev * RAD), se = Math.sin(elev * RAD);
  const cr = Math.cos(roll * RAD), sr = Math.sin(roll * RAD);
  // after the spin: v' = (ct*vx - st*vy, st*vx + ct*vy, vz); screen x = v'.y, y = -se*v'.x + ce*v'.z, depth = ce*v'.x + se*v'.z
  const X = [st, ct, 0];
  const Y = [-se * ct, se * st, ce];
  const D = [ce * ct, -ce * st, se];
  const row = (a: number, b: number) => [0, 1, 2].map((k) => a * X[k] + b * Y[k]);
  return [...row(cr, -sr), ...row(sr, cr), ...D];
}

const reduceMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const clamp = (n: number) => Math.min(160, Math.max(24, n));

export default function GlobeSpinner({ size = 64, perspective, label = "Loading", caption, className = "", period = 16000 }: Props) {
  const px = clamp(size);
  const id = useId();
  const [pick, setPick] = useState(0);
  const [land, setLand] = useState<Poly[]>(COARSE_POLYS);
  const host = useRef<HTMLSpanElement>(null);
  const coast = useRef<SVGPathElement>(null);
  const far = useRef<SVGPathElement>(null);
  const grid = useRef<SVGPathElement>(null);

  // A random angle per instance, chosen after mount so server and client markup agree.
  useEffect(() => {
    if (perspective === undefined) setPick(Math.floor(Math.random() * PERSPECTIVES.length));
  }, [perspective]);

  useEffect(() => {
    let dead = false;
    if (px >= 40) void loadLand().then((p) => { if (!dead && p) setLand(p); });
    return () => { dead = true; };
  }, [px]);

  const view: Perspective = typeof perspective === "object" ? perspective : PERSPECTIVES[(typeof perspective === "number" ? perspective : pick) % PERSPECTIVES.length];
  const { elev, roll } = view;

  useEffect(() => {
    const showGrid = px >= 40, showFar = px >= 56;
    const paint = (theta: number) => {
      const m = matrix(theta, elev, roll);
      const l = paths(land, m, showFar);
      coast.current?.setAttribute("d", l.front);
      far.current?.setAttribute("d", l.back);
      if (showGrid) grid.current?.setAttribute("d", paths(GRAT, m, false).front);
    };
    const theta0 = 0.6;
    if (reduceMotion()) {
      paint(theta0);
      return;
    }
    let raf = 0, last = 0, on = true;
    const t0 = performance.now();
    const tick = (t: number) => {
      raf = requestAnimationFrame(tick);
      if (!on || t - last < 33) return;
      last = t;
      paint(theta0 + ((t - t0) / period) * 2 * Math.PI);
    };
    paint(theta0);
    raf = requestAnimationFrame(tick);
    const io = typeof IntersectionObserver !== "undefined" && host.current ? new IntersectionObserver((e) => { on = e.some((x) => x.isIntersecting); }) : null;
    if (io && host.current) io.observe(host.current);
    return () => {
      cancelAnimationFrame(raf);
      io?.disconnect();
    };
  }, [land, elev, roll, px, period]);

  const sw = px < 48 ? 1.1 : 1; // css px, constant across sizes (non-scaling strokes)
  return (
    <span ref={host} className={`globe-spinner ${caption ? "has-caption" : ""} ${className}`.trim()} role="status" aria-label={caption || label}>
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
        </defs>
        <circle cx={C} cy={C} r={R} fill={`url(#${id}-w)`} />
        <path ref={grid} className="gs-grid" fill="none" strokeWidth={0.8} vectorEffect="non-scaling-stroke" />
        <path ref={far} className="gs-far" fill="none" strokeWidth={0.8} vectorEffect="non-scaling-stroke" />
        <path ref={coast} className="gs-coast" fill="none" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        <circle cx={C} cy={C} r={R} fill={`url(#${id}-l)`} />
        <circle cx={C} cy={C} r={R} className="gs-rim" fill="none" strokeWidth={sw} vectorEffect="non-scaling-stroke" />
      </svg>
      {caption && <span className="globe-caption">{caption}</span>}
    </span>
  );
}
