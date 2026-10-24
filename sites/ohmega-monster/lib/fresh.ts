// Freshness: how old a product is, in words, and whether that is late for the product's OWN cadence. Pure functions, safe in
// server and client code. A stamp is either a full ISO time ("2026-10-20T05:30:00Z") or a bare day ("2026-10-20"); a bare day
// is read at day granularity ("today", "yesterday", "17 days ago") because that is all it knows.

const HOUR = 3_600_000;
const DAY = 24 * HOUR;

/** How often each kind of product is meant to refresh, in hours (docs/architecture/information-architecture.md §1, site-inventory A0).
 *  A product is "stale" once it is twice this old: late for what it is, not old by some single magic number. */
export const CADENCE_HOURS = {
  daily: 24, // geopolitics twice a day, AI once; judged by the day
  headlines: 24,
  situation: 72, // updates only on days a daily writes it up, so quiet stretches of a few days are normal
  article: 14 * 24, // run by hand, irregular
  pulses: 48,
  forecasts: 7 * 24, // brief judgments are written by hand
  track: 24, // markets mirror daily
  benchmarks: 24,
  sanctions: 24,
  calendar: 24,
  maritime: 24,
  attacks: 1, // GDELT files land every 15 minutes
  gnss: 2, // one ADS-B pass an hour
  statements: 24,
  actors: 30 * 24, // profiles are slow data, refreshed by hand
  live: 1,
  graph: 72,
} as const;

export type Cadence = keyof typeof CADENCE_HOURS;

const isDayOnly = (s: string): boolean => /^\d{4}-\d{2}-\d{2}$/.test(s);

/** Milliseconds since the stamp, or null when it cannot be read (or is in the future by more than a clock-skew minute). */
export function ageMs(stamp: string, now: number = Date.now()): number | null {
  if (!stamp) return null;
  const t = Date.parse(isDayOnly(stamp) ? `${stamp}T00:00:00Z` : stamp);
  if (Number.isNaN(t)) return null;
  const startOfToday = Math.floor(now / DAY) * DAY;
  // A bare day is measured from the start of today, so a report dated today is 0 days old whatever the hour.
  const age = isDayOnly(stamp) ? Math.max(0, startOfToday - t) : now - t;
  return age < -60_000 ? null : Math.max(0, age);
}

/** "just now", "2 h ago", "yesterday", "17 days ago", "3 months ago"; "" when the stamp is unreadable. */
export function ageLabel(stamp: string, now: number = Date.now()): string {
  const a = ageMs(stamp, now);
  if (a === null) return "";
  if (isDayOnly(stamp)) {
    const d = Math.round(a / DAY);
    return d === 0 ? "today" : d === 1 ? "yesterday" : d < 60 ? `${d} days ago` : `${Math.round(d / 30)} months ago`;
  }
  const h = a / HOUR;
  if (h < 1) return a < 5 * 60_000 ? "just now" : `${Math.round(a / 60_000)} min ago`;
  if (h < 24) return `${Math.round(h)} h ago`;
  const d = Math.round(a / DAY);
  return d === 1 ? "yesterday" : d < 60 ? `${d} days ago` : `${Math.round(d / 30)} months ago`;
}

/** Late for its own cadence: older than twice the hours it is meant to refresh in. Unreadable stamps are not "stale", they are unknown. */
export function isStale(stamp: string, cadenceHours: number, now: number = Date.now()): boolean {
  const a = ageMs(stamp, now);
  return a !== null && a > 2 * cadenceHours * HOUR;
}

/** The stamp of the newest of several (ISO strings and bare days compare correctly as text when mixed within a kind); "" when none. */
export const newest = (stamps: string[]): string => stamps.filter(Boolean).reduce((a, b) => (b > a ? b : a), "");
