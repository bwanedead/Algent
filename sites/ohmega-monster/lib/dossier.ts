import fs from "node:fs";
import path from "node:path";

import { parseMap, type TheaterMap } from "./daily";
import { bandAt } from "./band";
import { maxBand, parseCoverage, safeUrl, type Band, type Coverage, type Direction, type IndicatorStatus, type Pace } from "./intel";

// Theater dossiers: one living record per theater, written by the backend as JSON to
// <intel dir>/theaters/index.json and <intel dir>/theaters/<theater_id>.json (ohmega.dossier/1) and read
// at build time. Parsed defensively: a missing dir, a missing index or a malformed file yields empty
// states, never a build failure.
const INTEL_DIR = process.env.OHMEGA_INTEL_DIR || path.join(process.cwd(), "content", "intel");
const THEATERS_DIR = path.join(INTEL_DIR, "theaters");
const ID_RE = /^[\w.-]+$/;

export type DossierIndexItem = {
  theater_id: string;
  name: string;
  domain: string;
  first_seen: string;
  last_seen: string;
  days_covered: number;
  heat: number;
  coverage: Coverage;
  escalation_direction: Direction;
  max_band: Band;
};
export type DossierPulse = { id: string; name: string; situation: string; position: number | null; band: Band; history: { at: string; position: number }[] };
export type EscalationPoint = { date: string; direction: Direction; pace: Pace };
export type CoveragePoint = { day: string; count: number; editions: number };
export type Verification = "researched" | "reported";
export type TimelineItem = { date: string; headline: string; detail: string; where: string; verification: Verification; sources: string[]; from: string };
export type Place = { name: string; country: string; count: number; last_date: string };
export type Actor = { name: string; mentions: number; first: string; last: string };
export type Relation = { source: string; target: string; kind: string; count: number; last_date: string; note: string };
export type FigurePoint = { as_of: string; value: number; source: string };
export type Figure = { label: string; unit: string; series: FigurePoint[] };
export type ForecastStatus = "open" | "yes" | "no" | "void";
export type DossierForecast = { id: string; statement: string; probability: number; horizon: string; status: ForecastStatus; resolution: Record<string, string> | null };
export type IndicatorRow = { signal: string; history: { date: string; status: IndicatorStatus }[] };
export type Statement = { who: string; role: string; said: string; quote: boolean; when: string; source: string };
export type RelatedTheater = { theater_id: string; name: string; link: string; date: string };
export type Dossier = {
  theater_id: string;
  name: string;
  domain: string;
  built_at: string;
  first_seen: string;
  last_seen: string;
  days_covered: number;
  primer: { text: string; built_at: string } | null;
  current: { date: string; bottom_line: string; direction: Direction; pace: Pace; coverage: Coverage; source: string; url: string } | null;
  pulses: DossierPulse[];
  escalation_history: EscalationPoint[];
  coverage_series: CoveragePoint[];
  timeline: TimelineItem[];
  places: Place[];
  map: TheaterMap | null;
  actors: Actor[];
  relations: Relation[];
  figures: Figure[];
  forecasts: DossierForecast[];
  indicators: IndicatorRow[];
  statements: Statement[];
  links: RelatedTheater[];
  reports: { date: string; url: string }[];
  briefs: { slug: string; title: string; as_of: string; url: string }[];
};

// ---- defensive coercion helpers -------------------------------------------------------------
type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v : typeof v === "number" ? String(v) : "");
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
/** A number, or a numeric string ("1,200"). */
const looseNum = (v: unknown): number | null => {
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v.replace(/,/g, ""));
    return Number.isFinite(n) ? n : null;
  }
  return num(v);
};
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const strs = (v: unknown): string[] => arr(v).map(str).filter(Boolean);
const oneOf = <T extends string>(v: unknown, allowed: readonly T[], fallback: T): T => ((allowed as readonly string[]).includes(v as string) ? (v as T) : fallback);
const objs = (v: unknown): Obj[] => arr(v).filter(isObj);
const byDate = <T>(key: (t: T) => string) => (a: T, b: T) => (key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0);

const DIRECTIONS = ["rising", "steady", "easing", "unclear"] as const;
const PACES = ["fast", "gradual", "flat"] as const;
const BANDS = ["calm", "elevated", "severe", "critical", "unassessed"] as const;
const STATUSES = ["not seen", "emerging", "observed"] as const;

/**
 * A link target: a site-relative path (internal) or an http(s) URL (external). Anything else (other
 * schemes, protocol-relative "//host") is dropped, so a hostile string never becomes an href.
 */
export function linkTarget(u: string): { href: string; external: boolean } | null {
  if (/^\/(?![/\\])[^\s<>"'\\]*$/.test(u)) return { href: u, external: false };
  const s = safeUrl(u);
  return s ? { href: s, external: true } : null;
}

function readJson(file: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

const dossierFile = (id: string) => path.join(THEATERS_DIR, `${id}.json`);

// ---- parsers --------------------------------------------------------------------------------
function parseIndexItem(raw: Obj): DossierIndexItem | null {
  const id = str(raw.theater_id);
  if (!id || !ID_RE.test(id)) return null;
  return {
    theater_id: id,
    name: str(raw.name) || id,
    domain: str(raw.domain),
    first_seen: str(raw.first_seen),
    last_seen: str(raw.last_seen),
    days_covered: num(raw.days_covered) ?? 0,
    heat: num(raw.heat) ?? 0,
    coverage: parseCoverage(raw.coverage, "steady"),
    escalation_direction: oneOf(raw.escalation_direction, DIRECTIONS, "unclear"),
    max_band: oneOf(raw.max_band, BANDS, "unassessed"),
  };
}

function parsePulse(raw: Obj): DossierPulse | null {
  const name = str(raw.name);
  if (!name) return null;
  const position = num(raw.position);
  return {
    id: str(raw.id) || name,
    name,
    situation: str(raw.situation),
    position,
    band: position === null ? "unassessed" : oneOf(raw.band, BANDS, bandAt(position)),
    history: objs(raw.history)
      .map((h) => ({ at: str(h.at), position: num(h.position) }))
      .filter((h): h is { at: string; position: number } => h.position !== null && h.at !== ""),
  };
}

function parseForecast(raw: Obj, i: number): DossierForecast | null {
  const statement = str(raw.statement);
  const p = num(raw.probability);
  if (!statement || p === null) return null;
  const res = isObj(raw.resolution) ? raw.resolution : null;
  const resolution: Record<string, string> = {};
  if (res) for (const [k, v] of Object.entries(res).slice(0, 12)) if (str(v)) resolution[k] = str(v);
  return {
    id: str(raw.id) || `f${i}`,
    statement,
    probability: Math.min(99, Math.max(1, Math.round(p))),
    horizon: str(raw.horizon),
    status: oneOf(raw.status, ["open", "yes", "no", "void"] as const, "open"),
    resolution: Object.keys(resolution).length > 0 ? resolution : null,
  };
}

function parseDossier(raw: unknown, id: string): Dossier | null {
  if (!isObj(raw)) return null;
  const cur = isObj(raw.current) ? raw.current : null;
  const esc = cur && isObj(cur.escalation) ? cur.escalation : {};
  const primer = isObj(raw.primer) && str(raw.primer.text).trim() ? { text: str(raw.primer.text).trim(), built_at: str(raw.primer.built_at) } : null;
  const bottom = cur ? str(cur.bottom_line) : "";
  return {
    theater_id: id,
    name: str(raw.name) || id,
    domain: str(raw.domain),
    built_at: str(raw.built_at),
    first_seen: str(raw.first_seen),
    last_seen: str(raw.last_seen),
    days_covered: num(raw.days_covered) ?? 0,
    primer,
    current: cur && bottom
      ? {
          date: str(cur.date),
          bottom_line: bottom,
          direction: oneOf(esc.direction, DIRECTIONS, "unclear"),
          pace: oneOf(esc.pace, PACES, "flat"),
          coverage: parseCoverage(cur.coverage, "steady"),
          source: str(cur.source),
          url: str(cur.url),
        }
      : null,
    pulses: objs(raw.pulses).map(parsePulse).filter((p): p is DossierPulse => p !== null),
    escalation_history: objs(raw.escalation_history)
      .map((e) => ({ date: str(e.date), direction: oneOf(e.direction, DIRECTIONS, "unclear"), pace: oneOf(e.pace, PACES, "flat") }))
      .filter((e) => e.date)
      .sort(byDate((e) => e.date)),
    coverage_series: objs(raw.coverage_series)
      .map((c) => ({ day: str(c.day), count: num(c.count) ?? 0, editions: num(c.editions) ?? 0 }))
      .filter((c) => c.day)
      .sort(byDate((c) => c.day)),
    timeline: objs(raw.timeline)
      .map((t) => ({
        date: str(t.date),
        headline: str(t.headline),
        detail: str(t.detail),
        where: str(t.where),
        verification: oneOf(t.verification, ["researched", "reported"] as const, "reported"),
        sources: strs(t.sources),
        from: str(t.from),
      }))
      .filter((t) => t.headline),
    places: objs(raw.places)
      .map((p) => ({ name: str(p.name), country: str(p.country), count: num(p.count) ?? 0, last_date: str(p.last_date) }))
      .filter((p) => p.name),
    map: parseMap(raw.map),
    actors: objs(raw.actors)
      .map((a) => ({ name: str(a.name).trim(), mentions: Math.max(0, num(a.mentions) ?? 0), first: str(a.first), last: str(a.last) }))
      .filter((a) => a.name),
    relations: objs(raw.relations)
      .map((r) => ({
        source: str(r.source).trim(),
        target: str(r.target).trim(),
        kind: str(r.kind) || "other",
        count: Math.max(1, num(r.count) ?? 1),
        last_date: str(r.last_date),
        note: str(r.note),
      }))
      .filter((r) => r.source && r.target),
    figures: objs(raw.figures)
      .map((f) => ({
        label: str(f.label),
        unit: str(f.unit),
        series: objs(f.series)
          .map((s) => ({ as_of: str(s.as_of), value: looseNum(s.value), source: str(s.source) }))
          .filter((s): s is FigurePoint => s.value !== null)
          .sort(byDate((s) => s.as_of)),
      }))
      .filter((f) => f.label && f.series.length > 0),
    forecasts: objs(raw.forecasts).map(parseForecast).filter((f): f is DossierForecast => f !== null),
    indicators: objs(raw.indicators)
      .map((x) => ({
        signal: str(x.signal),
        history: objs(x.history)
          .map((h) => ({ date: str(h.date), status: oneOf(h.status, STATUSES, "not seen") }))
          .filter((h) => h.date)
          .sort(byDate((h) => h.date)),
      }))
      .filter((x) => x.signal && x.history.length > 0),
    statements: objs(raw.statements)
      .map((s) => ({ who: str(s.who), role: str(s.role), said: str(s.said), quote: s.quote === true, when: str(s.when), source: str(s.source) }))
      .filter((s) => s.said),
    links: objs(raw.links)
      .map((l) => ({ theater_id: str(l.theater_id), name: str(l.name), link: str(l.link), date: str(l.date) }))
      .filter((l) => l.theater_id && (l.name || l.link)),
    reports: objs(raw.reports)
      .map((r) => ({ date: str(r.date), url: str(r.url) }))
      .filter((r) => r.date),
    briefs: objs(raw.briefs)
      .map((b) => ({ slug: str(b.slug), title: str(b.title), as_of: str(b.as_of), url: str(b.url) }))
      .filter((b) => b.title),
  };
}

// ---- public readers -------------------------------------------------------------------------
export function dossier(id: string): Dossier | null {
  if (!ID_RE.test(id) || id === "index") return null;
  return parseDossier(readJson(dossierFile(id)), id);
}

function itemFromDossier(d: Dossier): DossierIndexItem {
  const last = d.escalation_history[d.escalation_history.length - 1];
  return {
    theater_id: d.theater_id,
    name: d.name,
    domain: d.domain,
    first_seen: d.first_seen,
    last_seen: d.last_seen,
    days_covered: d.days_covered,
    heat: 0,
    coverage: d.current?.coverage ?? "steady",
    escalation_direction: d.current?.direction ?? last?.direction ?? "unclear",
    max_band: maxBand(d.pulses),
  };
}

/** Every theater that has a readable dossier. The index drives it; with no usable index, the dossier files do. */
export function dossierList(): DossierIndexItem[] {
  const raw = readJson(path.join(THEATERS_DIR, "index.json"));
  const fromIndex = (isObj(raw) ? objs(raw.theaters) : [])
    .map(parseIndexItem)
    .filter((i): i is DossierIndexItem => i !== null && i.theater_id !== "index" && fs.existsSync(dossierFile(i.theater_id)));
  if (fromIndex.length > 0) return fromIndex;
  try {
    return fs
      .readdirSync(THEATERS_DIR)
      .filter((f) => f.endsWith(".json") && f !== "index.json")
      .map((f) => dossier(f.slice(0, -5)))
      .filter((d): d is Dossier => d !== null)
      .map(itemFromDossier);
  } catch {
    return [];
  }
}

export const dossierIds = (): string[] => dossierList().map((i) => i.theater_id);

/** Where a theater's dossier lives, or null when it has none (so callers link only what exists). */
export function dossierPath(theaterId: string): string | null {
  return ID_RE.test(theaterId) && dossierIds().includes(theaterId) ? `/intel/theaters/${theaterId}` : null;
}
