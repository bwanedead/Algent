// The data specs of the native interactive daily visuals, as the site reads them (contracts: backend
// agents/intel/timeline_spec.py and mapstory_spec.py). The JSON is fetched in the browser from our published
// assets, so every field is coerced defensively: a malformed spec yields null and the caller falls back to the still.
// Client-safe: no server imports.

export type TimelineKind = "strike" | "statement" | "meeting" | "decision" | "movement" | "deadline" | "other";
export const TIMELINE_KINDS = ["strike", "statement", "meeting", "decision", "movement", "deadline", "other"] as const;
export type SpecSource = { label: string; url: string };

export type TimelineEvent = {
  id: string;
  date: string; // YYYY-MM-DD
  time: string; // HH:MM or ""
  title: string;
  detail: string;
  actors: string[]; // ISO alpha-2
  lane: string;
  kind: TimelineKind;
  place: string; // the place's name or ""
  sources: SpecSource[];
};
export type TimelineSpec = { title: string; caption: string; lanes: { id: string; label: string }[]; events: TimelineEvent[]; now: string; alt: string };

export type LonLat = [number, number];
export type MapTone = "ink" | "accent" | "warn" | "cool" | "hot" | "good";
export const MAP_TONES = ["ink", "accent", "warn", "cool", "hot", "good"] as const;
type MapBase = { id: string; label: string; tone: MapTone };
export type MapFeature =
  | (MapBase & { type: "point"; at: LonLat })
  | (MapBase & { type: "route"; path: LonLat[]; arrow: boolean })
  | (MapBase & { type: "area"; ring: LonLat[] })
  | (MapBase & { type: "range"; at: LonLat; radius_km: number });
export type MapStep = { date: string; caption: string; show: MapFeature[]; hide: string[]; sources: SpecSource[] };
export type MapStorySpec = { title: string; caption: string; steps: MapStep[]; bounds: [number, number, number, number] | null; alt: string };

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const fin = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const oneOf = <T extends string>(v: unknown, allowed: readonly T[], fallback: T): T => ((allowed as readonly string[]).includes(v as string) ? (v as T) : fallback);
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

const sources = (v: unknown): SpecSource[] =>
  arr(v)
    .filter(isObj)
    .map((x) => ({ label: str(x.label), url: /^https?:\/\//.test(str(x.url)) ? str(x.url) : "" }))
    .filter((x) => x.label);

export function parseTimeline(raw: unknown): TimelineSpec | null {
  if (!isObj(raw)) return null;
  const events = arr(raw.events)
    .filter(isObj)
    .map((e, i): TimelineEvent | null => {
      const date = str(e.date);
      const title = str(e.title);
      if (!DATE_RE.test(date) || !title) return null;
      const place = isObj(e.place) ? str(e.place.name) : "";
      return {
        id: str(e.id) || `e${i}`,
        date,
        time: /^\d{2}:\d{2}$/.test(str(e.time)) ? str(e.time) : "",
        title,
        detail: str(e.detail),
        actors: arr(e.actors).map(str).filter((c) => /^[A-Za-z]{2}$/.test(c)),
        lane: str(e.lane),
        kind: oneOf(e.kind, TIMELINE_KINDS, "other"),
        place,
        sources: sources(e.sources),
      };
    })
    .filter((e): e is TimelineEvent => e !== null)
    .sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));
  if (events.length === 0) return null;
  const lanes = arr(raw.lanes).filter(isObj).map((l) => ({ id: str(l.id), label: str(l.label) })).filter((l) => l.id && l.label).slice(0, 4);
  return { title: str(raw.title), caption: str(raw.caption), lanes, events, now: DATE_RE.test(str(raw.now)) ? str(raw.now) : "", alt: str(raw.alt) };
}

const lonLat = (v: unknown): LonLat | null => {
  if (!isObj(v)) return null;
  const lat = fin(v.lat);
  const lon = fin(v.lon);
  return lat !== null && lon !== null && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? [lon, lat] : null;
};
const lonLats = (v: unknown): LonLat[] => arr(v).map(lonLat).filter((p): p is LonLat => p !== null);

function parseFeature(raw: unknown): MapFeature | null {
  if (!isObj(raw)) return null;
  const base = { id: str(raw.id), label: str(raw.label), tone: oneOf(raw.tone, MAP_TONES, "accent") };
  if (!base.id) return null;
  if (raw.type === "point") {
    const at = lonLat(raw.at);
    return at ? { ...base, type: "point", at } : null;
  }
  if (raw.type === "route") {
    const path = lonLats(raw.path);
    return path.length >= 2 ? { ...base, type: "route", path, arrow: raw.arrow !== false } : null;
  }
  if (raw.type === "area") {
    const ring = lonLats(raw.ring);
    return ring.length >= 3 ? { ...base, type: "area", ring } : null;
  }
  if (raw.type === "range") {
    const at = lonLat(raw.at);
    const r = fin(raw.radius_km);
    return at && r !== null && r > 0 ? { ...base, type: "range", at, radius_km: r } : null;
  }
  return null;
}

export function parseMapStory(raw: unknown): MapStorySpec | null {
  if (!isObj(raw)) return null;
  const steps = arr(raw.steps)
    .filter(isObj)
    .map((s): MapStep | null => {
      const date = str(s.date);
      if (!DATE_RE.test(date)) return null;
      return {
        date,
        caption: str(s.caption),
        show: arr(s.show).map(parseFeature).filter((f): f is MapFeature => f !== null),
        hide: arr(s.hide).map(str).filter(Boolean),
        sources: sources(s.sources),
      };
    })
    .filter((s): s is MapStep => s !== null);
  if (steps.length < 2) return null;
  const b = arr(raw.bounds).map(fin);
  const bounds = b.length === 4 && b.every((x) => x !== null) && (b[0] as number) < (b[2] as number) && (b[1] as number) < (b[3] as number) ? (b as [number, number, number, number]) : null;
  return { title: str(raw.title), caption: str(raw.caption), steps, bounds, alt: str(raw.alt) };
}
