import { shortDay } from "./daily";
import type { EscalationPoint, Relation } from "./dossier";
import type { Direction } from "./intel";

// Pure presentation helpers for theater dossiers: dates, week grouping, "what changed" derivations and
// number formatting. No fs, no React.

const DAY_MS = 86_400_000;
const ISO = /\d{4}-\d{2}-\d{2}/;

/** The first valid YYYY-MM-DD in `s`, else "". */
export function isoDay(s: string): string {
  const m = s.match(ISO);
  return m && !Number.isNaN(Date.parse(`${m[0]}T00:00:00Z`)) ? m[0] : "";
}

const dayMs = (d: string) => Date.parse(`${d}T00:00:00Z`);

/** "2026-09-27" -> "27 Sep"; anything else passes through (and "" stays ""). */
export const dayLabel = (d: string): string => (isoDay(d) === d ? shortDay(d) : d);

/** How a timeline item's provenance reads: "daily report of 2 Oct", "deep brief of 17 Sept". */
export function fromLabel(from: string): string {
  const day = isoDay(from);
  const kind = /brief/i.test(from) ? "deep brief" : /geopolitics|daily|report/i.test(from) ? "daily report" : "";
  if (kind) return day ? `${kind} of ${dayLabel(day)}` : kind;
  return from.startsWith("/") ? "the report" : from;
}

/** Monday of the week containing `day` (YYYY-MM-DD), or "". */
export function weekStart(day: string): string {
  const t = dayMs(day);
  if (!Number.isFinite(t)) return "";
  const dow = (new Date(t).getUTCDay() + 6) % 7;
  return new Date(t - dow * DAY_MS).toISOString().slice(0, 10);
}

/** Consecutive items sharing a week, in the order given (callers sort first). Undated items form a "" week. */
export function groupByWeek<T>(items: T[], dayOf: (t: T) => string): { week: string; items: T[] }[] {
  const out: { week: string; items: T[] }[] = [];
  for (const it of items) {
    const week = weekStart(dayOf(it));
    const last = out[out.length - 1];
    if (last && last.week === week) last.items.push(it);
    else out.push({ week, items: [it] });
  }
  return out;
}

/** The current escalation run: its direction, the first report of the run, and what it replaced. */
export function escalationShift(h: EscalationPoint[]): { direction: Direction; since: string; was: Direction | null; first: boolean } | null {
  if (h.length === 0) return null;
  const last = h[h.length - 1];
  let i = h.length - 1;
  while (i > 0 && h[i - 1].direction === last.direction) i--;
  return { direction: last.direction, since: h[i].date, was: i > 0 ? h[i - 1].direction : null, first: i === 0 };
}

export const DIRECTION: Record<Direction, { glyph: string; word: string }> = {
  rising: { glyph: "▲", word: "rising" },
  steady: { glyph: "◆", word: "steady" },
  easing: { glyph: "▼", word: "easing" },
  unclear: { glyph: "?", word: "unclear" },
};

/** Change of a Pulse over the longest span of its own readings (about 7 days when it has them). null: no baseline yet. */
export function pulseChange(history: { at: string; position: number }[], position: number | null): { delta: number; period: string } | null {
  if (position === null) return null;
  const pts = history.map((h) => ({ t: Date.parse(h.at), v: h.position })).filter((h) => Number.isFinite(h.t)).sort((a, b) => a.t - b.t);
  if (pts.length < 2) return null;
  const asOf = pts[pts.length - 1].t;
  let base = pts[0];
  for (const p of pts) if (p.t <= asOf - 7 * DAY_MS) base = p;
  const hours = (asOf - base.t) / 3_600_000;
  if (hours < 1) return null;
  return { delta: position - base.v, period: hours < 48 ? `${Math.round(hours)}h` : `${Math.round(hours / 24)}d` };
}

export const fmtNum = (v: number): string => v.toLocaleString("en-GB", { maximumFractionDigits: 2 });
/** Big numbers shortened for a tile ("1.55M"); popovers keep the exact figure. */
export const fmtShort = (v: number): string => (Math.abs(v) >= 10000 ? v.toLocaleString("en-GB", { notation: "compact", maximumFractionDigits: 2 }) : fmtNum(v));
export const fmtPct = (p: number): string => `${p > 0 ? "▲ +" : p < 0 ? "▼ −" : "◆ "}${Math.abs(p) < 10 ? Math.abs(p).toFixed(1) : Math.round(Math.abs(p))}%`;

/** First paragraph(s) of `text` within roughly `budget` characters, and whether anything was left out. */
export function splitPrimer(text: string, budget = 760): { lead: string[]; rest: boolean } {
  const paras = text.split(/\n\s*\n/).map((p) => p.replace(/\s+/g, " ").trim()).filter(Boolean);
  const lead: string[] = [];
  let used = 0;
  for (const p of paras) {
    if (lead.length > 0 && used + p.length > budget) break;
    lead.push(p);
    used += p.length;
  }
  return { lead, rest: lead.length < paras.length };
}

/** Relations heaviest first (position = rank), then newest. */
export const byWeight = (a: Relation, b: Relation): number => b.count - a.count || (a.last_date < b.last_date ? 1 : a.last_date > b.last_date ? -1 : 0);
