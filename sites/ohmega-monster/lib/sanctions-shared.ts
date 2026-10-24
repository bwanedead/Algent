// Sanctions designations, as data: the `sanctions_events` row (backend `sanctions/`, migration 012) and the pure helpers the
// /intel/sanctions page shares with the actor pages. No I/O and no node imports, so a client component may import this file.
// The server-side reads live in lib/sanctions.ts.

export type SanctionsSource = "ofac" | "uk" | "eu";
export type SanctionsAction = "designated" | "delisted";
export type SanctionsType = "person" | "entity" | "vessel" | "aircraft";

export type SanctionsRow = {
  id: string;
  source: SanctionsSource;
  action: SanctionsAction;
  on_date: string;
  observed_on: string;
  ref: string;
  name: string;
  type: SanctionsType;
  programmes: string[];
  countries: string[];
  imo: string;
  flag: string;
  owner: string;
  source_url: string;
  baseline: boolean;
  asset_id: string | null;
};

/** Who publishes each list (short label, long name, the page to cite for the list as a whole). */
export const SOURCES: Record<SanctionsSource, { short: string; name: string }> = {
  ofac: { short: "US", name: "US Treasury OFAC (SDN list)" },
  uk: { short: "UK", name: "UK Sanctions List (FCDO / OFSI)" },
  eu: { short: "EU", name: "EU consolidated financial sanctions list" },
};

export const TYPES: { id: SanctionsType; label: string }[] = [
  { id: "person", label: "Person" },
  { id: "entity", label: "Entity" },
  { id: "vessel", label: "Vessel" },
  { id: "aircraft", label: "Aircraft" },
];

export const typeLabel = (t: string): string => TYPES.find((x) => x.id === t)?.label ?? t;

const MS = 86400000;
const ms = (iso: string): number => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
const iso = (t: number): string => new Date(t).toISOString().slice(0, 10);

/** Designations per day for the last `days` days ending at `today` (oldest first): the sparkline of a country or of all. */
export function dailyCounts(rows: SanctionsRow[], today: string, days = 30): number[] {
  const out = new Array<number>(days).fill(0);
  for (const r of rows) {
    if (r.action !== "designated") continue;
    const i = days - 1 - Math.round((ms(today) - ms(r.on_date)) / MS);
    if (i >= 0 && i < days) out[i] += 1;
  }
  return out;
}

export type CountryCount = { iso: string; designated: number; delisted: number; spark: number[] };

/** Per-country totals (a party with several countries counts once in each), most designations first. */
export function byCountry(rows: SanctionsRow[], today: string, days = 30): CountryCount[] {
  const groups = new Map<string, SanctionsRow[]>();
  for (const r of rows) for (const c of r.countries) groups.set(c, [...(groups.get(c) ?? []), r]);
  return Array.from(groups.entries())
    .map(([c, rs]) => ({
      iso: c,
      designated: rs.filter((r) => r.action === "designated").length,
      delisted: rs.filter((r) => r.action === "delisted").length,
      spark: dailyCounts(rs, today, days),
    }))
    .sort((a, b) => b.designated - a.designated || a.iso.localeCompare(b.iso));
}

export const addDaysIso = (d: string, n: number): string => iso(ms(d) + n * MS);

/** The one window every sanctions count uses (page, door hint, country panel). Collection began 2026-10-01, so the real span is shorter until day 90. */
export const SANCTIONS_WINDOW_DAYS = 90;
