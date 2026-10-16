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

import { useEffect, useId, useMemo, useRef, useState } from "react";

import { buildRings, landPath } from "@/lib/globe/clip";
import { cameraAt, ECL_SIN, VIEWS, PERSPECTIVES, type Perspective, type ViewDef } from "@/lib/globe/camera";
import { f1, paths, C, R } from "@/lib/globe/project";
import { COARSE_POLYS, GRAT, loadLand, RAD, type Poly } from "@/lib/globe/sphere";

import "./globe-spinner.css";

// Geometry, projection, ring clipping and the camera/view model live in lib/globe/ (shared with the full-screen viewer).

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


const FLASH_MS = 900; // the equatorial-plane flash right after each cut
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
  const rings = useMemo(() => buildRings(land), [land]);
  const host = useRef<HTMLSpanElement>(null);
  const fill = useRef<SVGPathElement>(null);
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
      fill.current?.setAttribute("d", landPath(rings, m));
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
  }, [land, rings, cycle, pinned, elev, roll, px, period, hold, precession, hasEcl]);

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
        <path ref={fill} className="gs-land" fillRule="evenodd" stroke="none" />
        <path ref={coast} className="gs-coast" fill="none" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
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
