// The /live items: one plain record per event or ship-count, shared by the interactive map, its static fallback, the
// layer toggles, the card and the list under the map. Client-safe: imports only lib/live-shared (never lib/live or the store).

import { whenUtc, type LiveEvent, type LiveKind, type LiveStat } from "@/lib/live-shared";

export type Layer = LiveKind | "ships";

export type Item = {
  id: string;
  layer: Layer;
  title: string;
  detail: string;
  when: string;
  source: string;
  url: string;
  lat: number | null;
  lon: number | null;
  countries: string[];
  size: number;
  major: boolean;
  /** Ship counts: the strait's region slug (ties the item to its counting line) and a short on-map label. */
  region?: string;
  badge?: string;
};

export const LAYERS: { id: Layer; label: string; glyph: string }[] = [
  { id: "outage", label: "Internet outages", glyph: "■" },
  { id: "quake", label: "Earthquakes", glyph: "●" },
  { id: "aircraft", label: "Military aircraft", glyph: "▲" },
  { id: "fire", label: "Fire hotspots", glyph: "◆" },
  { id: "ships", label: "Ship traffic", glyph: "◎" },
];

export const safeUrl = (u: string) => (/^https?:\/\//.test(u) ? u : "");

export function eventItem(e: LiveEvent): Item {
  const mag = typeof e.data.magnitude === "number" ? e.data.magnitude : 0;
  const count = typeof e.data.count === "number" ? e.data.count : typeof e.data.hotspots === "number" ? e.data.hotspots : 1;
  return {
    id: e.id,
    layer: e.kind,
    title: e.title,
    detail: e.detail,
    when: e.ends_at ? `${whenUtc(e.starts_at)} to ${whenUtc(e.ends_at)}` : e.starts_at ? `since ${whenUtc(e.starts_at)}` : "",
    source: e.source,
    url: safeUrl(e.source_url),
    lat: e.lat,
    lon: e.lon,
    countries: e.countries,
    size: e.kind === "quake" ? Math.max(1, mag - 3.5) : Math.min(3, 1 + Math.log2(count)),
    major: e.severity === "major",
  };
}

/** One item per chokepoint: its latest completed day's ship count. */
export function shipItems(stats: LiveStat[]): Item[] {
  const last = new Map<string, LiveStat>();
  for (const s of stats) if (s.kind === "ships" && !s.partial) last.set(s.region, s);
  return Array.from(last.values()).map((s) => {
    const name = s.name.split(" — ")[0];
    return {
      id: s.series_id,
      layer: "ships" as const,
      title: `${name}: ${s.value} ships crossed on ${s.period}`,
      detail: "Ships whose tracking signal crossed our counting line in this strait that day, counted by Ohmega from live ship-position broadcasts. Ships with their transponder off are not seen, so read it against its own recent days, not as a total.",
      when: `day ending ${s.period} 24:00 UTC`,
      source: "Ohmega count from aisstream.io",
      url: safeUrl(s.source_url),
      lat: s.lat,
      lon: s.lon,
      countries: [],
      size: 1.4,
      major: false,
      region: s.region,
      badge: `${name} · ${s.value}`,
    };
  });
}
