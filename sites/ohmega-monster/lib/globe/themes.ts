// Themes and recency bands for the globe's default channel ("Theme x recency"). Pure TS, client-safe.
//
// THEME RULE (applied per country on the server, lib/globe-data.ts): every item that names the country in the window (daily sections,
// developments, sanctions events, calendar items, live anomalies) is classified into one theme and adds a weight to that theme's tally:
//   weight = base * 0.5 ^ (ageDays / 7)       (a half-life of a week, so the most recent items outweigh a pile of old ones)
// base is 1 for a keyword-classified text, 0.5 for a text that matched nothing and fell to the "politics" default, and 0.5 for an
// upcoming calendar item. The country's theme is the tally's maximum; ties go to the order of THEMES. Classification is a reading aid,
// not a claim (same stance as lib/visual.ts categoryOf, which it extends with "tech").
//
// RECENCY BANDS (clock-relative, computed in the browser): < 24 h, <= 7 d, <= 30 d, older/none (no fill).

import { categoryOf, type Category } from "../visual";

export type Theme = Category | "tech";

/** Order is the tie-break order and the legend order. `css` names the colour token: the visual-language category tokens, plus --gv-tech. */
export const THEMES: { id: Theme; label: string }[] = [
  { id: "conflict", label: "Conflict" },
  { id: "economy", label: "Economy and trade" },
  { id: "energy", label: "Energy" },
  { id: "politics", label: "Politics and diplomacy" },
  { id: "tech", label: "Tech and cyber" },
  { id: "disaster", label: "Disaster and humanitarian" },
];

const TECH_RE = /\b(cyber\w*|hack\w*|ransomware|malware|breach|ai|artificial intelligence|semiconductors?|chips?|satellites?|spyware|telecom\w*|5g|data centers?|quantum|surveillance tech|internet shutdown)\b/i;
const POLITICS_RE = /\b(election\w*|vote\w*|summit|talks|diplomat\w*|minister\w*|treaty|parliament|president\w*|government|coalition|alliance|embassy|envoy|protest\w*|coup|referendum)\b/i;
const DISASTER_EXTRA_RE = /\b(refugees?|humanitarian|displaced|aid|cholera|earthquake|flood\w*)\b/i;

/** Theme of a text plus its base weight (see the rule above). */
export function themeOf(...texts: string[]): { theme: Theme; base: number } {
  const s = texts.join(" ");
  if (TECH_RE.test(s)) return { theme: "tech", base: 1 };
  if (DISASTER_EXTRA_RE.test(s)) return { theme: "disaster", base: 1 };
  const c = categoryOf(s);
  return { theme: c, base: c === "politics" && !POLITICS_RE.test(s) ? 0.5 : 1 };
}

export const HALF_LIFE_DAYS = 7;
export const decay = (ageDays: number): number => Math.pow(0.5, Math.max(0, ageDays) / HALF_LIFE_DAYS);

/** Recency band: 0 = under 24 h, 1 = up to 7 days, 2 = up to 30 days, -1 = older or never. `tSec` is unix seconds. */
export function bandOf(tSec: number | null, nowMs: number): number {
  if (tSec === null) return -1;
  const h = (nowMs - tSec * 1000) / 3600000;
  return h < 24 ? 0 : h <= 168 ? 1 : h <= 720 ? 2 : -1;
}

export const BAND_LABELS = ["Under 24 hours", "Up to 7 days", "Up to 30 days"] as const;
