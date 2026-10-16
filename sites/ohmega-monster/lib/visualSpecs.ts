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

// ---- network (backend agents/intel/network_spec.py) ----------------------------------------------------------------------

export type NetKind = "state" | "group" | "person" | "org" | "place";
export const NET_KINDS = ["state", "group", "person", "org", "place"] as const;
export type NetRelation = "supports" | "arms" | "funds" | "allied_with" | "opposes" | "attacks" | "sanctions" | "trades" | "depends_on" | "negotiates_with";
/** The colour families: one meaning each (backing, hostility, exchange, talks). Same table as the backend's `FAMILY`. */
export type NetFamily = "backing" | "hostile" | "exchange" | "talks";
export const NET_FAMILY: Record<NetRelation, NetFamily> = {
  supports: "backing", arms: "backing", funds: "backing", allied_with: "backing",
  opposes: "hostile", attacks: "hostile", sanctions: "hostile",
  trades: "exchange", depends_on: "exchange", negotiates_with: "talks",
};
export const NET_PHRASE: Record<NetRelation, string> = {
  supports: "supports", arms: "arms", funds: "funds", allied_with: "is allied with", opposes: "opposes", attacks: "attacks",
  sanctions: "sanctions", trades: "trades with", depends_on: "depends on", negotiates_with: "negotiates with",
};
export type NetNode = { id: string; label: string; kind: NetKind; iso: string; weight: number };
export type NetEdge = {
  id: string; source: string; target: string; relation: NetRelation; family: NetFamily; both: boolean;
  strength: 1 | 2 | 3; detail: string; start: string; end: string; sources: SpecSource[];
};
export type NetworkSpec = { title: string; caption: string; weightLabel: string; nodes: NetNode[]; edges: NetEdge[]; alt: string };

export function parseNetwork(raw: unknown): NetworkSpec | null {
  if (!isObj(raw)) return null;
  const nodes = arr(raw.nodes)
    .filter(isObj)
    .map((n): NetNode | null => {
      const id = str(n.id);
      const label = str(n.label);
      const w = fin(n.weight);
      return id && label ? { id, label, kind: oneOf(n.kind, NET_KINDS, "group"), iso: /^[A-Za-z]{2}$/.test(str(n.iso)) ? str(n.iso).toUpperCase() : "", weight: w !== null && w > 0 ? w : 0 } : null;
    })
    .filter((n): n is NetNode => n !== null);
  const have = new Set(nodes.map((n) => n.id));
  const rels = Object.keys(NET_FAMILY) as NetRelation[];
  const date = (v: unknown) => (DATE_RE.test(str(v)) ? str(v) : "");
  const edges = arr(raw.edges)
    .filter(isObj)
    .map((e, i): NetEdge | null => {
      const source = str(e.source);
      const target = str(e.target);
      if (!rels.includes(e.relation as NetRelation) || !have.has(source) || !have.has(target) || source === target) return null;
      const relation = e.relation as NetRelation;
      const s = fin(e.strength);
      return {
        id: str(e.id) || `e${i}`, source, target, relation, family: NET_FAMILY[relation], both: e.direction === "both",
        strength: s !== null && s >= 3 ? 3 : s !== null && s <= 1 ? 1 : 2, detail: str(e.detail), start: date(e.start), end: date(e.end), sources: sources(e.sources),
      };
    })
    .filter((e): e is NetEdge => e !== null);
  if (nodes.length < 2 || edges.length < 1) return null;
  return { title: str(raw.title), caption: str(raw.caption), weightLabel: str(raw.weight_label), nodes, edges, alt: str(raw.alt) };
}

// ---- flow (backend agents/intel/flow_spec.py) ----------------------------------------------------------------------------

export type FlowRole = "source" | "sink" | "hub" | "chokepoint";
export type FlowPlace = { id: string; name: string; role: FlowRole; at: LonLat };
export type FlowRoute = {
  id: string; source: string; target: string; commodity: string; amount: number; unit: string; period: string;
  via: string[]; detail: string; sources: SpecSource[];
};
export type FlowDisruption = { id: string; date: string; breaks: string[]; reroutes: string[]; effect: string; sources: SpecSource[] };
export type FlowSpec = {
  title: string; caption: string; places: FlowPlace[]; flows: FlowRoute[]; disruptions: FlowDisruption[];
  bounds: [number, number, number, number] | null; alt: string;
};

export function parseFlow(raw: unknown): FlowSpec | null {
  if (!isObj(raw)) return null;
  const places = arr(raw.places)
    .filter(isObj)
    .map((p): FlowPlace | null => {
      const lat = fin(p.lat);
      const lon = fin(p.lon);
      const id = str(p.id);
      return id && lat !== null && lon !== null && Math.abs(lat) <= 90 && Math.abs(lon) <= 180
        ? { id, name: str(p.name), role: oneOf(p.role, ["source", "sink", "hub", "chokepoint"] as const, "hub"), at: [lon, lat] }
        : null;
    })
    .filter((p): p is FlowPlace => p !== null);
  const have = new Set(places.map((p) => p.id));
  const flows = arr(raw.flows)
    .filter(isObj)
    .map((f, i): FlowRoute | null => {
      const source = str(f.source);
      const target = str(f.target);
      if (!have.has(source) || !have.has(target) || source === target) return null;
      const amount = fin(f.amount);
      return {
        id: str(f.id) || `f${i}`, source, target, commodity: str(f.commodity), amount: amount !== null && amount > 0 ? amount : 0,
        unit: str(f.unit), period: str(f.period), via: arr(f.via).map(str).filter((v) => have.has(v)), detail: str(f.detail), sources: sources(f.sources),
      };
    })
    .filter((f): f is FlowRoute => f !== null);
  if (flows.length < 1) return null;
  const ids = new Set(flows.map((f) => f.id));
  const known = new Set([...Array.from(ids), ...Array.from(have)]);
  const disruptions = arr(raw.disruptions)
    .filter(isObj)
    .map((d): FlowDisruption | null => {
      const breaks = arr(d.breaks).map(str).filter((b) => known.has(b));
      return DATE_RE.test(str(d.date)) && breaks.length
        ? { id: str(d.id), date: str(d.date), breaks, reroutes: arr(d.reroutes).map(str).filter((r) => ids.has(r)), effect: str(d.effect), sources: sources(d.sources) }
        : null;
    })
    .filter((d): d is FlowDisruption => d !== null)
    .sort((a, b) => a.date.localeCompare(b.date));
  const b = arr(raw.bounds).map(fin);
  const bounds = b.length === 4 && b.every((x) => x !== null) && (b[0] as number) < (b[2] as number) && (b[1] as number) < (b[3] as number) ? (b as [number, number, number, number]) : null;
  return { title: str(raw.title), caption: str(raw.caption), places, flows, disruptions, bounds, alt: str(raw.alt) };
}

// ---- tracker comparison (backend agents/intel/tracker_compare_spec.py) ------------------------------------------------------

export type TrackerLine = { id: string; label: string; unit: string; source: string; sourceUrl: string; points: [string, number][] };
export type TrackerMarker = { date: string; label: string; sources: SpecSource[] };
export type TrackerCompareSpec = { title: string; caption: string; start: string; end: string; series: TrackerLine[]; markers: TrackerMarker[]; alt: string };

export function parseTrackerCompare(raw: unknown): TrackerCompareSpec | null {
  if (!isObj(raw)) return null;
  const series = arr(raw.series)
    .filter(isObj)
    .map((s): TrackerLine | null => {
      const dates = arr(s.dates).map(str);
      const values = arr(s.values).map(fin);
      const points: [string, number][] = [];
      dates.forEach((d, i) => {
        const v = values[i];
        if (DATE_RE.test(d) && v !== null && v !== undefined) points.push([d, v]);
      });
      points.sort((a, b) => a[0].localeCompare(b[0]));
      return str(s.id) && points.length >= 2
        ? { id: str(s.id), label: str(s.label) || str(s.id), unit: str(s.unit), source: str(s.source), sourceUrl: /^https?:\/\//.test(str(s.source_url)) ? str(s.source_url) : "", points }
        : null;
    })
    .filter((s): s is TrackerLine => s !== null);
  if (series.length < 2) return null;
  const markers = arr(raw.markers)
    .filter(isObj)
    .map((m): TrackerMarker | null => (DATE_RE.test(str(m.date)) && str(m.label) ? { date: str(m.date), label: str(m.label), sources: sources(m.sources) } : null))
    .filter((m): m is TrackerMarker => m !== null);
  return { title: str(raw.title), caption: str(raw.caption), start: str(raw.start), end: str(raw.end), series, markers, alt: str(raw.alt) };
}
