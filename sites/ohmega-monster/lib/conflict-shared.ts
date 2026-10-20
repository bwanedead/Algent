// Attack / conflict events and GNSS interference zones, as data: the `conflict_events` and `gnss_zones` rows (backend `conflict/` and
// `gnss/`, migration 014) and the pure helpers the pages, the HUD and the API share. No I/O and no node imports, so a client component may
// import this file. The server-side reads live in lib/conflict.ts.
//
// PROVENANCE is part of the data: every row says what kind of record it is (`basis`) and the limit of its coverage (`coverage_note`), and a
// count we make ourselves is a minimum with a "since" date (`baseline_since`). `provenanceOf` turns those into the words an info hover shows.

export type EventSource = "gdelt" | "reliefweb" | "acled" | "ucdp";
export type EventType = "bombing" | "airstrike" | "armed_clash" | "assault" | "mass_violence" | "report";
export type Basis = "official" | "third_party" | "our_count" | "our_estimate";

export type AssetRef = { id: string; name: string; type: string; km: number };

export type ConflictRow = {
  id: string;
  source: EventSource;
  on_date: string;
  observed_at: string;
  type: EventType;
  code: string;
  lat: number | null;
  lon: number | null;
  place: string;
  country: string;
  actor1: string;
  actor2: string;
  fatalities: number | null;
  articles: number;
  title: string;
  urls: string[];
  coding: "machine" | "curated" | "report";
  confidence: "low" | "medium" | "high";
  basis: Basis;
  coverage_note: string;
  assets: AssetRef[];
};

export type Severity = "low" | "medium" | "high";
export type GnssFlag = "" | "new" | "intensifying";

export type GnssRow = {
  id: string;
  on_date: string;
  source: "ohmega_adsb" | "gpsjam";
  cell: string;
  lat: number;
  lon: number;
  size_deg: number;
  country: string;
  severity: Severity;
  degraded_share: number;
  aircraft: number;
  flag: GnssFlag;
  cross_check: "" | "agrees" | "not_in_gpsjam";
  basis: Basis;
  coverage_note: string;
  baseline_since: string | null;
};

export const EVENT_TYPES: { id: EventType; label: string }[] = [
  { id: "bombing", label: "Bombing" },
  { id: "airstrike", label: "Air or drone strike" },
  { id: "armed_clash", label: "Armed clash" },
  { id: "assault", label: "Assault or killing" },
  { id: "mass_violence", label: "Mass violence" },
  { id: "report", label: "Humanitarian report" },
];
export const typeLabel = (t: string): string => EVENT_TYPES.find((x) => x.id === t)?.label ?? t;

export const EVENT_SOURCES: Record<EventSource, { short: string; name: string; keyed: boolean }> = {
  gdelt: { short: "GDELT", name: "GDELT (machine-coded from news)", keyed: false },
  reliefweb: { short: "ReliefWeb", name: "ReliefWeb (UN OCHA reports)", keyed: true },
  acled: { short: "ACLED", name: "ACLED (curated)", keyed: true },
  ucdp: { short: "UCDP", name: "UCDP (curated)", keyed: true },
};

export const SEVERITY_LABEL: Record<Severity, string> = { low: "Low", medium: "Medium", high: "High" };

/** What kind of number this is, in the words of the info hover. */
export const BASIS_LABEL: Record<Basis, string> = {
  official: "Official report",
  third_party: "Third-party dataset",
  our_count: "Our own count",
  our_estimate: "Our own estimate",
};

export type Provenance = { basis: Basis; coverage_note: string; baseline_since: string | null };

/** The hover text for a figure: the kind of record, the limit of its coverage, and (for our own counts and baselines) since when we have been collecting. */
export function provenanceText(p: Provenance): string {
  const since = p.baseline_since ? ` Collected since ${p.baseline_since}; nothing earlier is counted.` : "";
  const minimum = p.basis === "our_count" || p.basis === "our_estimate" ? " Coverage is partial, so treat it as a minimum." : "";
  return `${BASIS_LABEL[p.basis]}. ${p.coverage_note}${minimum}${since}`.replace(/\s+/g, " ").trim();
}

/** Where the whole event log comes from, as one provenance for an aggregate figure on the page: our own count of what the sources reported. */
export function logProvenance(rows: ConflictRow[], since: string | null): Provenance {
  const sources = Array.from(new Set(rows.map((r) => EVENT_SOURCES[r.source]?.short ?? r.source))).join(", ") || "no source yet";
  return {
    basis: "our_count",
    coverage_note: `Ohmega's tally of events reported by ${sources}. Machine-coded rows (GDELT) can duplicate, misplace or misread an event; no source sees every attack.`,
    baseline_since: since,
  };
}

/** Per-country counts (an event with no resolved country is counted under ""), most events first. */
export function byCountry(rows: ConflictRow[]): { iso: string; n: number; fatalities: number }[] {
  const m = new Map<string, { iso: string; n: number; fatalities: number }>();
  for (const r of rows) {
    const c = m.get(r.country) ?? { iso: r.country, n: 0, fatalities: 0 };
    c.n += 1;
    c.fatalities += r.fatalities ?? 0;
    m.set(r.country, c);
  }
  return Array.from(m.values()).sort((a, b) => b.n - a.n || a.iso.localeCompare(b.iso));
}

/** Events per day for the `days` days ending at `today` (oldest first): the sparkline of the log. */
export function dailyCounts(rows: ConflictRow[], today: string, days = 14): number[] {
  const ms = (iso: string) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
  const out = new Array<number>(days).fill(0);
  for (const r of rows) {
    const i = days - 1 - Math.round((ms(today) - ms(r.on_date)) / 86400000);
    if (i >= 0 && i < days) out[i] += 1;
  }
  return out;
}

export const sharePct = (s: number): string => `${Math.round(s * 100)}%`;

export const addDaysIso = (d: string, n: number): string => new Date(Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10)) + n * 86400000).toISOString().slice(0, 10);
