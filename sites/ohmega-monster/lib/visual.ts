// Pure helpers for the site's visual language (app/visual.css, components/vl/*). No node imports: safe in client components.
// One place decides which category a story belongs to and how a quantity maps to a bar, so every surface draws the same picture.

export type Category = "conflict" | "economy" | "politics" | "energy" | "disaster";
export const CATEGORY_LABEL: Record<Category, string> = { conflict: "Conflict", economy: "Economy", politics: "Politics", energy: "Energy", disaster: "Disaster" };

// The first matching group wins; order is most specific first. A reading aid for a glyph and a tint, never a claim:
// anything unmatched is "politics", the broad default for state affairs.
const RULES: [Category, RegExp][] = [
  ["disaster", /\b(earthquake|quake|flood|hurricane|typhoon|cyclone|wildfire|drought|famine|outbreak|epidemic|volcano|tsunami|disaster)\b/i],
  ["energy", /\b(oil|gas|lng|opec|pipeline|refiner\w*|hormuz|tanker|nuclear power|power grid|electricity|energy|fuel)\b/i],
  ["conflict", /\b(war|strikes?|missiles?|military|ceasefire|troops|invasion|attack\w*|drone|armed|battle|insurgen\w*|houthi|confrontation|standoff|nuclear)\b/i],
  ["economy", /\b(tariffs?|trade|sanctions?|economy|economic|market|inflation|debt|bank|currency|chips?|semiconductor|export controls?|supply chain)\b/i],
];

/** The category a theater or story reads as, from the words that name it. */
export function categoryOf(...texts: string[]): Category {
  const s = texts.join(" ");
  for (const [c, re] of RULES) if (re.test(s)) return c;
  return "politics";
}

/** A value as 0..1 of the largest value shown, so bars on one screen share one scale (position on a common scale). */
export function shareOfMax(value: number, max: number): number {
  return max > 0 && Number.isFinite(value) ? Math.min(1, Math.max(0, value / max)) : 0;
}

/** Leading number of a hint ("12 theaters · 3 escalating" -> { n: "12", rest: "theaters · 3 escalating" }); n is "" when it has none. */
export function splitHint(hint: string): { n: string; rest: string } {
  const m = /^(\d[\d,]*)\s+(.*)$/.exec(hint.trim());
  return m ? { n: m[1], rest: m[2] } : { n: "", rest: hint.trim() };
}

/** Freshness of a timestamp for a status dot. The live feeds refresh about every minute, so a quarter hour is already worth a note. */
const FRESH_MIN = 15;
const AGING_MIN = 120;
export function freshnessOf(iso: string | null | undefined, nowMs: number): "fresh" | "aging" | "stale" {
  const t = iso ? Date.parse(iso) : NaN;
  if (!Number.isFinite(t)) return "stale";
  const min = (nowMs - t) / 60000;
  return min < FRESH_MIN ? "fresh" : min < AGING_MIN ? "aging" : "stale";
}
