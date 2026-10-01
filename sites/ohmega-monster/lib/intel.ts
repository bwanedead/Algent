import fs from "node:fs";
import path from "node:path";

// The Intelligence desk's data is written by the backend as JSON into the content dir and read at
// build time. Everything is parsed defensively: a missing/empty dir yields empty states, never a
// build failure.
const INTEL_DIR = process.env.OHMEGA_INTEL_DIR || path.join(process.cwd(), "content", "intel");

export type Band = "calm" | "elevated" | "severe" | "critical" | "unassessed";
export type Confidence = "high" | "medium" | "low" | "";
export type Trend = "heating" | "steady" | "cooling" | "new";
export type Direction = "rising" | "steady" | "easing" | "unclear";
export type Pace = "fast" | "gradual" | "flat";

export type Pulse = {
  id: string;
  name: string;
  question: string;
  low_end: string;
  high_end: string;
  position: number | null;
  band: Band;
  velocity_7d: number | null;
  velocity_30d: number | null;
  confidence: Confidence;
  last_assessed: string;
  evidence_through: string;
  history: { at: string; position: number }[];
  rationale: string;
};
export type Watch = { condition: string; why: string; direction: "up" | "down" | "either"; horizon: string; status: string };
export type Situation = { id: string; title: string; summary: string; domain: string; pulses: Pulse[]; watches: Watch[] };
export type Theater = {
  id: string;
  name: string;
  domain: string;
  why: string;
  heat: number;
  trend: Trend;
  recent: number;
  prior: number;
  first_seen: string;
  series: { day: string; count: number }[];
  brief: string | null;
};
export type BriefSummary = {
  slug: string;
  title: string;
  bottom_line: string;
  theater_id: string;
  theater_name: string;
  as_of: string;
  direction: string;
  pace: string;
};
export type Snapshot = { slug: string; built_at: string; situations: Situation[]; theaters: Theater[]; briefs: BriefSummary[] };

export type Effect = { effect: string; likelihood: string; watch_for: string };
export type Brief = {
  slug: string;
  as_of: string;
  built_at: string;
  theater_id: string;
  theater_name: string;
  heat: Theater | null;
  researched: boolean;
  focus: string;
  title: string;
  bottom_line: string;
  situation: string;
  escalation: { direction: Direction; pace: Pace; assessment: string };
  timeline: { date: string; what: string; actors: string[]; verification: "researched" | "reported"; source: string }[];
  relations: { source: string; target: string; kind: string; note: string; date: string }[];
  second_order: Effect[];
  peripheral: Effect[];
  indicators: { signal: string; status: "not seen" | "emerging" | "observed"; meaning: string }[];
  unknowns: string[];
  pulses: string[];
};

// ---- defensive coercion helpers -------------------------------------------------------------
type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v : typeof v === "number" ? String(v) : "");
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const strs = (v: unknown): string[] => arr(v).map(str).filter(Boolean);
const oneOf = <T extends string>(v: unknown, allowed: readonly T[], fallback: T): T =>
  (allowed as readonly string[]).includes(v as string) ? (v as T) : fallback;

/** Only http(s) links may be rendered as hrefs. */
export function safeUrl(u: string): string | null {
  try {
    const p = new URL(u);
    return p.protocol === "http:" || p.protocol === "https:" ? p.href : null;
  } catch {
    return null;
  }
}

function readJson(file: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

function jsonSlugs(sub: string): string[] {
  try {
    return fs
      .readdirSync(path.join(INTEL_DIR, sub))
      .filter((f) => f.endsWith(".json"))
      .map((f) => f.slice(0, -5))
      .sort();
  } catch {
    return [];
  }
}

// ---- parsers --------------------------------------------------------------------------------
function parsePulse(raw: unknown): Pulse | null {
  if (!isObj(raw)) return null;
  const position = num(raw.position);
  const name = str(raw.name);
  if (!name) return null;
  return {
    id: str(raw.id) || name,
    name,
    question: str(raw.question),
    low_end: str(raw.low_end),
    high_end: str(raw.high_end),
    position,
    band: position === null ? "unassessed" : oneOf(raw.band, ["calm", "elevated", "severe", "critical", "unassessed"] as const, "unassessed"),
    velocity_7d: num(raw.velocity_7d),
    velocity_30d: num(raw.velocity_30d),
    confidence: oneOf(raw.confidence, ["high", "medium", "low", ""] as const, ""),
    last_assessed: str(raw.last_assessed),
    evidence_through: str(raw.evidence_through),
    history: arr(raw.history)
      .filter(isObj)
      .map((h) => ({ at: str(h.at), position: num(h.position) }))
      .filter((h): h is { at: string; position: number } => h.position !== null),
    rationale: str(raw.rationale),
  };
}

function parseTheater(raw: unknown): Theater | null {
  if (!isObj(raw)) return null;
  const name = str(raw.name);
  if (!name) return null;
  return {
    id: str(raw.id) || name,
    name,
    domain: str(raw.domain),
    why: str(raw.why),
    heat: num(raw.heat) ?? 0,
    trend: oneOf(raw.trend, ["heating", "steady", "cooling", "new"] as const, "steady"),
    recent: num(raw.recent) ?? 0,
    prior: num(raw.prior) ?? 0,
    first_seen: str(raw.first_seen),
    series: arr(raw.series)
      .filter(isObj)
      .map((s) => ({ day: str(s.day), count: num(s.count) ?? 0 })),
    brief: str(raw.brief) || null,
  };
}

function parseSnapshot(raw: unknown, slug: string): Snapshot | null {
  if (!isObj(raw)) return null;
  return {
    slug: str(raw.slug) || slug,
    built_at: str(raw.built_at),
    situations: arr(raw.situations)
      .filter(isObj)
      .map((s) => ({
        id: str(s.id) || str(s.title),
        title: str(s.title),
        summary: str(s.summary),
        domain: str(s.domain),
        pulses: arr(s.pulses).map(parsePulse).filter((p): p is Pulse => p !== null),
        watches: arr(s.watches)
          .filter(isObj)
          .map((w) => ({
            condition: str(w.condition),
            why: str(w.why),
            direction: oneOf(w.direction, ["up", "down", "either"] as const, "either"),
            horizon: str(w.horizon),
            status: str(w.status),
          }))
          .filter((w) => w.condition),
      }))
      .filter((s) => s.title),
    theaters: arr(raw.theaters).map(parseTheater).filter((t): t is Theater => t !== null),
    briefs: arr(raw.briefs)
      .filter(isObj)
      .map((b) => ({
        slug: str(b.slug),
        title: str(b.title),
        bottom_line: str(b.bottom_line),
        theater_id: str(b.theater_id),
        theater_name: str(b.theater_name),
        as_of: str(b.as_of),
        direction: str(b.direction),
        pace: str(b.pace),
      }))
      .filter((b) => b.slug && b.title),
  };
}

const parseEffects = (v: unknown): Effect[] =>
  arr(v)
    .filter(isObj)
    .map((e) => ({ effect: str(e.effect), likelihood: str(e.likelihood), watch_for: str(e.watch_for) }))
    .filter((e) => e.effect);

function parseBrief(raw: unknown, slug: string): Brief | null {
  if (!isObj(raw)) return null;
  const esc = isObj(raw.escalation) ? raw.escalation : {};
  return {
    slug: str(raw.slug) || slug,
    as_of: str(raw.as_of),
    built_at: str(raw.built_at),
    theater_id: str(raw.theater_id),
    theater_name: str(raw.theater_name),
    heat: parseTheater(raw.heat),
    researched: raw.researched === true,
    focus: str(raw.focus),
    title: str(raw.title) || slug,
    bottom_line: str(raw.bottom_line),
    situation: str(raw.situation),
    escalation: {
      direction: oneOf(esc.direction, ["rising", "steady", "easing", "unclear"] as const, "unclear"),
      pace: oneOf(esc.pace, ["fast", "gradual", "flat"] as const, "flat"),
      assessment: str(esc.assessment),
    },
    timeline: arr(raw.timeline)
      .filter(isObj)
      .map((t) => ({
        date: str(t.date),
        what: str(t.what),
        actors: strs(t.actors),
        verification: oneOf(t.verification, ["researched", "reported"] as const, "reported"),
        source: str(t.source),
      }))
      .filter((t) => t.what),
    relations: arr(raw.relations)
      .filter(isObj)
      .map((r) => ({ source: str(r.source), target: str(r.target), kind: str(r.kind) || "other", note: str(r.note), date: str(r.date) }))
      .filter((r) => r.source && r.target),
    second_order: parseEffects(raw.second_order),
    peripheral: parseEffects(raw.peripheral),
    indicators: arr(raw.indicators)
      .filter(isObj)
      .map((i) => ({
        signal: str(i.signal),
        status: oneOf(i.status, ["not seen", "emerging", "observed"] as const, "not seen"),
        meaning: str(i.meaning),
      }))
      .filter((i) => i.signal),
    unknowns: strs(raw.unknowns),
    pulses: strs(raw.pulses),
  };
}

// ---- public readers -------------------------------------------------------------------------
export function latestSnapshot(): Snapshot | null {
  const slugs = jsonSlugs("snapshots");
  for (let i = slugs.length - 1; i >= 0; i--) {
    const snap = parseSnapshot(readJson(path.join(INTEL_DIR, "snapshots", `${slugs[i]}.json`)), slugs[i]);
    if (snap) return snap;
  }
  return null;
}

export function allBriefSlugs(): string[] {
  return jsonSlugs("briefs").filter((s) => /^[\w.-]+$/.test(s) && brief(s) !== null);
}

export function brief(slug: string): Brief | null {
  if (!/^[\w.-]+$/.test(slug)) return null;
  return parseBrief(readJson(path.join(INTEL_DIR, "briefs", `${slug}.json`)), slug);
}

// ---- small shared presentation helpers ------------------------------------------------------
export const BAND_LABEL: Record<Band, string> = { calm: "Calm", elevated: "Elevated", severe: "Severe", critical: "Critical", unassessed: "Not yet assessed" };
const BAND_RANK: Record<Band, number> = { calm: 1, elevated: 2, severe: 3, critical: 4, unassessed: 0 };

/** Pulses most severe first (band, then position). Unassessed excluded. */
export function mostSeverePulses(s: Snapshot | null, n: number): (Pulse & { situation: string })[] {
  if (!s) return [];
  return s.situations
    .flatMap((sit) => sit.pulses.map((p) => ({ ...p, situation: sit.title })))
    .filter((p) => p.position !== null)
    .sort((a, b) => BAND_RANK[b.band] - BAND_RANK[a.band] || (b.position ?? 0) - (a.position ?? 0))
    .slice(0, n);
}

export function hottestTheater(s: Snapshot | null): Theater | null {
  if (!s || s.theaters.length === 0) return null;
  return [...s.theaters].sort((a, b) => b.heat - a.heat)[0];
}

/** "2026-09-30T14:05:00Z" -> "2026-09-30 14:05 UTC"; date-only strings pass through. */
export function fmtUtc(iso: string): string {
  const m = iso.match(/^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
  return m ? `${m[1]} ${m[2]} UTC` : iso;
}
