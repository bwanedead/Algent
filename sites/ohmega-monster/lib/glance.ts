// Home's "at a glance" band, as data: a handful of key movers read from numbers we already publish (the live summary and ship counts,
// the energy snapshot, the Pulses, the day's report). Pure functions, no I/O and no node imports; every builder returns null when its
// source is missing, so the band shows only what is real and never a zero it does not know. Rendering: components/home/Glance.tsx.

import type { Daily, DailyTheater, DailyVisual, Tracker } from "./daily";
import { theaterAnchor } from "./daily";
import type { Snapshot } from "./intel";
import { shipTiles, type EnergyDoc, type LiveStat, type Summary } from "./live-shared";

export type Cell = {
  key: string;
  label: string;
  value: string;
  unit: string;
  /** Signed change in words ("+12% vs usual"); `sign` colours it and picks no meaning beyond up / down. */
  delta: { text: string; sign: number } | null;
  spark: number[];
  href: string;
  /** What the spark and delta are measured against, one short phrase. */
  foot: string;
};

const num = (n: number, digits = 0): string => n.toLocaleString("en-US", { maximumFractionDigits: digits });
const signed = (n: number, digits = 0): string => `${n > 0 ? "+" : n < 0 ? "−" : ""}${num(Math.abs(n), digits)}`;
const median = (xs: number[]): number => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

/** The chokepoint whose latest completed day departs furthest from its own recent normal. */
function chokepointCell(stats: LiveStat[]): Cell | null {
  const tiles = shipTiles(stats).filter((t) => t.pct !== null);
  if (tiles.length === 0) return null;
  const t = tiles.sort((a, b) => Math.abs(b.pct ?? 0) - Math.abs(a.pct ?? 0))[0];
  return {
    key: "chokepoint",
    label: `${t.name} transits`,
    value: num(t.latest),
    unit: "ships / day",
    delta: { text: `${signed(t.pct ?? 0)}% vs usual`, sign: t.pct ?? 0 },
    spark: t.days.slice(-14),
    href: "/live",
    foot: "last 14 days",
  };
}

/** Tankers inside Hormuz right now; failing a Hormuz gate, inside all the watched straits. */
function tankersCell(summary: Summary | null): Cell | null {
  const gates = Object.entries(summary?.gates ?? {});
  if (gates.length === 0) return null;
  const hormuz = gates.find(([k, g]) => /hormuz/i.test(`${k} ${g.label}`));
  const n = hormuz ? hormuz[1].tankers : gates.reduce((a, [, g]) => a + (g.tankers ?? 0), 0);
  if (n === undefined || n === null) return null;
  return { key: "tankers", label: hormuz ? "Tankers in Hormuz" : "Tankers in straits", value: num(n), unit: "now", delta: null, spark: [], href: "/live", foot: "live count" };
}

/** Military aircraft seen per day, all regions we count, against their recent median. */
function aircraftCell(stats: LiveStat[]): Cell | null {
  const by = new Map<string, number>();
  for (const s of stats) if (s.kind === "aircraft" && !s.partial) by.set(s.period, (by.get(s.period) ?? 0) + s.value);
  const days = Array.from(by.entries()).sort((a, b) => a[0].localeCompare(b[0])).map((d) => d[1]);
  if (days.length < 3) return null;
  const latest = days[days.length - 1];
  const before = days.slice(-15, -1);
  const usual = before.length >= 5 ? median(before) : null;
  const pct = usual && usual > 0 ? Math.round(((latest - usual) / usual) * 100) : null;
  return {
    key: "aircraft",
    label: "Military aircraft",
    value: num(latest),
    unit: "seen / day",
    delta: pct === null ? null : { text: `${signed(pct)}% vs usual`, sign: pct },
    spark: days.slice(-14),
    href: "/live",
    foot: "last 14 days",
  };
}

function gasCell(energy: EnergyDoc | null): Cell | null {
  const g = energy?.gas;
  if (!g) return null;
  return {
    key: "gas",
    label: "EU gas storage",
    value: num(g.value, 1),
    unit: "% full",
    delta: g.week_change === null ? null : { text: `${signed(g.week_change, 1)} pts wk`, sign: g.week_change },
    spark: g.spark.filter((v): v is number => v !== null),
    href: "/live",
    foot: "last 7 days",
  };
}

/** The Pulse that moved most over seven days, with its own history as the line. */
function pulseCell(snap: Snapshot | null): Cell | null {
  const all = (snap?.situations ?? []).flatMap((s) => s.pulses).filter((p) => p.position !== null && p.velocity_7d !== null);
  if (all.length === 0) return null;
  const p = all.sort((a, b) => Math.abs(b.velocity_7d ?? 0) - Math.abs(a.velocity_7d ?? 0))[0];
  const v = p.velocity_7d ?? 0;
  return {
    key: "pulse",
    label: p.title || p.name,
    value: num(p.position ?? 0),
    unit: "/ 100",
    delta: { text: `${signed(v, 1)} pts 7d`, sign: v },
    spark: p.history.slice(-14).map((h) => h.position),
    href: `/pulses`,
    foot: "biggest 7-day move",
  };
}

function theatersCell(report: Daily | null): Cell | null {
  const sections = (report?.theaters ?? []).filter((t) => t.kind === "section");
  if (sections.length === 0) return null;
  const up = sections.filter((t) => t.escalation.direction === "rising").length;
  return { key: "theaters", label: "Theaters escalating", value: num(up), unit: `of ${sections.length}`, delta: null, spark: [], href: "/intel/theaters", foot: "today's report" };
}

/** Up to six cells, in the order a reader should meet them; absent sources simply leave their cell out. */
export function glanceCells(i: { stats: LiveStat[]; summary: Summary | null; energy: EnergyDoc | null; snap: Snapshot | null; report: Daily | null }): Cell[] {
  return [theatersCell(i.report), chokepointCell(i.stats), tankersCell(i.summary), aircraftCell(i.stats), gasCell(i.energy), pulseCell(i.snap)].filter((c): c is Cell => c !== null);
}

// ---- chart of the day -------------------------------------------------------------------------------------------------

const CHART_KINDS: DailyVisual["kind"][] = ["tracker_compare", "chart", "timeline", "flow", "network", "comparison"];

export type DayChart = { visual: DailyVisual; theater: DailyTheater; anchor: string };

/** The day's best drawn visual that has a still image: our own tracker comparison first, then the other data forms, section order. */
export function chartOfDay(report: Daily | null): DayChart | null {
  if (!report) return null;
  let best: DayChart | null = null;
  let bestRank = CHART_KINDS.length;
  for (let i = 0; i < report.theaters.length; i++) {
    const t = report.theaters[i];
    for (const v of t.visuals) {
      const rank = CHART_KINDS.indexOf(v.kind);
      if (rank < 0 || rank >= bestRank || v.schematic || !(v.preview || v.asset)) continue;
      best = { visual: v, theater: t, anchor: theaterAnchor(t, i) };
      bestRank = rank;
    }
  }
  return best;
}

export type Mover = { id: string; name: string; value: string; unit: string; pct: number; stepLabel: string; spark: number[]; href: string };

/** Fallback to a chart: the trackers (instruments) that moved most over their own natural step, deduplicated across sections. */
export function topMovers(report: Daily | null, n = 5): Mover[] {
  const seen = new Map<string, Mover>();
  (report?.theaters ?? []).forEach((t, i) => {
    for (const tr of t.numbers?.trackers ?? ([] as Tracker[])) {
      const pct = tr.changes[tr.step_key]?.pct ?? null;
      if (pct === null || seen.has(tr.id)) continue;
      seen.set(tr.id, { id: tr.id, name: tr.name, value: num(tr.value, Math.abs(tr.value) < 100 ? 1 : 0), unit: tr.unit, pct, stepLabel: tr.step_label, spark: tr.spark, href: `/geopolitics#${theaterAnchor(t, i)}` });
    }
  });
  return Array.from(seen.values()).sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct)).slice(0, n);
}

export const fmtPct = (pct: number): string => `${signed(pct, Math.abs(pct) < 10 ? 1 : 0)}%`;
