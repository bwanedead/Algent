// Information channels for the globe: the compact per-country data the server hands the viewer, and how each channel sorts a country
// into a colour bucket. Pure TS and client-safe (the server-side builder lives in lib/globe-data.ts and imports these types).

export type Dir = "rising" | "steady" | "easing" | "unclear";

/** One country's row. `age` is days between its latest mention and the newest report (so it never depends on the clock). */
export type CountryRow = {
  n: number; //          theaters the country is tied to
  dir: Dir | null; //    the moving direction across those theaters (rising beats steady beats easing); null: none
  age: number | null; // days since a recent daily last named it; null: not in the recent dailies
  hot: number; //        live anomalies going on there now
};

export type ChannelId = "recency" | "direction" | "involvement" | "unusual" | "off";

export type Channel = {
  id: ChannelId;
  label: string;
  /** One line under the legend: what the colour means. */
  note: string;
  /** Legend entries in bucket order (bucket b is drawn with the CSS class gv-b{b}). */
  legend: string[];
};

export const CHANNELS: readonly Channel[] = [
  { id: "recency", label: "Recency", note: "How recently the daily reports last named the country.", legend: ["Newest report", "1 day before", "2–3 days before", "4–6 days before", "7+ days before"] },
  { id: "direction", label: "Direction", note: "Where its theaters are heading.", legend: ["Escalating", "Steady", "Easing", "Unclear"] },
  { id: "involvement", label: "Involvement", note: "How many theaters it is part of.", legend: ["1 theater", "2 theaters", "3 theaters", "4 or more"] },
  { id: "unusual", label: "Unusual", note: "Live sensors outside their learned normal.", legend: ["1 anomaly", "2 anomalies", "3 or more"] },
  { id: "off", label: "Plain", note: "", legend: [] },
];

const DIR_BUCKET: Record<Dir, number> = { rising: 0, steady: 1, easing: 2, unclear: 3 };

/** Which legend bucket a row falls in for a channel; -1 for "no data" (drawn as plain land). */
export function bucketOf(ch: ChannelId, r: CountryRow | undefined): number {
  if (!r) return -1;
  switch (ch) {
    case "recency":
      return r.age === null ? -1 : r.age <= 0 ? 0 : r.age === 1 ? 1 : r.age <= 3 ? 2 : r.age <= 6 ? 3 : 4;
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

/** The channel set the page offers: "Unusual" only when something is unusual right now. */
export const availableChannels = (rows: Record<string, CountryRow>): Channel[] => {
  const anyHot = Object.values(rows).some((r) => r.hot > 0);
  return CHANNELS.filter((c) => c.id !== "unusual" || anyHot);
};
