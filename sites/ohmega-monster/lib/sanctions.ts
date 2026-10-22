import { tableDoc, TTL } from "@/lib/store";

import { addDaysIso, type SanctionsRow } from "./sanctions-shared";

export * from "./sanctions-shared";

// Sanctions designations, read from published files (backend `sanctions/publish.py`): `sanctions/recent.json` holds the last 180 days, and
// `sanctions/country/<ISO>.json` one country's, so an actor page fetches only its own file. [] when nothing is published.

const SOURCES = new Set(["ofac", "uk", "eu"]);
const valid = (r: SanctionsRow): boolean => SOURCES.has(r.source) && (r.action === "designated" || r.action === "delisted") && /^\d{4}-\d{2}-\d{2}$/.test(r.on_date);

const today = (): string => new Date().toISOString().slice(0, 10);

const newestFirst = (a: SanctionsRow, b: SanctionsRow): number => b.on_date.localeCompare(a.on_date) || b.observed_on.localeCompare(a.observed_on);

/** Designations and delistings of the last `days` days (at most 180 are published), newest first. */
export async function recentSanctions(days = 90, limit = 1500): Promise<SanctionsRow[]> {
  const doc = await tableDoc<{ rows?: SanctionsRow[] }>("sanctions/recent.json", TTL.tables);
  const since = addDaysIso(today(), -days);
  return (doc?.rows ?? []).filter((r) => valid(r) && r.on_date >= since).sort(newestFirst).slice(0, limit);
}

/** Recent events that name one country (an actor page), newest first. */
export async function sanctionsForCountry(iso: string, days = 180, limit = 200): Promise<SanctionsRow[]> {
  if (!/^[A-Za-z]{2}$/.test(iso)) return [];
  const doc = await tableDoc<{ rows?: SanctionsRow[] }>(`sanctions/country/${iso.toUpperCase()}.json`, TTL.tables);
  const since = addDaysIso(today(), -days);
  return (doc?.rows ?? []).filter((r) => valid(r) && r.on_date >= since).sort(newestFirst).slice(0, limit);
}
