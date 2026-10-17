// The forward calendar, as data: types of the `calendar_items` rows (backend `lookahead/`, migration 012), the kinds with their glyph and
// label, and the pure date helpers the /calendar page and the "Coming up" strips share. No I/O and no node imports, so a client component
// may import this file. The server-side reads live in lib/calendar.ts.

import type { GlyphName } from "@/components/vl/Glyph";

export type CalendarKind = "election" | "central_bank" | "summit" | "security_council" | "opec" | "deadline" | "vote";

/** One row of `calendar_items`. `end_date` is null for a single day; extracted items (`source` "corpus") are low confidence and ours. */
export type CalendarRow = {
  id: string;
  on_date: string;
  end_date: string | null;
  title: string;
  kind: CalendarKind;
  countries: string[];
  theaters: string[];
  source: string;
  source_url: string;
  confidence: "high" | "medium" | "low";
  provenance: "aggregated" | "ohmega_derived";
  via: string;
  active: boolean;
};

/** The few fields a compact "coming up" line needs; a CalendarRow and a daily's stored `coming_up` row both satisfy it after `toComing`. */
export type ComingRow = { date: string; end_date: string; title: string; kind: CalendarKind; countries: string[]; confidence: "high" | "medium" | "low"; url: string; ours: boolean };

export const toComing = (r: CalendarRow): ComingRow => ({
  date: r.on_date, end_date: r.end_date ?? "", title: r.title, kind: r.kind, countries: r.countries, confidence: r.confidence, url: r.source_url, ours: r.source === "corpus",
});

export const KINDS: { id: CalendarKind; label: string; glyph: GlyphName }[] = [
  { id: "election", label: "Election", glyph: "country" },
  { id: "vote", label: "Vote", glyph: "ballot" },
  { id: "central_bank", label: "Central bank", glyph: "bank" },
  { id: "summit", label: "Summit or talks", glyph: "politics" },
  { id: "security_council", label: "UN Security Council", glyph: "globe" },
  { id: "opec", label: "OPEC+", glyph: "energy" },
  { id: "deadline", label: "Deadline or expiry", glyph: "clock" },
];

export const kindOf = (k: string) => KINDS.find((x) => x.id === k) ?? KINDS[KINDS.length - 1];

// ---- dates (ISO YYYY-MM-DD, UTC, string arithmetic through Date.UTC so a viewer's timezone never shifts a day) ------------------------------------

const MS = 86400000;
const t = (iso: string): number => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
export const isoOf = (ms: number): string => new Date(ms).toISOString().slice(0, 10);
export const addDays = (iso: string, n: number): string => isoOf(t(iso) + n * MS);
export const daysBetween = (a: string, b: string): number => Math.round((t(b) - t(a)) / MS);
/** The Monday of the week holding `iso`. */
export const weekStart = (iso: string): string => addDays(iso, -((new Date(t(iso)).getUTCDay() + 6) % 7));

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const shortDate = (iso: string): string => `${+iso.slice(8, 10)} ${MONTHS[+iso.slice(5, 7) - 1]}`;
export const weekday = (iso: string): string => WEEKDAYS[new Date(t(iso)).getUTCDay()];

/** "today", "tomorrow", "in 5 days" — the distance in words, so a date is never read against the wrong day. */
export function untilWords(iso: string, today: string): string {
  const n = daysBetween(today, iso);
  return n <= 0 ? "today" : n === 1 ? "tomorrow" : `in ${n} days`;
}

/** The days an item covers (a window spans several; a single day is one). */
export const spans = (r: { on_date: string; end_date: string | null }): string[] => {
  const end = r.end_date && r.end_date > r.on_date ? r.end_date : r.on_date;
  return Array.from({ length: Math.min(daysBetween(r.on_date, end), 14) + 1 }, (_, i) => addDays(r.on_date, i));
};

/** Items still ahead of (or running on) `today`, soonest first. */
export function ahead(rows: CalendarRow[], today: string): CalendarRow[] {
  return rows
    .filter((r) => r.active && (r.end_date ?? r.on_date) >= today)
    .sort((a, b) => a.on_date.localeCompare(b.on_date) || a.kind.localeCompare(b.kind) || a.title.localeCompare(b.title));
}

export type Week = { start: string; days: { date: string; items: CalendarRow[] }[] };

/** The grid: Monday-first weeks from the week holding `today` through `days` days on; each item sits on every day it covers. */
export function weeks(rows: CalendarRow[], today: string, days: number): Week[] {
  const last = addDays(today, days);
  const out: Week[] = [];
  for (let s = weekStart(today); s <= last; s = addDays(s, 7)) {
    out.push({ start: s, days: Array.from({ length: 7 }, (_, i) => ({ date: addDays(s, i), items: [] as CalendarRow[] })) });
  }
  for (const r of rows) {
    for (const d of spans(r)) {
      const w = out.find((x) => d >= x.start && d <= addDays(x.start, 6));
      if (w) w.days[daysBetween(w.start, d)].items.push(r);
    }
  }
  return out;
}

/** Items per day for the density strip: `days` numbers starting at `today`. */
export function density(rows: CalendarRow[], today: string, days: number): number[] {
  const out = new Array<number>(days).fill(0);
  for (const r of rows) for (const d of spans(r)) {
    const i = daysBetween(today, d);
    if (i >= 0 && i < days) out[i] += 1;
  }
  return out;
}

/** The countries mentioned across rows, most frequent first. */
export function countriesOf(rows: CalendarRow[]): string[] {
  const n = new Map<string, number>();
  for (const r of rows) for (const c of r.countries) n.set(c, (n.get(c) ?? 0) + 1);
  return Array.from(n.entries()).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map((e) => e[0]);
}

export const confidenceWord = (c: string, ours: boolean): string =>
  ours ? "from our own earlier report, unconfirmed" : c === "high" ? "official schedule" : c === "medium" ? "compiled from announcements" : "low confidence";
