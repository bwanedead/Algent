import { dbRows } from "@/lib/store";

import { addDaysIso, type ConflictRow, type GnssRow } from "./conflict-shared";

export * from "./conflict-shared";

const today = (): string => new Date().toISOString().slice(0, 10);
const DAY = /^\d{4}-\d{2}-\d{2}$/;
const validEvent = (r: ConflictRow): boolean => DAY.test(r.on_date) && typeof r.type === "string";
const validZone = (r: GnssRow): boolean => DAY.test(r.on_date) && Number.isFinite(r.lat) && Number.isFinite(r.lon);

/** Events of the last `days` days, newest first, most-reported first within a day; [] without a database. */
export async function recentEvents(days = 14, limit = 1500): Promise<ConflictRow[]> {
  const rows = await dbRows<ConflictRow>("conflict_events", `select=*&on_date=gte.${addDaysIso(today(), -days)}&order=on_date.desc,articles.desc&limit=${limit}`);
  return rows.filter(validEvent);
}

/** Recent events that concern one country (an actor page, a HUD country panel). */
export async function eventsForCountry(iso: string, days = 30, limit = 200): Promise<ConflictRow[]> {
  if (!/^[A-Za-z]{2}$/.test(iso)) return [];
  const rows = await dbRows<ConflictRow>("conflict_events", `select=*&country=eq.${iso.toUpperCase()}&on_date=gte.${addDaysIso(today(), -days)}&order=on_date.desc,articles.desc&limit=${limit}`);
  return rows.filter(validEvent);
}

/** The day we first stored an event we published (an upper bound of "collecting since": the local record may start earlier). Null without data. */
export async function eventsSince(): Promise<string | null> {
  const rows = await dbRows<{ observed_at: string }>("conflict_events", "select=observed_at&order=observed_at.asc&limit=1");
  return rows[0]?.observed_at?.slice(0, 10) ?? null;
}

/** Interference zones of the last `days` days (both sources), newest first, strongest first within a day. */
export async function recentZones(days = 14, limit = 3000): Promise<GnssRow[]> {
  const rows = await dbRows<GnssRow>("gnss_zones", `select=*&on_date=gte.${addDaysIso(today(), -days)}&order=on_date.desc,degraded_share.desc&limit=${limit}`);
  return rows.filter(validZone);
}

/** The newest day that has zones, and its zones. */
export async function latestZones(): Promise<{ day: string; zones: GnssRow[] } | null> {
  const rows = await recentZones(7);
  if (rows.length === 0) return null;
  const day = rows[0].on_date;
  return { day, zones: rows.filter((r) => r.on_date === day) };
}
