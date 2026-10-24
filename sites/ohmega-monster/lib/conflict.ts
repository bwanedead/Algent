import { tableDoc, TTL } from "@/lib/store";

import { addDaysIso, type ConflictDoc, type ConflictFacts, type ConflictRow, type GnssDoc, type GnssRow } from "./conflict-shared";

export * from "./conflict-shared";

// The attack log and the GPS-interference zones, read from the documents the server publishes (backend `conflict/publish.py`, `gnss/publish.py`):
// `conflict/recent.json` (the strongest events of 14 days plus the per-day counts of everything stored) and `gnss/latest.json` (the newest day). A country's
// own events (`conflict/country/<ISO>.json`) reach the country panel through the server-built country view (backend `views/country.py`), not here.
// Everything is [] / null when nothing is published, and a row that fails its own shape is dropped rather than shown.

const DAY = /^\d{4}-\d{2}-\d{2}$/;
const today = (): string => new Date().toISOString().slice(0, 10);

export const conflictDoc = (): Promise<ConflictDoc | null> => tableDoc<ConflictDoc>("conflict/recent.json", TTL.tables);
export const gnssDoc = (): Promise<GnssDoc | null> => tableDoc<GnssDoc>("gnss/latest.json", TTL.tables);

const validEvent = (r: ConflictRow): boolean => DAY.test(r.on_date) && typeof r.type === "string" && Array.isArray(r.urls) && Array.isArray(r.assets);

/** Events of the last `days` days (at most the document's window), newest first, strongest first within a day; [] without a document. */
export async function recentEvents(days = 14, limit = 1500): Promise<ConflictRow[]> {
  const doc = await conflictDoc();
  if (!doc) return [];
  const since = addDaysIso(today(), -days);
  return doc.rows
    .filter((r) => r.on_date >= since)
    .map((r) => ({ ...r, coverage_note: doc.coverage[r.source] ?? "" }))
    .filter(validEvent)
    .slice(0, limit);
}

/** What the document says about itself: the whole stored window's size (not the rows carried), the day collection began, the per-day counts, which sources are live. */
export async function conflictFacts(): Promise<ConflictFacts | null> {
  const doc = await conflictDoc();
  if (!doc) return null;
  return { total: doc.total, shown: doc.shown, capped: doc.capped, days: doc.window_days, since: doc.since || null, asOf: doc.as_of, byDay: doc.by_day, sources: doc.sources };
}

/** The day we first stored an event ("collecting since"); null without data. */
export async function eventsSince(): Promise<string | null> {
  return (await conflictDoc())?.since || null;
}

/** The newest day's zones (ours first, then GPSJam's top band), each carrying its source's coverage note; null before any zone is published. */
export async function latestZones(): Promise<{ day: string; zones: GnssRow[]; baselineSince: string | null; baselineDays: number; history: GnssDoc["history"]; asOf: string } | null> {
  const doc = await gnssDoc();
  if (!doc || !DAY.test(doc.day)) return null;
  const valid = (r: GnssRow): boolean => DAY.test(r.on_date) && Number.isFinite(r.lat) && Number.isFinite(r.lon);
  const ours = doc.ours.map((r) => ({ ...r, coverage_note: doc.coverage.ohmega_adsb ?? "", baseline_since: doc.baseline_since || null }));
  const theirs = doc.gpsjam.map((r) => ({ ...r, coverage_note: doc.coverage.gpsjam ?? "", baseline_since: null }));
  return { day: doc.day, zones: [...ours, ...theirs].filter(valid), baselineSince: doc.baseline_since || null, baselineDays: doc.baseline_days, history: doc.history, asOf: doc.generated_at };
}
