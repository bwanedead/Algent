// Pure display helpers for trackers (no node imports: safe anywhere). Change is shown from -> to; the arrow
// carries direction only, never good or bad (the accent is reserved for "unusual / new").

import type { Tracker, TrackerChange, TrackerHorizon } from "@/lib/daily";

/** 4-5 significant figures, trailing zeros trimmed: 101.49, 1.1225, 4171.6 -> "4,172", ships 27 -> "27". */
export function fmtValue(v: number): string {
  const a = Math.abs(v);
  const dp = a >= 1000 ? 0 : a >= 100 ? 1 : a >= 10 ? 2 : 4;
  const s = v.toFixed(dp);
  const trimmed = dp > 0 ? s.replace(/\.?0+$/, "") : s;
  const [int, frac] = trimmed.split(".");
  return Number(int).toLocaleString("en-US") + (frac ? `.${frac}` : "");
}

export const arrow = (delta: number): string => (delta > 0 ? "▲" : delta < 0 ? "▼" : "◆");

/** "▲ +1.1%" — or in points ("▲ +0.12 pp") for a series that is itself a percentage or a rate. */
export function fmtChange(t: Tracker, c: TrackerChange): string {
  const delta = t.value - c.from;
  if (Math.abs(delta) < 1e-12) return "◆ 0";
  const sign = delta > 0 ? "+" : "−";
  if (t.unit.startsWith("%")) return `${arrow(delta)} ${sign}${fmtValue(Math.abs(delta))} pp`;
  if (c.pct === null) return `${arrow(delta)} ${sign}${fmtValue(Math.abs(delta))}`;
  const p = Math.abs(c.pct);
  return `${arrow(delta)} ${sign}${p < 10 ? p.toFixed(1) : Math.round(p)}%`;
}

/** Label of the previous-reading horizon, by how often the series is published. */
export const PREV_LABEL: Record<Tracker["freq"], string> = { daily: "1d", weekly: "1w", monthly: "1mo" };
export const HORIZON_LABEL: Record<TrackerHorizon, string> = { prev: "previous reading", "7d": "7 days", "30d": "30 days", "1y": "1 year" };

/** A reader-sized name: drops bracketed qualifiers and "daily vessel transits" wordiness. */
export function shortName(name: string): string {
  return name
    .replace(/\s*\([^)]*\)/g, "")
    .replace(/\s+—\s+daily (vessel|tanker) transits/i, " $1 transits")
    .trim();
}

export const REASON: Record<string, string> = {
  change: "today's move is large against this series' own history",
  level: "the level is far from where it sat over the past year",
};
