import { actor, allActors, compact, fieldOf, fmt, type Actor } from "./actors";
import { calendarForCountry } from "./calendar";
import { getGrid } from "./geoledger";
import type { CountryPanel, PanelStat } from "./globe/data";
import { countryBriefs } from "./globe-briefs";
import { liveAnomalies } from "./live";
import { sanctionsForCountry, SANCTIONS_WINDOW_DAYS } from "./sanctions";

// The globe's country panel: supplemental stats and counts for one country, fetched when it is picked (so the globe payload stays small).
// Stats come from the published actor profiles; each bar places the value against the WORLD MEDIAN of the same field on a log track
// (tick at the middle, a factor of ten either side spans it), so heavy-tailed fields (GDP, population) stay readable. Server only.

const STATS: { id: string; label: string }[] = [
  { id: "population", label: "Population" },
  { id: "gdp", label: "GDP" },
  { id: "gdp_pc", label: "GDP per person" },
  { id: "milex", label: "Military spending" },
  { id: "milex_pct", label: "Military, share of GDP" },
  { id: "energy_import_pct", label: "Net energy imports, share of use" },
  { id: "fuel_exports_pct", label: "Fuels, share of exports" },
  { id: "gov_debt", label: "Government debt, share of GDP" },
  { id: "reserves_usd", label: "Foreign reserves" },
];

const MEDIAN_TTL_MS = 3600000;
let medians: { at: number; by: Map<string, number>; n: number } | null = null;

const median = (xs: number[]): number => {
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

async function worldMedians(): Promise<{ by: Map<string, number>; n: number }> {
  if (medians && Date.now() - medians.at < MEDIAN_TTL_MS) return medians;
  const all = await allActors();
  const by = new Map<string, number>();
  for (const { id } of STATS) {
    const vals = all.map((a) => fieldOf(a, id)?.value).filter((v): v is number => typeof v === "number" && v > 0);
    if (vals.length >= 5) by.set(id, median(vals));
  }
  medians = { at: Date.now(), by, n: all.length };
  return medians;
}

const pos = (v: number, med: number | undefined): number | null =>
  med && v > 0 ? Math.min(1, Math.max(0, 0.5 + 0.5 * Math.log10(v / med))) : null;

function statsOf(a: Actor, med: Map<string, number>): PanelStat[] {
  const out: PanelStat[] = [];
  for (const { id, label } of STATS) {
    const f = fieldOf(a, id);
    if (!f) continue;
    const m = med.get(id);
    out.push({ id, label, text: fmt(f.value, f.unit), year: f.year, pos: pos(f.value, m), median: m === undefined ? "" : f.unit === "pct" ? `${m.toFixed(1)}%` : f.unit === "usd" ? `$${compact(m)}` : compact(m) });
  }
  return out;
}

export async function countryPanel(iso: string): Promise<CountryPanel | null> {
  if (!/^[A-Z]{2}$/.test(iso)) return null;
  const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
  const [a, med, sanctions, calendar, anomalies, grid, briefs] = await Promise.all([
    actor(iso), worldMedians(), sanctionsForCountry(iso, SANCTIONS_WINDOW_DAYS), calendarForCountry(iso, 45, 60), liveAnomalies(), getGrid(iso), countryBriefs(iso),
  ]);
  return {
    iso,
    stats: a ? statsOf(a, med) : [],
    counts: {
      theaters: a?.involved.theaters.length ?? 0,
      statements7d: a?.statements.filter((s) => s.date >= weekAgo).length ?? 0,
      sanctions30d: sanctions.length,
      calendar: calendar.length,
      anomalies: anomalies.filter((x) => x.active && x.countries.includes(iso)).length,
    },
    grid: grid && grid.line ? { line: grid.line, asOf: grid.as_of } : null,
    leaders: { head_of_state: a?.leadership.head_of_state?.name ?? "", head_of_government: a?.leadership.head_of_government?.name ?? "" },
    briefs,
  };
}
