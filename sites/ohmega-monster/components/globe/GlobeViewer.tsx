"use client";

// The full-screen interactive globe (/globe). The same line-art Earth as the loading spinner, but yours to drive:
//   - Drag to rotate (with inertia). Wheel or pinch to zoom, which also leans toward what is under the cursor, down to a regional
//     top-down view. Double-click / double-tap centres on a spot (and steps in). Arrow keys rotate, + and - zoom.
//   - Two modes. "Cycle" walks the spinner's view set (lib/globe/camera.ts VIEWS) with hard cuts, slowly. "Still" is a north-up globe
//     centred where you left it. Any drag, click, wheel or key press cancels Cycle and keeps the point it was looking at.
//   - Reduced motion: starts Still, no inertia, no easing. Pauses when the tab is hidden or the globe is off screen.
// Frames are written straight to SVG paths from requestAnimationFrame, not through React (as in GlobeSpinner).
// Geometry, projection, clipping and cameras all come from lib/globe/ (pure, client-safe).

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { cameraAt, spun, VIEWS } from "@/lib/globe/camera";
import { buildRings, landPath } from "@/lib/globe/clip";
import { C, paths, R } from "@/lib/globe/project";
import { COARSE_POLYS, GRAT, loadLand, type Poly } from "@/lib/globe/sphere";
import { centreOf, centredView, MAX_LAT, unproject, wrapLon } from "@/lib/globe/view";

import "../globe-spinner.css";
import "./globe-viewer.css";

type Mode = "cycle" | "still";

const MIN_ZOOM = 1;
const MAX_ZOOM = 8;
const CYCLE_HOLD = 30000; // ms per view while cycling
const CYCLE_SPIN = 60000; // ms per full turn while cycling (the spinner does 16 s)
const TAP_SLOP = 6; // px a press may wander and still be a tap
const DOUBLE_TAP_MS = 320;

const clampZoom = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));
const clampLat = (l: number) => Math.min(MAX_LAT, Math.max(-MAX_LAT, l));
const reduceMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

type Camera = { lon: number; lat: number; zoom: number };
type Goto = { lon: number; lat: number; zoom: number };

export default function GlobeViewer() {
  const id = useId();
  const [mode, setModeState] = useState<Mode>("cycle");
  const [land, setLand] = useState<Poly[]>(COARSE_POLYS);
  const rings = useMemo(() => buildRings(land), [land]);

  const box = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const world = useRef<SVGGElement>(null);
  const fill = useRef<SVGPathElement>(null);
  const coast = useRef<SVGPathElement>(null);
  const far = useRef<SVGPathElement>(null);
  const grid = useRef<SVGPathElement>(null);
  const tag = useRef<HTMLSpanElement>(null);

  // All per-frame state lives in refs; React only hears about the mode.
  const modeRef = useRef<Mode>("cycle");
  const cam = useRef<Camera>({ lon: 20, lat: 25, zoom: 1 });
  const target = useRef<Goto | null>(null);
  const vel = useRef({ lon: 0, lat: 0 }); // degrees per ms, from the last drag
  const clock = useRef(0);
  const seed = useRef(Math.floor(Math.random() * 2 ** 31));
  const dirty = useRef(true);
  const shownLabel = useRef(-1);
  const matrix = useRef<number[]>(centredView(20, 25)); // the matrix of the last painted frame

  const setMode = useCallback((next: Mode) => {
    if (modeRef.current === next) return;
    if (next === "still") {
      // Keep looking at whatever the cycle was centred on; the picture snaps north-up.
      const c = centreOf(matrix.current);
      cam.current.lon = c.lon;
      cam.current.lat = clampLat(c.lat);
    } else {
      cam.current.zoom = 1;
      target.current = null;
      vel.current = { lon: 0, lat: 0 };
    }
    modeRef.current = next;
    setModeState(next);
    dirty.current = true;
  }, []);

  useEffect(() => {
    let dead = false;
    void loadLand().then((p) => { if (!dead && p) { setLand(p); dirty.current = true; } });
    return () => { dead = true; };
  }, []);

  // Start Still for readers who asked for less motion.
  useEffect(() => {
    if (reduceMotion()) setMode("still");
  }, [setMode]);

  // ---- the frame loop ---------------------------------------------------------------------------------------------------------
  useEffect(() => {
    const calm = reduceMotion();
    const paint = () => {
      const c = cam.current;
      let m: number[];
      if (modeRef.current === "cycle") {
        const k = cameraAt(VIEWS, clock.current, CYCLE_HOLD, 40000, seed.current);
        m = spun(k.v, 0.6 + (clock.current / CYCLE_SPIN) * 2 * Math.PI);
        if (tag.current && k.label !== shownLabel.current) { shownLabel.current = k.label; tag.current.textContent = VIEWS[k.label].label; }
      } else {
        m = centredView(c.lon, c.lat);
        if (tag.current && shownLabel.current !== -2) { shownLabel.current = -2; tag.current.textContent = ""; }
      }
      matrix.current = m;
      world.current?.setAttribute("transform", c.zoom === 1 ? "" : `translate(${C} ${C}) scale(${c.zoom}) translate(${-C} ${-C})`);
      const l = paths(land, m, true);
      fill.current?.setAttribute("d", landPath(rings, m));
      coast.current?.setAttribute("d", l.front);
      far.current?.setAttribute("d", l.back);
      grid.current?.setAttribute("d", paths(GRAT, m, false).front);
    };

    let raf = 0, last = 0, seen = true;
    const tick = (t: number) => {
      raf = requestAnimationFrame(tick);
      if (!seen || document.hidden) { last = 0; return; }
      if (!last) { last = t; return; }
      const dt = Math.min(t - last, 100);
      if (dt < 16) return;
      last = t;
      const c = cam.current;
      if (modeRef.current === "cycle") {
        if (!calm) { clock.current += dt; dirty.current = true; }
      } else {
        const g = target.current;
        if (g) { // ease toward a double-tap / zoom-to-cursor destination
          const a = calm ? 1 : 1 - Math.exp(-dt / 140);
          c.lon = wrapLon(c.lon + wrapLon(g.lon - c.lon) * a);
          c.lat += (g.lat - c.lat) * a;
          c.zoom += (g.zoom - c.zoom) * a;
          if (Math.abs(g.lat - c.lat) < 0.02 && Math.abs(wrapLon(g.lon - c.lon)) < 0.02 && Math.abs(g.zoom - c.zoom) < 0.002) { c.lon = g.lon; c.lat = g.lat; c.zoom = g.zoom; target.current = null; }
          dirty.current = true;
        }
        const v = vel.current;
        if (v.lon || v.lat) { // inertia after a flick
          c.lon = wrapLon(c.lon + v.lon * dt);
          c.lat = clampLat(c.lat + v.lat * dt);
          const decay = Math.exp(-dt / 320);
          v.lon *= decay; v.lat *= decay;
          if (Math.abs(v.lon) < 1e-4 && Math.abs(v.lat) < 1e-4) { v.lon = 0; v.lat = 0; }
          dirty.current = true;
        }
      }
      if (dirty.current) { dirty.current = false; paint(); }
    };
    paint();
    raf = requestAnimationFrame(tick);
    const io = typeof IntersectionObserver !== "undefined" && box.current ? new IntersectionObserver((e) => { seen = e.some((x) => x.isIntersecting); }) : null;
    if (io && box.current) io.observe(box.current);
    return () => { cancelAnimationFrame(raf); io?.disconnect(); };
  }, [land, rings]);

  // ---- input ------------------------------------------------------------------------------------------------------------------
  /** Pointer position -> unit-globe coordinates (radius 1, y up) for the current zoom. */
  const toGlobe = useCallback((clientX: number, clientY: number) => {
    const r = svg.current?.getBoundingClientRect();
    if (!r) return { nx: 0, ny: 0, rpx: 1 };
    const rpx = (Math.min(r.width, r.height) * R * cam.current.zoom) / 100;
    return { nx: (clientX - (r.left + r.width / 2)) / rpx, ny: -(clientY - (r.top + r.height / 2)) / rpx, rpx };
  }, []);

  const rotateBy = useCallback((dLon: number, dLat: number) => {
    cam.current.lon = wrapLon(cam.current.lon + dLon);
    cam.current.lat = clampLat(cam.current.lat + dLat);
    dirty.current = true;
  }, []);

  const zoomBy = useCallback((factor: number, atX?: number, atY?: number) => {
    setMode("still");
    target.current = null;
    const c = cam.current;
    const next = clampZoom(c.zoom * factor);
    if (next > c.zoom && atX !== undefined && atY !== undefined) { // zooming in leans toward the point under the cursor
      const g = toGlobe(atX, atY);
      const p = unproject(matrix.current, g.nx, g.ny);
      if (p) {
        const f = Math.min(0.35, (next / c.zoom - 1) * 0.6);
        c.lon = wrapLon(c.lon + wrapLon(p.lon - c.lon) * f);
        c.lat = clampLat(c.lat + (p.lat - c.lat) * f);
      }
    }
    c.zoom = next;
    dirty.current = true;
  }, [setMode, toGlobe]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const pointers = new Map<number, { x: number; y: number }>();
    let pinch = 0;
    let down: { x: number; y: number; t: number; moved: number } | null = null;
    let lastMove = 0;
    let lastTap: { x: number; y: number; t: number } | null = null;

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      zoomBy(Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0016)), e.clientX, e.clientY);
    };
    const onDown = (e: PointerEvent) => {
      if ((e.target as Element).closest(".gv-controls")) return;
      el.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      setMode("still");
      target.current = null;
      vel.current = { lon: 0, lat: 0 };
      if (pointers.size === 1) down = { x: e.clientX, y: e.clientY, t: performance.now(), moved: 0 };
      else { down = null; const [a, b] = [...pointers.values()]; pinch = Math.hypot(a.x - b.x, a.y - b.y); }
    };
    const onMove = (e: PointerEvent) => {
      const p = pointers.get(e.pointerId);
      if (!p) return;
      const dx = e.clientX - p.x, dy = e.clientY - p.y;
      p.x = e.clientX; p.y = e.clientY;
      if (pointers.size >= 2) {
        const [a, b] = [...pointers.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinch > 0 && d > 0) zoomBy(d / pinch, (a.x + b.x) / 2, (a.y + b.y) / 2);
        pinch = d;
        return;
      }
      if (!down) return;
      down.moved += Math.abs(dx) + Math.abs(dy);
      if (down.moved <= TAP_SLOP) return;
      const c = cam.current;
      const { rpx } = toGlobe(e.clientX, e.clientY);
      const dpp = 180 / Math.PI / rpx; // degrees of arc per pixel at the disc centre
      const dLon = -dx * dpp / Math.max(0.15, Math.cos(c.lat * Math.PI / 180));
      const dLat = dy * dpp;
      rotateBy(dLon, dLat);
      const now = performance.now(), dt = Math.max(1, now - lastMove);
      if (lastMove) {
        vel.current.lon = vel.current.lon * 0.5 + (dLon / dt) * 0.5;
        vel.current.lat = vel.current.lat * 0.5 + (dLat / dt) * 0.5;
      }
      lastMove = now;
    };
    const onUp = (e: PointerEvent) => {
      if (!pointers.delete(e.pointerId)) return;
      pinch = 0;
      const now = performance.now();
      const d = down;
      down = null;
      if (!d) { vel.current = { lon: 0, lat: 0 }; return; }
      if (d.moved <= TAP_SLOP && now - d.t < 500) { // a tap
        vel.current = { lon: 0, lat: 0 };
        if (lastTap && now - lastTap.t < DOUBLE_TAP_MS && Math.hypot(e.clientX - lastTap.x, e.clientY - lastTap.y) < 28) {
          lastTap = null;
          const { nx, ny } = toGlobe(e.clientX, e.clientY);
          const p = unproject(matrix.current, nx, ny);
          if (p) { const c = cam.current; target.current = { lon: p.lon, lat: clampLat(p.lat), zoom: clampZoom(Math.max(c.zoom * 1.7, 2)) }; }
        } else {
          lastTap = { x: e.clientX, y: e.clientY, t: now };
        }
        return;
      }
      if (reduceMotion() || now - lastMove > 90) vel.current = { lon: 0, lat: 0 }; // a held-still release does not coast
      lastMove = 0;
    };
    const onKey = (e: KeyboardEvent) => {
      const step = 12 / cam.current.zoom;
      const keys: Record<string, () => void> = {
        ArrowLeft: () => rotateBy(-step, 0), ArrowRight: () => rotateBy(step, 0), ArrowUp: () => rotateBy(0, step), ArrowDown: () => rotateBy(0, -step),
        "+": () => zoomBy(1.4), "=": () => zoomBy(1.4), "-": () => zoomBy(1 / 1.4), _: () => zoomBy(1 / 1.4),
      };
      const act = keys[e.key];
      if (!act) return;
      e.preventDefault();
      setMode("still");
      act();
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointercancel", onUp);
    el.addEventListener("keydown", onKey);
    return () => {
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointercancel", onUp);
      el.removeEventListener("keydown", onKey);
    };
  }, [rotateBy, setMode, toGlobe, zoomBy]);

  const toggleFullscreen = useCallback(() => {
    const el = box.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen?.();
  }, []);

  return (
    <div ref={box} className="gv" tabIndex={0} role="application" aria-label="Interactive globe. Drag to rotate, scroll or pinch to zoom, double-click to centre. Arrow keys rotate; plus and minus zoom.">
      <svg ref={svg} className="gv-svg" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">
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
        <g ref={world}>
          <circle cx={C} cy={C} r={R} fill={`url(#${id}-w)`} />
          <circle cx={C} cy={C} r={R} className="gs-ocean" />
          <path ref={grid} className="gs-grid" fill="none" strokeWidth={0.8} vectorEffect="non-scaling-stroke" />
          <path ref={far} className="gs-far" fill="none" strokeWidth={0.8} vectorEffect="non-scaling-stroke" />
          <path ref={fill} className="gs-land" fillRule="evenodd" stroke="none" />
          <path ref={coast} className="gs-coast" fill="none" strokeWidth={1} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          <circle cx={C} cy={C} r={R} fill={`url(#${id}-l)`} />
          <circle cx={C} cy={C} r={R} className="gs-rim" fill="none" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        </g>
      </svg>
      <span ref={tag} className="gv-view-label" aria-hidden="true" />
      <div className="gv-controls" role="group" aria-label="Globe controls">
        <div className="gv-seg" role="group" aria-label="Mode">
          <button type="button" className={mode === "cycle" ? "is-on" : ""} aria-pressed={mode === "cycle"} onClick={() => setMode("cycle")}>Cycle</button>
          <button type="button" className={mode === "still" ? "is-on" : ""} aria-pressed={mode === "still"} onClick={() => setMode("still")}>Still</button>
        </div>
        <div className="gv-seg">
          <button type="button" aria-label="Zoom in" onClick={() => zoomBy(1.5)}>+</button>
          <button type="button" aria-label="Zoom out" onClick={() => zoomBy(1 / 1.5)}>&minus;</button>
          <button type="button" aria-label="Toggle full screen" onClick={toggleFullscreen}>Full</button>
        </div>
      </div>
      <p className="gv-hint" aria-hidden="true">Drag to turn · scroll to zoom · double-click to centre</p>
    </div>
  );
}
