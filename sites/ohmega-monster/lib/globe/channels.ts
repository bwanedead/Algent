// Information channels for the globe: the compact per-country row the server hands the viewer, and how each channel sorts a country
// into a fill bucket (a CSS class). Pure TS and client-safe (the server-side builder is lib/globe-data.ts).

import { bandOf, BAND_LABELS, THEMES, type Theme } from "./themes";

export type Dir = "rising" | "steady" | "easing" | "unclear";

/** One country's row. `t` is the unix second of the newest item naming it (daily, sanction, anomaly); bands are computed against the
 *  viewer's clock, so a page left open ages honestly. */
export type CountryRow = {
  n: number; //          theaters the country is tied to
  dir: Dir | null; //    the moving direction across those theaters (rising beats steady beats easing); null: none
  t: number | null; //   newest mention, unix seconds; null: nothing in the window
  th: Theme | null; //   dominant theme of what is new there (rule in lib/globe/themes.ts)
  hot: number; //        live anomalies going on there now
};

export type ChannelId = "theme" | "recency" | "direction" | "involvement" | "unusual" | "off";

export type LegendItem = { label: string; cls: string; n: number };
export type Legend = { hues: LegendItem[]; items: LegendItem[] };

export type Channel = {
  id: ChannelId;
  label: string;
  /** One line under the legend: what the colour means. */
  note: string;
};

export const CHANNELS: readonly Channel[] = [
  { id: "theme", label: "Theme × recency", note: "Hue: what is new there. Strength: how recently. Amber edge: escalating; green edge: easing." },
  { id: "recency", label: "Recency", note: "How recently anything named the country." },
  { id: "direction", label: "Direction", note: "Where its theaters are heading." },
  { id: "involvement", label: "Involvement", note: "How many theaters it is part of." },
  { id: "unusual", label: "Anomalies", note: "Live sensors outside their learned normal." },
  { id: "off", label: "Plain", note: "" },
];

const DIR_BUCKET: Record<Dir, number> = { rising: 0, steady: 1, easing: 2, unclear: 3 };
const DIR_LABELS = ["Escalating", "Steady", "Easing", "Unclear"];
const INV_LABELS = ["1 theater", "2 theaters", "3 theaters", "4 or more"];
const HOT_LABELS = ["1 anomaly", "2 anomalies", "3 or more"];
const themeIx = (t: Theme | null): number => THEMES.findIndex((x) => x.id === t);

/** Fill bucket of a row for a channel (-1: no fill). Theme channel: theme index * 3 + band. */
export function bucketOf(ch: ChannelId, r: CountryRow | undefined, nowMs: number): number {
  if (!r) return -1;
  switch (ch) {
    case "theme": {
      const band = bandOf(r.t, nowMs), th = themeIx(r.th);
      return band < 0 || th < 0 ? -1 : th * 3 + band;
    }
    case "recency":
      return bandOf(r.t, nowMs);
    case "direction":
      return r.dir === null ? -1 : DIR_BUCKET[r.dir];
    case "involvement":
      return r.n <= 0 ? -1 : Math.min(r.n, 4) - 1;
    case "unusual":
      return r.hot <= 0 ? -1 : Math.min(r.hot, 3) - 1;
    default:
      return -1;
  }
}

/** Number of buckets a channel can produce (the viewer keeps one path per bucket). */
export const bucketCount = (ch: ChannelId): number => (ch === "theme" ? THEMES.length * 3 : ch === "recency" ? 3 : ch === "off" ? 0 : ch === "direction" ? 4 : ch === "involvement" ? 4 : 3);

/** CSS classes of a bucket's path and legend swatch. Theme: `gv-th gv-t-<theme> gv-r<band>`; other channels: `gv-b<bucket>`. */
export function bucketClass(ch: ChannelId, b: number): string {
  if (ch === "theme") return `gv-th gv-t-${THEMES[Math.floor(b / 3)].id} gv-r${b % 3}`;
  if (ch === "recency") return `gv-th gv-t-ink gv-r${b}`;
  return `gv-b${b}`;
}

/** The always-visible legend for a channel: hue chips (theme only) and the bands/buckets, each with how many countries fall in it. */
export function legendOf(ch: ChannelId, buckets: number[]): Legend {
  const count = (pred: (b: number) => boolean) => buckets.filter((b) => b >= 0 && pred(b)).length;
  switch (ch) {
    case "theme":
      return {
        hues: THEMES.map((t, i) => ({ label: t.label, cls: `gv-th gv-t-${t.id} gv-r0`, n: count((b) => Math.floor(b / 3) === i) })),
        items: BAND_LABELS.map((label, band) => ({ label, cls: `gv-th gv-t-ink gv-r${band}`, n: count((b) => b % 3 === band) })),
      };
    case "recency":
      return { hues: [], items: BAND_LABELS.map((label, band) => ({ label, cls: bucketClass(ch, band), n: count((b) => b === band) })) };
    case "direction":
      return { hues: [], items: DIR_LABELS.map((label, b) => ({ label, cls: bucketClass(ch, b), n: count((x) => x === b) })) };
    case "involvement":
      return { hues: [], items: INV_LABELS.map((label, b) => ({ label, cls: bucketClass(ch, b), n: count((x) => x === b) })) };
    case "unusual":
      return { hues: [], items: HOT_LABELS.map((label, b) => ({ label, cls: bucketClass(ch, b), n: count((x) => x === b) })) };
    default:
      return { hues: [], items: [] };
  }
}

/** The channel set the page offers: "Anomalies" only when something is unusual right now. */
export const availableChannels = (rows: Record<string, CountryRow>): Channel[] => {
  const anyHot = Object.values(rows).some((r) => r.hot > 0);
  return CHANNELS.filter((c) => c.id !== "unusual" || anyHot);
};
