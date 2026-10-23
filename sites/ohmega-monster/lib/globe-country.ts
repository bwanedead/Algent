import { compact, fmt, type Unit } from "./actors";
import { claimOf } from "./daily";
import type { CountryPanel, PanelStat } from "./globe/data";
import { liveAnomalies } from "./live";
import { countryView, type RawPanelStat } from "./views";

// The globe's country panel: supplemental stats and counts for one country, fetched when it is picked (so the globe payload stays small). The worker
// server builds the panel with the rest of the country (backend `views/country.py`): each stat bar places the value against the MEDIAN OF THE PROFILED
// STATES (G20, P5, countries in the news; not the world) for the same field on a log track (tick at the middle, a factor of ten either side spans it),
// so heavy-tailed fields (GDP, population) stay readable; the brief history is the country's own section of the one view, not a walk over thirty
// dailies. This module reads that view, words the numbers and brings the one live count (anomalies going on now). Server only.

const BRIEF_MAX = 150;

const medianText = (m: number, unit: string): string => (unit === "pct" ? `${m.toFixed(1)}%` : unit === "usd" ? `$${compact(m)}` : compact(m));

const statOf = (s: RawPanelStat): PanelStat => ({
  id: s.id,
  label: s.label,
  text: fmt(s.value, s.unit as Unit),
  year: s.year,
  pos: s.pos,
  median: s.median === null ? "" : medianText(s.median, s.unit),
});

export async function countryPanel(iso: string): Promise<CountryPanel | null> {
  if (!/^[A-Z]{2}$/.test(iso)) return null;
  const [view, anomalies] = await Promise.all([countryView(iso), liveAnomalies()]);
  const hot = anomalies.filter((x) => x.active && x.countries.includes(iso)).length;
  if (!view) {
    // A state with nothing on record yet: an honest empty panel, not an error (the globe lets any country be picked).
    return { iso, stats: [], profiled: 0, counts: { theaters: 0, statements7d: 0, sanctions: 0, calendar: 0, anomalies: hot }, grid: null, leaders: { head_of_state: "", head_of_government: "" }, briefs: [] };
  }
  const p = view.panel;
  return {
    iso,
    stats: p.stats.map(statOf),
    profiled: p.profiled,
    counts: { ...p.counts, anomalies: hot },
    grid: p.grid,
    leaders: p.leaders,
    briefs: p.briefs.map((b) => ({ ...b, text: claimOf(b.text, BRIEF_MAX) })),
  };
}
