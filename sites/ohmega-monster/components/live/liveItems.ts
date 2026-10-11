// The /live event items: one plain record per event (outage, quake, notable fire, aircraft region) or chokepoint, shared by the
// interactive map, its static fallback, the card and the list under the map. Ships and aircraft are NOT items (thousands of
// them; see entities.ts). Client-safe: imports only lib/live-shared (never lib/live or the store).

import { whenUtc, type GateNow, type LiveEvent, type LiveKind } from "@/lib/live-shared";

export type Layer = LiveKind | "gates";

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
  notable: boolean;
};

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
    notable: e.data.notable === true,
  };
}

/** One item per chokepoint, carrying the live count when the summary has it. */
export function gateItems(gates: Record<string, GateNow> | undefined): Item[] {
  return Object.entries(gates ?? {}).map(([slug, g]) => {
    const live = typeof g.in_strait === "number" ? `${g.in_strait} ships in the strait right now (${g.moving ?? 0} moving, ${g.tankers ?? 0} tankers)` : "no live ship count yet";
    const today = typeof g.transits_today === "number" ? `; ${g.transits_today} have crossed our counting line so far today` : "";
    return {
      id: `gate:${slug}`,
      layer: "gates" as const,
      title: `${g.label}: ${live}`,
      detail: `${live}${today}. Ships whose tracking signal crossed the counting line, counted by Ohmega from live ship-position broadcasts; ships with the transponder off are not seen, so read it against its own recent days.`,
      when: "live",
      source: "Ohmega count from aisstream.io",
      url: "https://aisstream.io/",
      lat: g.lat,
      lon: g.lon,
      countries: [],
      size: 1,
      major: false,
      notable: false,
    };
  });
}
