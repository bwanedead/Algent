// Pure layout of a native network (NativeNetwork.tsx; contract: backend agents/intel/network_spec.py). A tiny force simulation
// (nodes repel, ties are springs, a faint pull keeps everything central) run to rest before the first paint, so the same data
// always gives the same picture and nothing jitters. No DOM, no React, no library. The ideas are those of
// components/graph/RelationshipGraph.tsx, kept separate: that one is an interactive browser, this one is a still layout.

import type { NetEdge, NetNode } from "@/lib/visualSpecs";

export const VIEW_W = 400;
export const VIEW_H = 380;
const PAD_X = 64; // room for labels at the sides
const PAD_Y = 34;
const TICKS = 320;

export type Placed = { id: string; x: number; y: number; r: number };

/** Node radius: from the stated figure (area in proportion to it) when the network is sized, else one standard size. */
export function radiusOf(n: NetNode, maxWeight: number): number {
  return maxWeight > 0 && n.weight > 0 ? 8 + 12 * Math.sqrt(n.weight / maxWeight) : 9;
}

/** Where each node sits, in the VIEW_W x VIEW_H box. Deterministic. */
export function layout(nodes: NetNode[], edges: NetEdge[]): Map<string, Placed> {
  const maxW = Math.max(0, ...nodes.map((n) => n.weight));
  const p = nodes.map((n, i) => {
    const t = (i / Math.max(1, nodes.length)) * Math.PI * 2;
    const wobble = 1 + 0.15 * Math.sin(i * 7.3);
    return { id: n.id, x: Math.cos(t) * 120 * wobble, y: Math.sin(t) * 110 * wobble, vx: 0, vy: 0, r: radiusOf(n, maxW) };
  });
  const at = new Map(p.map((q, i) => [q.id, i]));
  const links = edges.flatMap((e) => {
    const a = at.get(e.source);
    const b = at.get(e.target);
    return a !== undefined && b !== undefined ? [{ a, b, k: 0.6 + 0.2 * e.strength }] : [];
  });
  let alpha = 1;
  for (let t = 0; t < TICKS; t++, alpha = Math.max(0.02, alpha * 0.985)) {
    for (let i = 0; i < p.length; i++) {
      for (let j = i + 1; j < p.length; j++) {
        const dx = p[i].x - p[j].x;
        const dy = p[i].y - p[j].y;
        const d2 = Math.max(dx * dx + dy * dy, 100);
        const d = Math.sqrt(d2);
        const f = (3400 * alpha) / d2;
        p[i].vx += (dx / d) * f;
        p[i].vy += (dy / d) * f;
        p[j].vx -= (dx / d) * f;
        p[j].vy -= (dy / d) * f;
      }
    }
    for (const l of links) {
      const dx = p[l.b].x - p[l.a].x;
      const dy = p[l.b].y - p[l.a].y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const f = ((d - 80) / d) * 0.06 * alpha * l.k;
      p[l.a].vx += dx * f;
      p[l.a].vy += dy * f;
      p[l.b].vx -= dx * f;
      p[l.b].vy -= dy * f;
    }
    for (const q of p) {
      q.vx = (q.vx - q.x * 0.015 * alpha) * 0.78;
      q.vy = (q.vy - q.y * 0.015 * alpha) * 0.78;
      q.x += q.vx;
      q.y += q.vy;
    }
  }
  // Fit the settled cloud into the box (keeping its proportions), leaving room for labels.
  const xs = p.map((q) => q.x);
  const ys = p.map((q) => q.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const k = Math.min((VIEW_W - 2 * PAD_X) / Math.max(x1 - x0, 1), (VIEW_H - 2 * PAD_Y) / Math.max(y1 - y0, 1), 2.4);
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  return new Map(p.map((q) => [q.id, { id: q.id, x: VIEW_W / 2 + (q.x - cx) * k, y: VIEW_H / 2 + (q.y - cy) * k, r: q.r }]));
}

/** The path of a tie between two placed nodes, ending at the nodes' edges. `bow` bends it sideways (for ties that share a pair).
 *  Returns the SVG path and its end tangent, so an arrowhead can be oriented. */
export function tiePath(a: Placed, b: Placed, bow: number, gap = 3): { d: string; mid: [number, number] } {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  const mx = (a.x + b.x) / 2 + nx * bow;
  const my = (a.y + b.y) / 2 + ny * bow;
  const trim = (from: Placed, toward: [number, number]): [number, number] => {
    const ux = toward[0] - from.x;
    const uy = toward[1] - from.y;
    const l = Math.hypot(ux, uy) || 1;
    return [from.x + (ux / l) * (from.r + gap), from.y + (uy / l) * (from.r + gap)];
  };
  const s = trim(a, [mx, my]);
  const e = trim(b, [mx, my]);
  return { d: `M${s[0].toFixed(1)},${s[1].toFixed(1)} Q${mx.toFixed(1)},${my.toFixed(1)} ${e[0].toFixed(1)},${e[1].toFixed(1)}`, mid: [0.25 * s[0] + 0.5 * mx + 0.25 * e[0], 0.25 * s[1] + 0.5 * my + 0.25 * e[1]] };
}

/** The dates the picture changes on (a tie begins or ends), oldest first: the scrubber's stops. */
export function frameDates(edges: NetEdge[]): string[] {
  return Array.from(new Set(edges.flatMap((e) => [e.start, e.end]).filter(Boolean))).sort();
}

/** Is the tie in force on `date`? A tie with no start has always been; with no end, still is. `date` "" = no scrubbing, all ties. */
export function activeOn(e: NetEdge, date: string): boolean {
  return !date || ((!e.start || e.start <= date) && (!e.end || date < e.end));
}
