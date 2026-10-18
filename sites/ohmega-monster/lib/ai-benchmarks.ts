import { intelDoc } from "./store";

// The AI benchmark tracker (backend `ai_benchmarks/`): frontier model scores across public benchmarks, collected on a timer and published as ONE document,
// `data/ai-benchmarks.json`. Everything charted here is derived on the backend (frontier, open vs closed, per-lab, saturation); this file only parses
// defensively: a missing or malformed document is "nothing yet". `claimed` rows are lab-claimed scores (blogs, model cards): never mixed with measured ones.

/** One point on a chart: date, score, model name, lab id. */
export type Pt = { d: string; s: number; m: string; l: string };
export type Top = Pt & { weights: string; lab_name: string };
export type Claim = Pt & { lab_name: string; url: string; weights: string; observed_on: string };
export type Bench = {
  id: string;
  name: string;
  source: string;
  source_url: string;
  unit: string;
  ceiling: number | null;
  baseline: number | null;
  released: string;
  superseded_by: string;
  n_models: number;
  n_results: number;
  /** Date of the newest measured result for this benchmark. */
  as_of: string;
  frontier: Pt[];
  best: (Pt & { weights: string }) | null;
  saturation: number | null;
  velocity: number | null;
  new_records: Pt[];
  open: Pt[];
  closed: Pt[];
  open_lag_days: number | null;
  gap: number | null;
  labs: Record<string, Pt[]>;
  top: Top[];
  claimed: Claim[];
};
export type SourceHealth = { source: string; name: string; last_ok: string; last_error: string; rows: number; newest_result: string; stale: boolean; reasons: string[]; page: string; licence: string };
export type LabRow = { id: string; name: string; models: number; records: number };
export type AiBenchmarks = { as_of: string; sources: SourceHealth[]; labs: LabRow[]; benchmarks: Bench[]; note: string };

type Raw = Record<string, unknown>;
const isObj = (v: unknown): v is Raw => typeof v === "object" && v !== null && !Array.isArray(v);
const list = (v: unknown): Raw[] => (Array.isArray(v) ? v.filter(isObj) : []);
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const n0 = (v: unknown): number => num(v) ?? 0;
const http = (v: unknown): string => (typeof v === "string" && /^https?:\/\//.test(v) ? v : "");

const pt = (r: Raw): Pt | null => (/^\d{4}-\d{2}-\d{2}/.test(str(r.d)) && num(r.s) !== null ? { d: str(r.d).slice(0, 10), s: n0(r.s), m: str(r.m), l: str(r.l) } : null);
const pts = (v: unknown): Pt[] => list(v).map(pt).filter((p): p is Pt => p !== null);

function bench(r: Raw): Bench | null {
  const id = str(r.id);
  if (!id) return null;
  const best = isObj(r.best) ? pt(r.best) : null;
  return {
    id, name: str(r.name) || id, source: str(r.source), source_url: http(r.source_url), unit: str(r.unit) || "fraction", ceiling: num(r.ceiling), baseline: num(r.baseline),
    released: str(r.released), superseded_by: str(r.superseded_by), n_models: n0(r.n_models), n_results: n0(r.n_results), as_of: str(r.as_of),
    frontier: pts(r.frontier), best: best && isObj(r.best) ? { ...best, weights: str(r.best.weights) } : null, saturation: num(r.saturation), velocity: num(r.velocity),
    new_records: pts(r.new_records), open: pts(r.open), closed: pts(r.closed), open_lag_days: num(r.open_lag_days), gap: num(r.gap),
    labs: isObj(r.labs) ? Object.fromEntries(Object.entries(r.labs).map(([k, v]) => [k, pts(v)])) : {},
    top: list(r.top).flatMap((t) => { const p = pt(t); return p ? [{ ...p, weights: str(t.weights), lab_name: str(t.lab_name) }] : []; }),
    claimed: list(r.claimed).flatMap((c) => { const p = pt(c); return p ? [{ ...p, lab_name: str(c.lab_name), url: http(c.url), weights: str(c.weights), observed_on: str(c.observed_on) }] : []; }),
  };
}

export function parseAiBenchmarks(raw: unknown): AiBenchmarks | null {
  if (!isObj(raw) || !Array.isArray(raw.benchmarks)) return null;
  const benchmarks = list(raw.benchmarks).map(bench).filter((b): b is Bench => b !== null);
  if (benchmarks.length === 0) return null;
  return {
    as_of: str(raw.as_of),
    sources: list(raw.sources).map((s) => ({
      source: str(s.source), name: str(s.name) || str(s.source), last_ok: str(s.last_ok), last_error: str(s.last_error), rows: n0(s.rows), newest_result: str(s.newest_result),
      stale: s.stale === true, reasons: Array.isArray(s.reasons) ? s.reasons.filter((x): x is string => typeof x === "string") : [], page: http(s.page), licence: str(s.licence),
    })),
    labs: list(raw.labs).map((l) => ({ id: str(l.id), name: str(l.name) || str(l.id), models: n0(l.models), records: n0(l.records) })),
    benchmarks,
    note: str(raw.note),
  };
}

/** The published AI benchmark document, or null when none has been published yet. */
export async function aiBenchmarks(): Promise<AiBenchmarks | null> {
  return parseAiBenchmarks(await intelDoc("data/ai-benchmarks.json"));
}

// ---- formatting (pure; shared by the page, the charts and the API note) --------------------------------------------------------------------

/** "89.6%" for a fraction, "1,532" for Elo and points, "11.9 h" for minutes. */
export function fmtScore(unit: string, s: number): string {
  if (unit === "fraction") return `${(s * 100).toFixed(1)}%`.replace(/\.0%$/, "%");
  if (unit === "minutes") return s >= 120 ? `${(s / 60).toFixed(1)} h` : `${s.toFixed(0)} min`;
  if (unit === "usd") return `$${Math.round(s).toLocaleString("en-US")}`;
  return Math.abs(s) >= 100 ? Math.round(s).toLocaleString("en-US") : s.toFixed(1);
}

/** A change in score units, signed ("+9.4 pts" for a fraction, "+16"). */
export function fmtDelta(unit: string, d: number): string {
  const sign = d > 0 ? "+" : d < 0 ? "-" : "";
  const a = Math.abs(d);
  return unit === "fraction" ? `${sign}${(a * 100).toFixed(1)} pts` : `${sign}${a >= 100 ? Math.round(a).toLocaleString("en-US") : a.toFixed(1)}`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-10-15" -> "15 Oct 2026"; anything else passes through. */
export function fmtDate(d: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1] ?? m[2]} ${m[1]}` : d;
}

/** Whole days from an ISO date to `now` (never negative). */
export function daysSince(d: string, now: Date = new Date()): number {
  const t = Date.parse(`${d.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(t) ? 0 : Math.max(0, Math.floor((now.getTime() - t) / 86_400_000));
}

/** "3 h ago", "2 days ago" from an ISO timestamp. */
export function ago(iso: string, now: Date = new Date()): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "never";
  const h = Math.max(0, (now.getTime() - t) / 3_600_000);
  return h < 1 ? "just now" : h < 48 ? `${Math.round(h)} h ago` : `${Math.round(h / 24)} days ago`;
}
