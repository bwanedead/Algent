import { tableDoc, TTL } from "@/lib/store";

import { addDays, ahead, type CalendarRow } from "./calendar-shared";

export * from "./calendar-shared";

// The forward calendar, read from one published file (backend `lookahead/publish.py`): `calendar/next.json` holds the active items from a
// week back to 120 days ahead. Every window the pages ask for is cut from it here. [] when nothing is published.

const KINDS = new Set(["election", "central_bank", "summit", "security_council", "opec", "deadline", "vote"]);

const valid = (r: CalendarRow): boolean => KINDS.has(r.kind) && r.active !== false && /^\d{4}-\d{2}-\d{2}$/.test(r.on_date);

/** UTC today as YYYY-MM-DD (the calendar is dated in UTC, like the daily). */
export const todayIso = (): string => new Date().toISOString().slice(0, 10);

async function items(): Promise<CalendarRow[]> {
  const doc = await tableDoc<{ items?: CalendarRow[] }>("calendar/next.json", TTL.tables);
  return (doc?.items ?? []).filter(valid);
}

/** Active items from a week back (a running window may have started) to `days` ahead. Filtered to what is still ahead. */
export async function calendarItems(days = 45): Promise<CalendarRow[]> {
  const today = todayIso();
  const hi = addDays(today, days);
  return ahead((await items()).filter((r) => r.on_date <= hi), today);
}

/** What is coming up that concerns one country (an actor page), soonest first. */
export async function calendarForCountry(iso: string, days = 120, limit = 6): Promise<CalendarRow[]> {
  if (!/^[A-Za-z]{2}$/.test(iso)) return [];
  const today = todayIso();
  const hi = addDays(today, days);
  const code = iso.toUpperCase();
  return ahead((await items()).filter((r) => r.on_date <= hi && r.countries.includes(code)), today).slice(0, limit);
}
