import { tableDoc, TTL } from "@/lib/store";

import { addDays, ahead, KINDS as KIND_LIST, norm, type CalendarRow } from "./calendar-shared";

export * from "./calendar-shared";

// The forward calendar, read from one published file (backend `lookahead/publish.py`): `calendar/next.json` holds the active items from 14 days
// back to 180 ahead, already merged across sources and ranked. Every window the calendar pages ask for is cut from it here (a country's own rows
// are also published as `calendar/country/<ISO>.json`, and cut by the server into the country view, backend `views/country.py`). [] when nothing is published.

const KINDS = new Set<string>(KIND_LIST.map((k) => k.id));

const valid = (r: CalendarRow): boolean => KINDS.has(r.kind) && r.active !== false && /^\d{4}-\d{2}-\d{2}$/.test(r.on_date);

/** UTC today as YYYY-MM-DD (the calendar is dated in UTC, like the daily). */
export const todayIso = (): string => new Date().toISOString().slice(0, 10);

async function items(): Promise<Required<CalendarRow>[]> {
  const doc = await tableDoc<{ items?: CalendarRow[] }>("calendar/next.json", TTL.tables);
  return (doc?.items ?? []).filter(valid).map(norm);
}

/** Active items still ahead of (or running on) today, up to `days` on, soonest first. Routine items (importance 1) are included: callers that want
 *  the notable ones filter on `importance`. */
export async function calendarItems(days = 45): Promise<Required<CalendarRow>[]> {
  const today = todayIso();
  const hi = addDays(today, days);
  return ahead((await items()).filter((r) => r.on_date <= hi), today) as Required<CalendarRow>[];
}

/** The whole published window, past 14 days included (context for the /calendar page), soonest first. */
export async function calendarWindow(): Promise<Required<CalendarRow>[]> {
  return (await items()).sort((a, b) => a.on_date.localeCompare(b.on_date) || b.importance - a.importance || a.title.localeCompare(b.title));
}
