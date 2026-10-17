import { dbRows } from "@/lib/store";

import { addDays, ahead, type CalendarRow } from "./calendar-shared";

export * from "./calendar-shared";

const KINDS = new Set(["election", "central_bank", "summit", "security_council", "opec", "deadline", "vote"]);

const valid = (r: CalendarRow): boolean => KINDS.has(r.kind) && /^\d{4}-\d{2}-\d{2}$/.test(r.on_date);

/** UTC today as YYYY-MM-DD (the calendar is dated in UTC, like the daily). */
export const todayIso = (): string => new Date().toISOString().slice(0, 10);

/** Active items from a week back (a running window may have started) to `days` ahead; [] without a database. Filtered to what is still ahead. */
export async function calendarItems(days = 45): Promise<CalendarRow[]> {
  const today = todayIso();
  const rows = await dbRows<CalendarRow>(
    "calendar_items",
    `select=*&active=eq.true&on_date=gte.${addDays(today, -7)}&on_date=lte.${addDays(today, days)}&order=on_date.asc&limit=600`,
  );
  return ahead(rows.filter(valid), today);
}

/** What is coming up that concerns one country (an actor page), soonest first. */
export async function calendarForCountry(iso: string, days = 120, limit = 6): Promise<CalendarRow[]> {
  if (!/^[A-Za-z]{2}$/.test(iso)) return [];
  const today = todayIso();
  const rows = await dbRows<CalendarRow>(
    "calendar_items",
    `select=*&active=eq.true&countries=cs.{${iso.toUpperCase()}}&on_date=gte.${addDays(today, -7)}&on_date=lte.${addDays(today, days)}&order=on_date.asc&limit=60`,
  );
  return ahead(rows.filter(valid), today).slice(0, limit);
}
