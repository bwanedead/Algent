// One frame of the flow layer on a 2D canvas. No React, no allocation per dot: the globe's 3x3 view matrix projects every unit vector,
// the far side of the globe is skipped, and labels avoid each other. What is drawn, back to front:
//   1. ship lanes: thin lines that breathe (faster the busier the lane), coloured by the strongest visible class;
//   2. ship dots: one dot per (thinned) ship, travelling along its lane in the direction the ships go, one hue per class;
//   3. trade arcs (grain, money): wide translucent arcs lifted off the globe with slowly moving dashes and an arrowhead;
//   4. place marks: chokepoints (always), and a pulsing ring on any place outside its own normal;
//   5. labels: chokepoints, the busiest lanes, the largest arcs.

import { pointAt, type Path, type Vec } from "./geometry";
import type { Scene, ShipLane } from "./scene";
import { ANOMALY, colorOf, SHIP_IDS } from "./style";
import type { LayerId, ShipId } from "./types";

export type View = {
  /** The globe's 3x3 matrix (rows: screen x, screen y, depth). */
  m: number[];
  /** Disc centre in CSS pixels and radius at the current zoom. */
  cx: number;
  cy: number;
  rpx: number;
  zoom: number;
  /** Seconds of animation clock. */
  t: number;
  light: boolean;
  /** Reduced motion: dots stand still, nothing breathes. */
  calm: boolean;
};

const TAU = Math.PI * 2;
const LIMB = 0.04; // depth under which a point counts as on the far side / on the rim

let sx = new Float32Array(512), sy = new Float32Array(512), sd = new Float32Array(512);
let dxs = new Float32Array(1024), dys = new Float32Array(1024); // the visible dots of one group
const grow = (n: number) => {
  if (sx.length >= n) return;
  sx = new Float32Array(n * 2); sy = new Float32Array(n * 2); sd = new Float32Array(n * 2);
};

/** Project a whole path into the scratch arrays. */
function projectPath(p: Path, v: View): void {
  grow(p.n);
  const { m, cx, cy, rpx } = v;
  for (let i = 0; i < p.n; i++) {
    const x = p.v[i * 3], y = p.v[i * 3 + 1], z = p.v[i * 3 + 2];
    sx[i] = cx + rpx * (m[0] * x + m[1] * y + m[2] * z);
    sy[i] = cy - rpx * (m[3] * x + m[4] * y + m[5] * z);
    sd[i] = (m[6] * x + m[7] * y + m[8] * z) / Math.hypot(x, y, z); // depth of the direction, so a lifted arc is judged by where it stands
  }
}

/** Stroke the projected scratch path, breaking it where it goes behind the globe. */
function strokeScratch(ctx: CanvasRenderingContext2D, n: number): void {
  ctx.beginPath();
  let open = false;
  for (let i = 0; i < n; i++) {
    if (sd[i] < LIMB) { open = false; continue; }
    if (open) ctx.lineTo(sx[i], sy[i]); else { ctx.moveTo(sx[i], sy[i]); open = true; }
  }
  ctx.stroke();
}

const tmp: Vec = [0, 0, 0];

function screenOf(v: View, p: Path, s: number): { x: number; y: number; d: number } {
  pointAt(p, s, tmp);
  const { m } = v;
  return {
    x: v.cx + v.rpx * (m[0] * tmp[0] + m[1] * tmp[1] + m[2] * tmp[2]),
    y: v.cy - v.rpx * (m[3] * tmp[0] + m[4] * tmp[1] + m[5] * tmp[2]),
    d: (m[6] * tmp[0] + m[7] * tmp[1] + m[8] * tmp[2]) / Math.hypot(tmp[0], tmp[1], tmp[2]),
  };
}

type Box = { x0: number; y0: number; x1: number; y1: number };

class Labels {
  private placed: Box[] = [];
  private widths = new Map<string, number>();
  constructor(private ctx: CanvasRenderingContext2D, private bg: string, private size: number) {
    ctx.font = `${size}px system-ui, -apple-system, "Segoe UI", sans-serif`;
  }
  /** Draw `text` beside (x, y) unless it would sit on a label already drawn or leave the canvas. Returns whether it was drawn. */
  put(text: string, x: number, y: number, color: string, bounds: { w: number; h: number }, dx = 6, dy = 0): boolean {
    let w = this.widths.get(text);
    if (w === undefined) { w = this.ctx.measureText(text).width; this.widths.set(text, w); }
    const left = x + dx + w > bounds.w - 4 ? x - dx - w : x + dx;
    const box = { x0: left - 2, y0: y + dy - this.size, x1: left + w + 2, y1: y + dy + 4 };
    if (box.x0 < 2 || box.x1 > bounds.w - 2 || box.y0 < 2 || box.y1 > bounds.h - 2) return false;
    if (this.placed.some((b) => box.x0 < b.x1 && box.x1 > b.x0 && box.y0 < b.y1 && box.y1 > b.y0)) return false;
    this.placed.push(box);
    const c = this.ctx;
    c.lineJoin = "round";
    c.lineWidth = 3;
    c.strokeStyle = this.bg;
    c.strokeText(text, left, y + dy);
    c.fillStyle = color;
    c.fillText(text, left, y + dy);
    return true;
  }
}

function dominant(l: ShipLane, on: ReadonlySet<LayerId>): ShipId | null {
  let best: ShipId | null = null, top = 0;
  for (const c of SHIP_IDS) {
    const r = on.has(c) ? l.by[c] ?? 0 : 0;
    if (r > top) { top = r; best = c; }
  }
  return best;
}

function visibleRate(l: ShipLane, on: ReadonlySet<LayerId>): number {
  let s = 0;
  for (const c of SHIP_IDS) if (on.has(c)) s += l.by[c] ?? 0;
  return s;
}

export function paintFlows(ctx: CanvasRenderingContext2D, scene: Scene, on: ReadonlySet<LayerId>, v: View, size: { w: number; h: number }): void {
  const dark = !v.light;
  const bg = dark ? "rgba(12,15,14,0.82)" : "rgba(240,238,230,0.85)";
  const ink = dark ? "#e9e6dc" : "#1c1f1d";
  const label = new Labels(ctx, bg, 11);
  const zoomK = Math.min(1.6, Math.pow(v.zoom, 0.25));
  const lanesOn = scene.lanes.filter((l) => visibleRate(l, on) > 0);

  // 1. lanes
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.globalCompositeOperation = dark ? "lighter" : "source-over";
  for (const l of lanesOn) {
    const cls = dominant(l, on);
    if (!cls) continue;
    const r = visibleRate(l, on);
    const breath = v.calm ? 0.5 : 0.5 + 0.5 * Math.sin(TAU * l.pulseHz * v.t + l.phase);
    projectPath(l.path, v);
    ctx.strokeStyle = colorOf(cls, v.light);
    ctx.globalAlpha = (dark ? 0.1 : 0.16) + (dark ? 0.16 : 0.2) * breath * (0.4 + 0.6 * (r / scene.rmax));
    ctx.lineWidth = (0.8 + 2.2 * Math.sqrt(r / scene.rmax)) * zoomK;
    strokeScratch(ctx, l.path.n);
  }

  ctx.globalCompositeOperation = "source-over";

  // 2. dots, batched per lane and class. Each class keeps its own strand across the lane (always the same side, so a class is found by
  // position as well as hue), and ships keep to the right of their direction of travel, so opposite flows run side by side.
  const dotR = 1.4 * zoomK;
  const strand = 1.35 * zoomK;
  for (const l of lanesOn) {
    for (const g of l.groups) {
      if (!on.has(g.cls)) continue;
      const total = l.path.total;
      const run = v.calm ? 0 : (v.t * g.speed) / total;
      const side = 2.4 * zoomK + (SHIP_IDS.indexOf(g.cls) - (SHIP_IDS.length - 1) / 2) * strand;
      if (dxs.length < g.n) { dxs = new Float32Array(g.n * 2); dys = new Float32Array(g.n * 2); }
      let k = 0;
      for (let i = 0; i < g.n; i++) {
        const jitter = (((g.seed * 31 + i * 17) % 97) / 97) * 0.6;
        let f = (i + jitter) / g.n + run;
        f -= Math.floor(f);
        const s = f * total;
        const p = screenOf(v, l.path, s);
        if (p.d < LIMB) continue;
        const q = screenOf(v, l.path, Math.min(total, s + 0.004)); // the way it is heading, to step to its right
        const len = Math.hypot(q.x - p.x, q.y - p.y);
        const off = side + (((i * 53 + g.seed) % 7) - 3) * 0.12 * zoomK; // a hair of scatter inside the strand
        dxs[k] = len > 1e-6 ? p.x - ((q.y - p.y) / len) * off : p.x;
        dys[k] = len > 1e-6 ? p.y + ((q.x - p.x) / len) * off : p.y;
        k++;
      }
      if (k === 0) continue;
      ctx.fillStyle = colorOf(g.cls, v.light);
      if (dark) { // a soft halo so a lone ship still reads on dark water
        ctx.globalAlpha = 0.13;
        ctx.beginPath();
        for (let i = 0; i < k; i++) { ctx.moveTo(dxs[i] + dotR * 2.4, dys[i]); ctx.arc(dxs[i], dys[i], dotR * 2.4, 0, TAU); }
        ctx.fill();
      }
      ctx.globalAlpha = 0.95;
      ctx.beginPath();
      for (let i = 0; i < k; i++) { ctx.moveTo(dxs[i] + dotR, dys[i]); ctx.arc(dxs[i], dys[i], dotR, 0, TAU); }
      ctx.fill();
    }
  }

  // 3. trade arcs
  for (const a of scene.arcs) {
    if (!on.has(a.layer)) continue;
    projectPath(a.path, v);
    const color = colorOf(a.layer, v.light);
    const w = a.width * zoomK;
    ctx.strokeStyle = color;
    ctx.setLineDash([]);
    ctx.globalAlpha = (dark ? 0.1 : 0.12) * a.weight;
    ctx.lineWidth = w * 2.6;
    strokeScratch(ctx, a.path.n);
    ctx.globalAlpha = (dark ? 0.5 : 0.55) * (0.5 + 0.5 * a.weight);
    ctx.lineWidth = w;
    ctx.setLineDash([w * 3 + 5, w * 2 + 7]);
    ctx.lineDashOffset = v.calm ? 0 : -v.t * 11;
    strokeScratch(ctx, a.path.n);
    ctx.setLineDash([]);
    // the arrowhead: where the arc is going, 88% of the way
    const tip = screenOf(v, a.path, a.path.total * 0.9), back = screenOf(v, a.path, a.path.total * 0.84);
    if (tip.d >= LIMB && back.d >= LIMB) {
      const ang = Math.atan2(tip.y - back.y, tip.x - back.x), s = 3.5 + w * 0.9;
      ctx.globalAlpha = dark ? 0.8 : 0.85;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(tip.x + Math.cos(ang) * s, tip.y + Math.sin(ang) * s);
      ctx.lineTo(tip.x + Math.cos(ang + 2.5) * s, tip.y + Math.sin(ang + 2.5) * s);
      ctx.lineTo(tip.x + Math.cos(ang - 2.5) * s, tip.y + Math.sin(ang - 2.5) * s);
      ctx.closePath();
      ctx.fill();
    }
  }
  ctx.globalAlpha = 1;

  // 4. place marks and anomalies
  const { m } = v;
  const markAt = (pv: Vec) => ({
    x: v.cx + v.rpx * (m[0] * pv[0] + m[1] * pv[1] + m[2] * pv[2]),
    y: v.cy - v.rpx * (m[3] * pv[0] + m[4] * pv[1] + m[5] * pv[2]),
    d: m[6] * pv[0] + m[7] * pv[1] + m[8] * pv[2],
  });
  const shipsOn = SHIP_IDS.some((c) => on.has(c)); // places are about ships: with only grain or money on, they stay off the globe
  const marks = shipsOn ? scene.places.map((p) => ({ p, s: markAt(p.v) })).filter((x) => x.s.d >= 0.08) : [];
  for (const { p, s } of marks) {
    const r = 2.2 + 0.7 * Math.sqrt(Math.max(0, p.r7));
    if (p.dir) {
      const col = ANOMALY[p.dir];
      const ph = v.calm ? 0.35 : (v.t * 0.7 + (p.id.length % 5) * 0.2) % 1;
      for (let k = 0; k < 2; k++) {
        const q = (ph + k * 0.5) % 1;
        ctx.globalAlpha = 0.7 * (1 - q);
        ctx.strokeStyle = col;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.arc(s.x, s.y, Math.min(r, 9) + 3 + q * 16, 0, TAU);
        ctx.stroke();
      }
      ctx.globalAlpha = 0.9;
      ctx.fillStyle = col;
      ctx.beginPath();
      ctx.arc(s.x, s.y, Math.min(r, 9) * 0.7 + 1.5, 0, TAU);
      ctx.fill();
    } else {
      ctx.globalAlpha = 0.85;
      ctx.strokeStyle = ink;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(s.x, s.y, 2.6, 0, TAU);
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;

  // 5. labels, most important first: anomalies, chokepoints, the busiest lanes, the largest arcs
  for (const { p, s } of marks.filter((x) => x.p.dir)) label.put(p.note, s.x, s.y, ANOMALY[p.dir as "above" | "below"], size, 12, 4);
  for (const { p, s } of marks.filter((x) => !x.p.dir && x.p.kind === "chokepoint")) {
    label.put(p.r7 > 0 ? `${p.label} · ${p.r7 >= 10 ? Math.round(p.r7) : p.r7.toFixed(1)}/day` : p.label, s.x, s.y, ink, size, 6, 4);
  }
  const busiest = [...lanesOn].sort((a, b) => visibleRate(b, on) - visibleRate(a, on)).slice(0, 5);
  for (const l of busiest) {
    const s = markAt(l.mid);
    const cls = dominant(l, on);
    if (s.d >= 0.25 && cls) label.put(l.label, s.x, s.y, colorOf(cls, v.light), size, 0, -6);
  }
  for (const a of scene.arcs) {
    if (!on.has(a.layer) || !a.labelled) continue;
    const mid = screenOf(v, a.path, a.path.total / 2);
    if (mid.d >= 0.3) label.put(a.label, mid.x, mid.y, colorOf(a.layer, v.light), size, 0, -6);
  }
  ctx.globalAlpha = 1;
}
