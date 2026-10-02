import fs from "node:fs";
import path from "node:path";

import { parseCoverage, type Band, type Coverage, type Direction, type Pace, type Trend } from "./intel";

// Daily reports are written by the backend to <intel dir>/daily/<domain>/<YYYY-MM-DD>.json and read
// at build time. Parsed defensively: a missing dir or malformed file yields empty states, never a
// build failure.
const INTEL_DIR = process.env.OHMEGA_INTEL_DIR || path.join(process.cwd(), "content", "intel");

export type DailyChangeKind = "escalated" | "eased" | "new" | "resolved" | "unchanged";
export type DailyStatement = { who: string; role: string; said: string; quote: boolean; when: string; source: string };
export type DailyPlace = { name: string; country: string; lat: number | null; lon: number | null };
export type DailyDevelopment = {
  headline: string;
  detail: string;
  when: string;
  where: string;
  place: DailyPlace | null;
  actors: string[];
  statements: DailyStatement[];
  significance: string;
  verification: "researched" | "reported";
  sources: string[];
};
export type DailyPulse = { id: string; name: string; position: number | null; band: Band; change_24h: number | null; change_7d: number | null };
export type KeyFigure = {
  label: string;
  value: number;
  unit: string;
  baseline: number | null;
  baseline_label: string;
  as_of: string;
  source: string;
};
export type MapPoint = { x: number; y: number; label: string; date: string; verification: "researched" | "reported"; n: number | null };
export type TheaterMap = {
  bbox: number[];
  projection: string;
  width: number;
  height: number;
  countries: { name: string; d: string }[];
  points: MapPoint[];
  credit: string;
};
export type DailyTheater = {
  theater_id: string;
  name: string;
  temperature: { heat: number; trend: Trend; coverage: Coverage; recent_share: number | null; prior_share: number | null };
  escalation: { direction: Direction; pace: Pace };
  pulses: DailyPulse[];
  bottom_line: string;
  since_yesterday: { what: string; kind: DailyChangeKind }[];
  developments: DailyDevelopment[];
  context: { what: string; when: string; why_relevant: string; source: string }[];
  outlook: string;
  watch_next: string[];
  brief_slug: string | null;
  key_figures: KeyFigure[];
  map: TheaterMap | null;
};
export type Daily = {
  domain: string;
  date: string;
  built_at: string;
  researched: boolean;
  headline: string;
  the_day: string[];
  theaters: DailyTheater[];
  cross_theater: { theaters: string[]; link: string }[];
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

const DOMAIN_RE = /^[\w-]+$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function readJson(file: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

// ---- parsers --------------------------------------------------------------------------------
/** Only plain SVG path data may reach a `d` attribute. */
const PATH_RE = /^[MmLlHhVvCcSsQqTtAaZz0-9eE.,\s+-]*$/;
const MAX_DIM = 4000;
const dim = (v: unknown): number | null => {
  const n = num(v);
  return n !== null && n > 0 && n <= MAX_DIM ? n : null;
};

function parseKeyFigure(raw: unknown): KeyFigure | null {
  if (!isObj(raw)) return null;
  const label = str(raw.label);
  const value = typeof raw.value === "string" && raw.value.trim() !== "" ? Number(raw.value.replace(/,/g, "")) : num(raw.value);
  if (!label || value === null || !Number.isFinite(value)) return null;
  const b = typeof raw.baseline === "string" && raw.baseline.trim() !== "" ? Number(raw.baseline.replace(/,/g, "")) : num(raw.baseline);
  return {
    label,
    value,
    unit: str(raw.unit),
    baseline: b !== null && Number.isFinite(b) ? b : null,
    baseline_label: str(raw.baseline_label),
    as_of: str(raw.as_of),
    source: str(raw.source),
  };
}

function parseMap(raw: unknown): TheaterMap | null {
  if (!isObj(raw)) return null;
  const width = dim(raw.width);
  const height = dim(raw.height);
  if (width === null || height === null) return null;
  const countries = arr(raw.countries)
    .filter(isObj)
    .map((c) => ({ name: str(c.name), d: str(c.d) }))
    .filter((c) => c.d !== "" && PATH_RE.test(c.d));
  const points = arr(raw.points)
    .filter(isObj)
    .map((p) => ({ x: num(p.x), y: num(p.y), label: str(p.label), date: str(p.date), verification: oneOf(p.verification, ["researched", "reported"] as const, "reported"), n: num(p.n) }))
    .filter((p): p is MapPoint => p.x !== null && p.y !== null && p.x >= 0 && p.x <= width && p.y >= 0 && p.y <= height);
  if (countries.length === 0 && points.length === 0) return null;
  return { bbox: arr(raw.bbox).map(num).filter((n): n is number => n !== null), projection: str(raw.projection), width, height, countries, points, credit: str(raw.credit) };
}

function parsePlace(raw: unknown): DailyPlace | null {
  if (!isObj(raw)) return null;
  const name = str(raw.name);
  return name ? { name, country: str(raw.country), lat: num(raw.lat), lon: num(raw.lon) } : null;
}

function parseDevelopment(raw: unknown): DailyDevelopment | null {
  if (!isObj(raw)) return null;
  const headline = str(raw.headline);
  if (!headline) return null;
  return {
    headline,
    detail: str(raw.detail),
    when: str(raw.when),
    where: str(raw.where),
    place: parsePlace(raw.place),
    actors: strs(raw.actors),
    statements: arr(raw.statements)
      .filter(isObj)
      .map((s) => ({ who: str(s.who), role: str(s.role), said: str(s.said), quote: s.quote === true, when: str(s.when), source: str(s.source) }))
      .filter((s) => s.said),
    significance: str(raw.significance),
    verification: oneOf(raw.verification, ["researched", "reported"] as const, "reported"),
    sources: strs(raw.sources),
  };
}

function parseTheater(raw: unknown): DailyTheater | null {
  if (!isObj(raw)) return null;
  const name = str(raw.name);
  if (!name) return null;
  const temp = isObj(raw.temperature) ? raw.temperature : {};
  const esc = isObj(raw.escalation) ? raw.escalation : {};
  const trend = oneOf(temp.trend, ["heating", "steady", "cooling", "new"] as const, "steady");
  return {
    theater_id: str(raw.theater_id) || name,
    name,
    temperature: {
      heat: num(temp.heat) ?? 0,
      trend,
      coverage: parseCoverage(temp.coverage, trend),
      recent_share: num(temp.recent_share),
      prior_share: num(temp.prior_share),
    },
    escalation: {
      direction: oneOf(esc.direction, ["rising", "steady", "easing", "unclear"] as const, "unclear"),
      pace: oneOf(esc.pace, ["fast", "gradual", "flat"] as const, "flat"),
    },
    pulses: arr(raw.pulses)
      .filter(isObj)
      .map((p) => {
        const position = num(p.position);
        const pname = str(p.name);
        return {
          id: str(p.id) || pname,
          name: pname,
          position,
          band: position === null ? ("unassessed" as Band) : oneOf(p.band, ["calm", "elevated", "severe", "critical", "unassessed"] as const, "unassessed"),
          change_24h: num(p.change_24h),
          change_7d: num(p.change_7d),
        };
      })
      .filter((p) => p.name),
    bottom_line: str(raw.bottom_line),
    since_yesterday: arr(raw.since_yesterday)
      .filter(isObj)
      .map((c) => ({ what: str(c.what), kind: oneOf(c.kind, ["escalated", "eased", "new", "resolved", "unchanged"] as const, "unchanged") }))
      .filter((c) => c.what),
    developments: arr(raw.developments).map(parseDevelopment).filter((d): d is DailyDevelopment => d !== null),
    context: arr(raw.context)
      .filter(isObj)
      .map((c) => ({ what: str(c.what), when: str(c.when), why_relevant: str(c.why_relevant), source: str(c.source) }))
      .filter((c) => c.what),
    outlook: str(raw.outlook),
    watch_next: strs(raw.watch_next),
    brief_slug: /^[\w.-]+$/.test(str(raw.brief_slug)) ? str(raw.brief_slug) : null,
    key_figures: arr(raw.key_figures).map(parseKeyFigure).filter((k): k is KeyFigure => k !== null),
    map: parseMap(raw.map),
  };
}

function parseDaily(raw: unknown, domain: string, date: string): Daily | null {
  if (!isObj(raw)) return null;
  const summary = isObj(raw.summary) ? raw.summary : {};
  return {
    domain: str(raw.domain) || domain,
    date,
    built_at: str(raw.built_at),
    researched: raw.researched === true,
    headline: str(summary.headline),
    the_day: strs(summary.the_day),
    theaters: arr(raw.theaters).map(parseTheater).filter((t): t is DailyTheater => t !== null),
    cross_theater: arr(raw.cross_theater)
      .filter(isObj)
      .map((c) => ({ theaters: strs(c.theaters), link: str(c.link) }))
      .filter((c) => c.link),
  };
}

// ---- public readers -------------------------------------------------------------------------
/** All dates with a daily report for the domain, newest first. */
export function allDailyDates(domain: string): string[] {
  if (!DOMAIN_RE.test(domain)) return [];
  try {
    return fs
      .readdirSync(path.join(INTEL_DIR, "daily", domain))
      .filter((f) => f.endsWith(".json") && DATE_RE.test(f.slice(0, -5)))
      .map((f) => f.slice(0, -5))
      .filter((d) => daily(domain, d) !== null)
      .sort()
      .reverse();
  } catch {
    return [];
  }
}

export function daily(domain: string, date: string): Daily | null {
  if (!DOMAIN_RE.test(domain) || !DATE_RE.test(date)) return null;
  return parseDaily(readJson(path.join(INTEL_DIR, "daily", domain, `${date}.json`)), domain, date);
}

export function latestDaily(domain: string): Daily | null {
  const dates = allDailyDates(domain);
  return dates.length > 0 ? daily(domain, dates[0]) : null;
}

/** "2026-09-30" -> "Wed 30 Sep 2026" (UTC, so build timezone never shifts the day). */
export function fmtDay(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

// ---- pure presentation helpers shared by the daily surfaces (server components only: this module reads fs) --
/** Stable in-page anchor of a theater section. */
export const theaterAnchor = (t: { theater_id: string }, i: number): string =>
  `theater-${i}-${t.theater_id.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;

/** A short label for a theater: "US-Iran-Houthi confrontation over Hormuz and Red Sea" -> "US-Iran-Houthi confrontation". */
export function shortTheater(name: string): string {
  const head = name.split(/\s+(?:over|and|after|amid|during)\s+/i)[0].trim();
  return head.length >= 3 ? head : name;
}

/** First sentence of `s` (initials such as "U.S." do not end it). */
function firstSentence(s: string): string {
  const re = /[.!?]+(?=\s+[A-Z“"(\[]|$)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    if (/(^|[^A-Za-z])[A-Za-z]$/.test(s.slice(0, m.index))) continue;
    return s.slice(0, m.index + m[0].length);
  }
  return s;
}

/**
 * The claim in a passage: its first sentence, cut at a clause boundary when longer than `max`
 * (never mid-word, never before 45% of `max`). Text only; the full passage belongs behind a popover.
 */
export function claimOf(text: string, max = 120): string {
  const s = text.replace(/\s+/g, " ").trim();
  if (!s) return "";
  const one = firstSentence(s).replace(/[.!?]+$/, "");
  if (one.length <= max) return one;
  const min = Math.floor(max * 0.45);
  const lastWithin = (re: RegExp): number => {
    let best = -1;
    for (const m of one.matchAll(re)) {
      const i = m.index ?? -1;
      if (i >= min && i <= max && i > best) best = i;
    }
    return best;
  };
  const strong = lastWithin(/;|:\s| — |,\s+(?:while|as|but|with|and|then|after|though|amid|which|keeping|including)\b/g);
  const at = strong >= 0 ? strong : lastWithin(/,\s/g);
  if (at >= 0) return one.slice(0, at).trim();
  const words = one.slice(0, max).replace(/\s+\S*$/, "");
  return `${words || one.slice(0, max)}…`;
}

/** True when `claim` (from claimOf) leaves part of `full` unsaid. */
export const isCut = (full: string, claim: string): boolean => full.replace(/\s+/g, " ").trim().replace(/[.!?]+$/, "").length > claim.replace(/…$/, "").length;

/** "Saudi-Houthi exchange: Medina …" -> lead "Saudi-Houthi exchange", tail "Medina …". No short lead: all tail. */
export function splitLead(what: string): { lead: string; tail: string } {
  const i = what.indexOf(": ");
  if (i > 2 && i <= 56 && !/[.;]/.test(what.slice(0, i))) return { lead: what.slice(0, i), tail: what.slice(i + 2) };
  return { lead: "", tail: what };
}

/** The backend writes cross-theater links as "A -> B: text" (or "<->"). Returns the text and whether it runs both ways. */
export function crossParts(c: { theaters: string[]; link: string }): { mutual: boolean; text: string } {
  const i = c.link.indexOf(": ");
  const head = i > 0 ? c.link.slice(0, i) : "";
  const arrowed = /<->|->|→|↔/.test(head);
  return { mutual: !arrowed || /<->|↔/.test(head), text: arrowed ? c.link.slice(i + 2) : c.link };
}

/** "2026-10-01" -> "1 Oct" (UTC). Anything else passes through. */
export function shortDay(d: string): string {
  const dt = new Date(`${d}T00:00:00Z`);
  return Number.isNaN(dt.getTime()) ? d : dt.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}
