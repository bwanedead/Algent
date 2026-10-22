// Home's "at a glance" band, as data: a handful of key movers read from numbers we already publish (the live summary and ship counts,
// the energy snapshot, the Pulses, the day's report). Pure functions, no I/O and no node imports; every builder returns null when its
// source is missing, so the band shows only what is real and never a zero it does not know. Rendering: components/home/Glance.tsx.
// Every number is worded by the stats registry (lib/stats): our own counts are minimums, model readings are marked, and a comparison with
// our own young history is withheld ("collecting since 11 Oct").

import type { Daily, DailyTheater, DailyVisual, Tracker } from "./daily";
import { shortDay, theaterAnchor } from "./daily";
import type { Snapshot } from "./intel";
import { shipTiles, type EnergyDoc, type LiveStat, type Summary, type Tile } from "./live-shared";
import { fmtNum, historyOf, shortDate, signed, statView, type Provenance } from "./stats/render";

export type Cell = {
  key: string;
  label: string;
  value: string;
  unit: string;
  /** Signed change in words ("+12% vs usual"); `sign` colours it and picks no meaning beyond up / down. Null while a comparison is withheld. */
  delta: { text: string; sign: number } | null;
  spark: number[];
  href: string;
  /** What the spark and delta are measured against, one short phrase. Says "collecting since 11 Oct" while our own baseline is too young. */
  foot: string;
  /** Registry id (lib/stats/registry.ts) and the plain hover lines that say whose number this is. */
  statId: string;
  info: string[];
  /** A model's reading rather than a measurement. */
  model?: boolean;
  /** A second figure for the same thing, labelled as ours ("Heard by our receivers: 0 heard on 19 Oct, a minimum"). */
  note?: string;
};

const median = (xs: number[]): number => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

const PORTWATCH_ID = /^chk_((?!.*tanker).+)_transits$/;

/** IMF PortWatch chokepoint trackers in the newest report (official), keyed by the gate slug our own AIS uses. */
function portwatchTrackers(report: Daily | null): Map<string, Tracker> {
  const out = new Map<string, Tracker>();
  for (const t of report?.theaters ?? []) {
    for (const tr of t.numbers?.trackers ?? ([] as Tracker[])) {
      const m = PORTWATCH_ID.exec(tr.id);
      if (m && !out.has(m[1])) out.set(m[1], tr);
    }
  }
  return out;
}

/** Periods of the completed days of one stat kind, to read how long our own series is. */
const statPeriods = (stats: LiveStat[], kind: "ships" | "aircraft" | "fires"): string[] => stats.filter((s) => s.kind === kind && !s.partial).map((s) => s.period);

/** Our AIS reading for a gate as the registry words it: a minimum, with the day it is for. Undefined without a completed day. */
function heardLine(tile: Tile | undefined, prov: Provenance | undefined): string | undefined {
  if (!tile) return undefined;
  const v = statView({ id: "chokepoint_ais_transits", value: tile.latest, provenance: prov, layer: "ships" });
  return `Heard by our receivers: ${v.text} on ${shortDate(tile.latestDay)}, a minimum`;
}

/** A chokepoint, led by the OFFICIAL series (IMF PortWatch) when the Daily carries one: Hormuz first, else the one that moved most against a year ago.
 *  Our own AIS count rides underneath, labelled a minimum. It never headlines and never picks the story: a young noisy series cannot "depart furthest". */
function chokepointCell(stats: LiveStat[], report: Daily | null, prov: Provenance | undefined): Cell | null {
  const tiles = new Map(shipTiles(stats).map((t) => [t.region, t]));
  const pw = portwatchTrackers(report);
  const yearPct = (t: Tracker) => t.changes["1y"]?.pct ?? null;
  const slug = pw.has("hormuz")
    ? "hormuz"
    : Array.from(pw.entries())
        .filter(([, t]) => yearPct(t) !== null)
        .sort((a, b) => Math.abs(yearPct(b[1]) ?? 0) - Math.abs(yearPct(a[1]) ?? 0))[0]?.[0];
  const tr = slug ? pw.get(slug) : undefined;
  if (tr && slug) {
    const pct = yearPct(tr);
    const v = statView({ id: "chokepoint_portwatch_transits", value: Math.round(tr.value), compare: pct === null ? undefined : { kind: "prior", pct, label: "vs a year ago" } });
    return {
      key: "chokepoint", label: `${tr.name.split(" — ")[0]} transits`, value: v.text, unit: "ships / day · IMF PortWatch", delta: v.comparison, spark: tr.spark.slice(-14), href: "/live",
      foot: `official, week to ${shortDay(tr.as_of)}`, statId: v.def.id, info: v.lines, note: heardLine(tiles.get(slug), prov),
    };
  }
  const t = tiles.get("hormuz");
  if (!t) return null;
  const v = statView({ id: "chokepoint_ais_transits", value: t.latest, compare: { kind: "usual", pct: t.pct }, history: historyOf(statPeriods(stats, "ships")), provenance: prov, layer: "ships" });
  return {
    key: "chokepoint", label: `${t.name} transits`, value: v.text, unit: "ships / day · our receivers", delta: v.comparison, spark: t.days.slice(-14),
    href: "/live", foot: v.collecting ?? "last 14 days", statId: v.def.id, info: v.lines,
  };
}

/** Tankers inside Hormuz right now (a minimum: only what our receivers hear); failing a Hormuz gate, inside all the watched straits. */
function tankersCell(summary: Summary | null): Cell | null {
  const gates = Object.entries(summary?.gates ?? {});
  if (gates.length === 0) return null;
  const hormuz = gates.find(([k, g]) => /hormuz/i.test(`${k} ${g.label}`));
  const n = hormuz ? hormuz[1].tankers : gates.reduce((a, [, g]) => a + (g.tankers ?? 0), 0);
  if (n === undefined || n === null) return null;
  const v = statView({ id: "tankers_in_strait_now", value: n });
  return { key: "tankers", label: hormuz ? "Tankers in Hormuz" : "Tankers in straits", value: v.text, unit: "now", delta: null, spark: [], href: "/live", foot: "live, our receivers only", statId: v.def.id, info: v.lines };
}

/** The busiest moment of the day for military aircraft, summed over the regions we watch. NOT unique aircraft and not a total over the day. */
function aircraftCell(stats: LiveStat[], prov: Provenance | undefined): Cell | null {
  const by = new Map<string, number>();
  const regions = new Set<string>();
  for (const s of stats) {
    if (s.kind === "aircraft" && !s.partial) {
      by.set(s.period, (by.get(s.period) ?? 0) + s.value);
      regions.add(s.region);
    }
  }
  const days = Array.from(by.entries()).sort((a, b) => a[0].localeCompare(b[0])).map((d) => d[1]);
  if (days.length < 3) return null;
  const latest = days[days.length - 1];
  const before = days.slice(-15, -1);
  const usual = before.length >= 5 ? median(before) : null;
  const pct = usual && usual > 0 ? Math.round(((latest - usual) / usual) * 100) : null;
  const v = statView({ id: "mil_aircraft_peak", value: latest, compare: { kind: "usual", pct }, history: historyOf(statPeriods(stats, "aircraft")), provenance: prov, layer: "aircraft" });
  return {
    key: "aircraft", label: "Military aircraft, busiest moment", value: v.text, unit: `in the air at once, summed over ${regions.size} regions`, delta: v.comparison, spark: days.slice(-14),
    href: "/live", foot: v.collecting ?? "last 14 days", statId: v.def.id, info: v.lines,
  };
}

function gasCell(energy: EnergyDoc | null): Cell | null {
  const g = energy?.gas;
  if (!g) return null;
  const v = statView({ id: "eu_gas_storage", value: g.value, digits: 1 });
  return {
    key: "gas",
    label: "EU gas storage",
    value: v.text,
    unit: "% full",
    delta: g.week_change === null ? null : { text: `${signed(g.week_change, 1)} pts wk`, sign: g.week_change },
    spark: g.spark.filter((x): x is number => x !== null),
    href: "/live",
    foot: `GIE AGSI+, ${shortDate(g.as_of_day)}`,
    statId: v.def.id,
    info: v.lines,
  };
}

/** The Pulse that moved most over seven days, with its own history as the line. A model's reading, and marked as one. */
function pulseCell(snap: Snapshot | null): Cell | null {
  const all = (snap?.situations ?? []).flatMap((s) => s.pulses).filter((p) => p.position !== null && p.velocity_7d !== null);
  if (all.length === 0) return null;
  const p = all.sort((a, b) => Math.abs(b.velocity_7d ?? 0) - Math.abs(a.velocity_7d ?? 0))[0];
  const v = p.velocity_7d ?? 0;
  const view = statView({ id: "pulse_position", value: p.position ?? 0 });
  return {
    key: "pulse",
    label: p.title || p.name,
    value: view.text,
    unit: "/ 100",
    delta: { text: `${signed(v, 1)} pts 7d`, sign: v },
    spark: p.history.slice(-14).map((h) => h.position),
    href: `/pulses`,
    foot: "biggest 7-day move",
    statId: view.def.id,
    info: view.lines,
    model: true,
  };
}

function theatersCell(report: Daily | null): Cell | null {
  const sections = (report?.theaters ?? []).filter((t) => t.kind === "section");
  if (sections.length === 0) return null;
  const up = sections.filter((t) => t.escalation.direction === "rising").length;
  const v = statView({ id: "theaters_escalating", value: up });
  return { key: "theaters", label: "Daily sections escalating", value: v.text, unit: `of ${sections.length} written today`, delta: null, spark: [], href: "/intel/theaters", foot: "today's report", statId: v.def.id, info: v.lines };
}

/** Up to six cells, in the order a reader should meet them; absent sources simply leave their cell out. */
export function glanceCells(i: { stats: LiveStat[]; summary: Summary | null; energy: EnergyDoc | null; snap: Snapshot | null; report: Daily | null }): Cell[] {
  const prov = i.summary?.provenance;
  return [theatersCell(i.report), chokepointCell(i.stats, i.report, prov), tankersCell(i.summary), aircraftCell(i.stats, prov), gasCell(i.energy), pulseCell(i.snap)].filter((c): c is Cell => c !== null);
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
      seen.set(tr.id, { id: tr.id, name: tr.name, value: fmtNum(tr.value, Math.abs(tr.value) < 100 ? 1 : 0), unit: tr.unit, pct, stepLabel: tr.step_label, spark: tr.spark, href: `/geopolitics#${theaterAnchor(t, i)}` });
    }
  });
  return Array.from(seen.values()).sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct)).slice(0, n);
}

export const fmtPct = (pct: number): string => `${signed(pct, Math.abs(pct) < 10 ? 1 : 0)}%`;
