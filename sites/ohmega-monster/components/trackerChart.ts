// Pure maths of the tracker comparison chart (NativeTrackerCompare.tsx; contract: backend agents/intel/tracker_compare_spec.py):
// the shared time axis, indexing every line to 100 where all of them have begun, "nice" ticks, nearest-reading lookup for the
// crosshair, and spreading of the direct labels at the line ends so none overlaps another. No DOM, no React.

import type { TrackerLine } from "@/lib/visualSpecs";

const DAY_MS = 86_400_000;
/** Days since the epoch of an ISO date (UTC): the x value of a reading. */
export const dayOf = (iso: string): number => Math.floor(Date.parse(`${iso}T00:00:00Z`) / DAY_MS);
export const isoOf = (day: number): string => new Date(day * DAY_MS).toISOString().slice(0, 10);

/** The first date every line has a reading on: where the index is 100. */
export function commonStart(series: TrackerLine[]): string {
  return series.reduce((m, s) => (s.points[0][0] > m ? s.points[0][0] : m), series[0].points[0][0]);
}

export type Pt = { day: number; date: string; raw: number; idx: number };

/** A line's readings from `start` on, each with its raw value and its index (the reading at, or just before, `start` = 100). */
export function indexed(s: TrackerLine, start: string): Pt[] {
  const before = s.points.filter((p) => p[0] <= start);
  const base = (before.length ? before[before.length - 1] : s.points[0])[1];
  return s.points.filter((p) => p[0] >= start).map((p) => ({ day: dayOf(p[0]), date: p[0], raw: p[1], idx: base ? (p[1] / base) * 100 : 100 }));
}

/** Round tick values covering [lo, hi], about `n` of them. */
export function ticks(lo: number, hi: number, n = 4): number[] {
  const span = hi - lo || Math.abs(hi) || 1;
  const raw = span / Math.max(1, n);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Math.round(v / step) * step);
  return out;
}

/** The reading of a line in force on `day`: its last one on or before (null before the line begins). */
export function readingAt(pts: Pt[], day: number): Pt | null {
  let found: Pt | null = null;
  for (const p of pts) {
    if (p.day > day) break;
    found = p;
  }
  return found;
}

/** The sorted union of the days any of the lines has a reading on. */
export function allDays(lines: Pt[][]): number[] {
  return Array.from(new Set(lines.flatMap((l) => l.map((p) => p.day)))).sort((a, b) => a - b);
}

/** The day in `days` nearest to `day`. */
export function nearestDay(days: number[], day: number): number {
  let best = days[0];
  for (const d of days) if (Math.abs(d - day) < Math.abs(best - day)) best = d;
  return best;
}

/** Spread label positions (y of each, in any order) so neighbours are at least `gap` apart, within [top, bottom]. */
export function dodge(ys: number[], gap: number, top: number, bottom: number): number[] {
  const order = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y);
  for (let k = 0; k < order.length; k++) order[k].y = Math.max(order[k].y, k === 0 ? top : order[k - 1].y + gap);
  for (let k = order.length - 1; k >= 0; k--) order[k].y = Math.min(order[k].y, k === order.length - 1 ? bottom : order[k + 1].y - gap);
  const out = new Array<number>(ys.length);
  for (const o of order) out[o.i] = o.y;
  return out;
}

/** A value for people: 3 significant figures for small, grouped thousands for large. */
export function fmt(v: number): string {
  const a = Math.abs(v);
  if (a >= 1000) return Math.round(v).toLocaleString("en");
  if (a >= 100) return v.toFixed(0);
  if (a >= 10) return v.toFixed(1);
  return v.toFixed(2).replace(/\.?0+$/, "");
}
