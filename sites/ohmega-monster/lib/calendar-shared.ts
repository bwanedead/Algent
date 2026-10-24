// The forward calendar, as data: types of the `calendar_items` rows (backend `lookahead/`, migration 012), the kinds with their glyph and
// label, and the pure date helpers the /calendar page and the "Coming up" strips share. No I/O and no node imports, so a client component
// may import this file. The server-side reads live in lib/calendar.ts.

import type { GlyphName } from "@/components/vl/Glyph";

export type CalendarKind =
  | "election" | "central_bank" | "summit" | "security_council" | "opec" | "deadline" | "vote"
  | "data_release" | "commodity_report" | "conference" | "earnings" | "regulation" | "launch" | "court" | "market_resolves";

/** The topic chips of /calendar (backend `lookahead/contracts.py` TOPIC_OF). */
export type CalendarTopic = "economy" | "central_banks" | "elections" | "diplomacy" | "security" | "energy" | "tech" | "space" | "markets";
/** Trust, four levels: official schedule, announced (compiled or company-confirmed), estimated (a rule or projection), unconfirmed (our own reading). */
export type CalendarGrade = "official" | "announced" | "estimated" | "unconfirmed";

/** One row of `calendar/next.json`. `end_date` is null for a single day; extracted items (`source` "corpus") are low confidence and ours.
 *  The last five fields are additive (contract ohmega.calendar stays major 1): a document written before them lacks them, so readers go through `norm`. */
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
  situations?: string[];
  grade?: CalendarGrade;
  topic?: CalendarTopic;
  importance?: number;
  sources?: { source: string; url: string }[];
};

/** The few fields a compact "coming up" line needs; a CalendarRow and a daily's stored `coming_up` row both satisfy it after `toComing`. */
export type ComingRow = { date: string; end_date: string; title: string; kind: CalendarKind; countries: string[]; confidence: "high" | "medium" | "low"; url: string; ours: boolean };

// ---- the title-date guard ---------------------------------------------------------------------------------------------------
// Extracted items (source "corpus") are read from our own text and can be mis-dated: an item dated 21 Oct whose title says "Oct. 19" is an
// extraction error. A date written in a title that falls on none of the days the item covers marks it unconfirmed, whoever supplied it.

const MON = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
const MONTH_DAY = [/\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?!\d)/gi, /\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*/gi];

/** True when `title` names a month and day that none of the item's covered days (`start` to `end`, up to 14) falls on. False when it names none. */
export function titleDateConflict(title: string, start: string, end: string | null): boolean {
  const named = new Set<string>();
  MONTH_DAY.forEach((re, i) => {
    for (const m of title.matchAll(re)) named.add(`${MON.indexOf((i === 0 ? m[1] : m[2]).toLowerCase())}-${Number(i === 0 ? m[2] : m[1])}`);
  });
  if (named.size === 0) return false;
  const covered = spans({ on_date: start, end_date: end }).map((d) => `${+d.slice(5, 7) - 1}-${+d.slice(8, 10)}`);
  return !covered.some((c) => named.has(c));
}

/** Not an official schedule: extracted from our own reports (source "corpus"), or its title disagrees with its date. Shown as "unconfirmed". */
export const isUnconfirmed = (r: { source: string; title: string; on_date: string; end_date: string | null; grade?: string }): boolean =>
  r.source === "corpus" || r.grade === "unconfirmed" || titleDateConflict(r.title, r.on_date, r.end_date);

export const toComing = (r: CalendarRow): ComingRow => ({
  date: r.on_date, end_date: r.end_date ?? "", title: r.title, kind: r.kind, countries: r.countries, confidence: r.confidence, url: r.source_url, ours: isUnconfirmed(r),
});

export const KINDS: { id: CalendarKind; label: string; glyph: GlyphName }[] = [
  { id: "election", label: "Election", glyph: "country" },
  { id: "vote", label: "Vote", glyph: "ballot" },
  { id: "central_bank", label: "Central bank", glyph: "bank" },
  { id: "summit", label: "Summit or talks", glyph: "politics" },
  { id: "security_council", label: "UN Security Council", glyph: "globe" },
  { id: "opec", label: "OPEC+", glyph: "energy" },
  { id: "deadline", label: "Deadline or expiry", glyph: "clock" },
  { id: "data_release", label: "Data release", glyph: "economy" },
  { id: "commodity_report", label: "Commodity report", glyph: "plant" },
  { id: "conference", label: "Conference", glyph: "event" },
  { id: "earnings", label: "Earnings", glyph: "record" },
  { id: "regulation", label: "Regulation milestone", glyph: "article" },
  { id: "launch", label: "Launch", glyph: "up" },
  { id: "court", label: "Court hearing or ruling", glyph: "sanction" },
  { id: "market_resolves", label: "Market resolves", glyph: "pulse" },
];

export const kindOf = (k: string) => KINDS.find((x) => x.id === k) ?? KINDS.find((x) => x.id === "deadline")!;

export const TOPICS: { id: CalendarTopic; label: string }[] = [
  { id: "economy", label: "Economy" },
  { id: "central_banks", label: "Central banks" },
  { id: "elections", label: "Elections" },
  { id: "diplomacy", label: "Diplomacy" },
  { id: "security", label: "Security" },
  { id: "energy", label: "Energy and commodities" },
  { id: "tech", label: "AI and tech" },
  { id: "space", label: "Space" },
  { id: "markets", label: "Markets" },
];

const TOPIC_OF: Record<CalendarKind, CalendarTopic> = {
  election: "elections", vote: "elections", central_bank: "central_banks", data_release: "economy", commodity_report: "energy", opec: "energy",
  summit: "diplomacy", court: "diplomacy", security_council: "security", deadline: "diplomacy", conference: "tech", earnings: "tech",
  regulation: "tech", launch: "space", market_resolves: "markets",
};
const GRADE_OF = { high: "official", medium: "announced", low: "unconfirmed" } as const;

/** A row with every additive field present (documents written before them lack them): topic from the kind, grade from the confidence, importance 2. */
export function norm(r: CalendarRow): Required<CalendarRow> {
  return {
    ...r,
    situations: r.situations ?? [],
    grade: r.grade ?? GRADE_OF[r.confidence] ?? "announced",
    topic: r.topic ?? TOPIC_OF[r.kind] ?? "diplomacy",
    importance: r.importance === 1 || r.importance === 2 || r.importance === 3 ? r.importance : 2,
    sources: r.sources && r.sources.length > 0 ? r.sources : [{ source: r.source, url: r.source_url }],
  };
}

export const IMPORTANCE_WORD = ["", "routine", "notable", "major"] as const;
export const GRADE_WORD: Record<CalendarGrade, string> = {
  official: "official schedule", announced: "announced", estimated: "estimated from a rule or projection", unconfirmed: "unconfirmed (our own reading)",
};

/** "sit_russia_nato" -> "Russia nato": the situation id as a label (the rows carry ids, not titles). */
export const situationLabel = (id: string): string => {
  const t = id.replace(/^sit_/, "").replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
};

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

/** Who published it, in words (the collector's source key -> a name a reader knows). */
const SOURCE_LABEL: Record<string, string> = {
  fed: "Federal Reserve", ecb: "ECB", boe: "Bank of England", boj: "Bank of Japan", rba: "Reserve Bank of Australia", norges: "Norges Bank", pboc: "PBoC (rule)",
  bea: "BEA", bls_jobs: "BLS (rule)", wasde: "USDA", eia_petroleum: "EIA", eia_gas: "EIA", opec: "OPEC", elections: "Wikipedia electoral calendar",
  unsc: "UN Security Council", unsc_presidency: "UN Security Council", icj: "ICJ", summits: "Wikipedia", ai_act: "AI Act timeline", gtc: "NVIDIA",
  earnings: "Nasdaq earnings calendar", launches: "Launch Library 2", markets: "Ohmega markets", watches: "Ohmega situations", corpus: "Ohmega report",
};
export const sourceLabel = (s: string): string => SOURCE_LABEL[s] ?? s;

/** Rows by the days they cover (a window sits on every day it spans). */
export function indexByDay<T extends { on_date: string; end_date: string | null }>(rows: T[]): Map<string, T[]> {
  const out = new Map<string, T[]>();
  for (const r of rows) for (const d of spans(r)) out.set(d, [...(out.get(d) ?? []), r]);
  return out;
}

export type CalFilter ={ topics: ReadonlySet<CalendarTopic>; country: string; situation: string; routine: boolean };
export const NO_FILTER: CalFilter = { topics: new Set(), country: "", situation: "", routine: false };

/** Rows that pass a filter: any chosen topic (none chosen = all), the country, the situation, and, unless `routine` or the row's topic chip is chosen, importance above 1. */
export function filterRows(rows: Required<CalendarRow>[], f: CalFilter): Required<CalendarRow>[] {
  return rows.filter(
    (r) => (f.topics.size === 0 || f.topics.has(r.topic)) && (!f.country || r.countries.includes(f.country)) && (!f.situation || r.situations.includes(f.situation)) && (f.routine || r.importance > 1 || f.topics.has(r.topic)),   // choosing a topic chip shows its routine rows too (e.g. Markets: ~350 resolution dates)
  );
}

/** The strip "on the horizon": rows that start from `today` up to three days on (72 hours), or are running now, most important first within a day. */
export function horizon(rows: Required<CalendarRow>[], today: string, days = 3): Required<CalendarRow>[] {
  const last = addDays(today, days);
  return rows
    .filter((r) => r.on_date <= last && (r.end_date ?? r.on_date) >= today)
    .sort((a, b) => a.on_date.localeCompare(b.on_date) || b.importance - a.importance || a.title.localeCompare(b.title));
}

export type MonthCell = { date: string; inMonth: boolean; items: Required<CalendarRow>[] };

/** Monday-first weeks covering the month of `anchor` (any day in it); each item sits on every day it covers, at most `max` per cell, most important first. */
export function monthGrid(rows: Required<CalendarRow>[], anchor: string): { label: string; weeks: MonthCell[][] } {
  const first = `${anchor.slice(0, 7)}-01`;
  const next = isoOf(Date.UTC(+anchor.slice(0, 4), +anchor.slice(5, 7), 1));
  const end = addDays(next, -1);
  const byDay = new Map<string, Required<CalendarRow>[]>();
  for (const r of rows) for (const d of spans(r)) byDay.set(d, [...(byDay.get(d) ?? []), r]);
  const weeksOut: MonthCell[][] = [];
  for (let s = weekStart(first); s <= end; s = addDays(s, 7)) {
    weeksOut.push(Array.from({ length: 7 }, (_, i) => {
      const date = addDays(s, i);
      return { date, inMonth: date.slice(0, 7) === first.slice(0, 7), items: (byDay.get(date) ?? []).slice().sort((a, b) => b.importance - a.importance || a.title.localeCompare(b.title)) };
    }));
  }
  const names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  return { label: `${names[+first.slice(5, 7) - 1]} ${first.slice(0, 4)}`, weeks: weeksOut };
}

/** The first day of the month `n` months from the month of `iso`. */
export const addMonths = (iso: string, n: number): string => isoOf(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1 + n, 1));

export const confidenceWord = (c: string, ours: boolean): string =>
  ours ? "from our own earlier report, unconfirmed" : c === "high" ? "official schedule" : c === "medium" ? "compiled from announcements" : "low confidence";
