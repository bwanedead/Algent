"use client";

// The interference canvas: a transparent 2D canvas over the globe's SVG that draws each zone as a soft disc (our estimate, filled glow) or a ring
// (GPSJam), coloured by severity and nothing else. Zones are heat from real points, never a grid of cells. It reads the globe's camera from refs
// each frame (like components/flows/FlowLayer.tsx), redraws only when the view, size, theme or data change, and never takes a pointer event.

import { useEffect, useRef, type MutableRefObject } from "react";

import type { GnssZoneDot } from "./types";

const R_FRAC = 0.44; // globe radius as a share of the smaller canvas side (R / viewBox size in lib/globe/project.ts)
const RAD = Math.PI / 180;
const LIMB = 0.05;
// severity colours: the site's --band-* tokens, dark and paper themes
const DARK = { low: "216,182,64", medium: "224,129,58", high: "224,89,79" };
const PAPER = { low: "138,109,0", medium: "181,86,15", high: "177,38,28" };

export default function GnssLayer({ zones, on, matrix, cam }: {
  zones: GnssZoneDot[];
  on: { ours: boolean; gpsjam: boolean };
  matrix: MutableRefObject<number[]>;
  cam: MutableRefObject<{ zoom: number }>;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const live = useRef({ zones, on });
  live.current = { zones, on };

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    let w = 0, h = 0, dpr = 1, raf = 0, seen = true, lastKey = "";
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

    const frame = () => {
      raf = requestAnimationFrame(frame);
      if (!seen || document.hidden || w === 0 || h === 0) return;
      const { zones: zs, on: show } = live.current;
      const m = matrix.current, zoom = cam.current.zoom;
      const light = document.documentElement.getAttribute("data-theme") === "paper";
      const key = `${m.map((x) => x.toFixed(4)).join(",")}|${zoom.toFixed(3)}|${w}x${h}|${light}|${show.ours}${show.gpsjam}|${zs.length}`;
      if (key === lastKey) return;
      lastKey = key;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const cx = w / 2, cy = h / 2, rpx = Math.min(w, h) * R_FRAC * zoom;
      const col = light ? PAPER : DARK;
      for (const z of zs) {
        if ((z.src === "o" && !show.ours) || (z.src === "g" && !show.gpsjam)) continue;
        const la = z.lat * RAD, lo = z.lon * RAD, c = Math.cos(la);
        const x = c * Math.cos(lo), y = c * Math.sin(lo), zz = Math.sin(la);
        const depth = m[6] * x + m[7] * y + m[8] * zz;
        if (depth < LIMB) continue;
        const px = cx + rpx * (m[0] * x + m[1] * y + m[2] * zz);
        const py = cy - rpx * (m[3] * x + m[4] * y + m[5] * zz);
        const r = Math.max(z.src === "o" ? 6 : 3, z.r * RAD * rpx * (z.src === "o" ? 1.1 : 1.4));
        const rgb = col[z.s];
        if (z.src === "o") {
          const g = ctx.createRadialGradient(px, py, 0, px, py, r);
          g.addColorStop(0, `rgba(${rgb},${0.35 + 0.4 * z.share})`);
          g.addColorStop(1, `rgba(${rgb},0)`);
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(px, py, r, 0, Math.PI * 2);
          ctx.fill();
          if (z.f) { // a new or intensifying zone gets a thin ring
            ctx.strokeStyle = `rgba(${rgb},0.9)`;
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(px, py, r * 0.6, 0, Math.PI * 2);
            ctx.stroke();
          }
        } else {
          ctx.strokeStyle = `rgba(${rgb},0.85)`;
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.arc(px, py, r, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro?.disconnect(); io?.disconnect(); };
  }, [matrix, cam]);

  return <canvas ref={canvas} className="gj-canvas" aria-hidden="true" />;
}
