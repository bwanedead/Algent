"use client";

// The flow canvas: a transparent 2D canvas laid over the globe's SVG that draws ship lanes, dots and trade arcs (paint.ts) with the
// globe's own camera. It reads the camera from refs every frame (GlobeViewer writes them, nothing re-renders), so it follows drags,
// zoom and the cycling views exactly. It pauses when the tab is hidden or the globe is off screen, honours prefers-reduced-motion
// (one static frame, redrawn only when the view, size, layers or data change) and never takes a pointer event: the globe underneath
// keeps every gesture.

import { useEffect, useRef, type MutableRefObject } from "react";

import { paintFlows } from "./paint";
import type { Scene } from "./scene";
import type { LayerId } from "./types";

const R_FRAC = 0.44; // globe radius as a share of the smaller canvas side (R / viewBox size in lib/globe/project.ts)

export default function FlowLayer({ scene, on, matrix, cam }: {
  scene: Scene;
  on: ReadonlySet<LayerId>;
  /** The globe's 3x3 view matrix of the last painted frame (GlobeViewer `matrix`). */
  matrix: MutableRefObject<number[]>;
  /** The globe's camera; only `zoom` is read. */
  cam: MutableRefObject<{ zoom: number }>;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const live = useRef({ scene, on });
  live.current = { scene, on };
  const sceneSeen = useRef<Scene | null>(null);
  const sceneId = useRef(0);

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const calm = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, dpr = 1, raf = 0, seen = true, lastKey = "";
    const t0 = performance.now();
    const fit = () => {
      const r = el.getBoundingClientRect();
      w = r.width; h = r.height;
      dpr = Math.min(2, window.devicePixelRatio || 1);
      el.width = Math.max(1, Math.round(w * dpr));
      el.height = Math.max(1, Math.round(h * dpr));
      lastKey = "";
    };
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(fit) : null;
    ro?.observe(el);
    fit();
    const io = typeof IntersectionObserver !== "undefined" ? new IntersectionObserver((e) => { seen = e.some((x) => x.isIntersecting); }) : null;
    io?.observe(el);

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      if (!seen || document.hidden || w === 0 || h === 0) return;
      const { scene: sc, on: layers } = live.current;
      const m = matrix.current, zoom = cam.current.zoom;
      const light = document.documentElement.getAttribute("data-theme") === "paper";
      if (calm) {
        if (sceneSeen.current !== sc) { sceneSeen.current = sc; sceneId.current++; }
        const key = `${m.map((x) => x.toFixed(4)).join(",")}|${zoom.toFixed(3)}|${w}x${h}|${[...layers].join("+")}|${sceneId.current}|${light}`;
        if (key === lastKey) return;
        lastKey = key;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      if (layers.size === 0) return;
      ctx.save();
      paintFlows(ctx, sc, layers, { m, cx: w / 2, cy: h / 2, rpx: Math.min(w, h) * R_FRAC * zoom, zoom, t: (now - t0) / 1000, light, calm }, { w, h });
      ctx.restore();
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro?.disconnect(); io?.disconnect(); };
  }, [matrix, cam]);

  return <canvas ref={canvas} className="fl-canvas" aria-hidden="true" />;
}
