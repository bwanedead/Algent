// Pure logic behind the /pulses wall: period change, sort orders, spiral layout. No node imports
// (it runs in the client component) and no React, so it is easy to reason about in isolation.
// Type-only imports from ./intel (which reads node:fs) are erased at build time, so this stays client-safe.
import type { Band, Confidence, Pulse } from "./intel";

/** One Pulse, flattened and serialisable: what every Pulse tile and popover is drawn from. */
export type WallPulse = {
  id: string;
  name: string;
  /** Who and what: what a tile, a popover and a link show. `name` stays the dimension's own name. */
  title: string;
  /** ISO alpha-2 of the principal actors (flags beside the title). */
  actors_iso2: string[];
  situation: string;
  question: string;
  low_end: string;
  high_end: string;
  position: number | null;
  band: Band;
  confidence: Confidence;
  last_assessed: string;
  history: { at: string; position: number }[];
  rationale: string;
};

/** A snapshot Pulse as a WallPulse, labelled with the title of the Situation it belongs to. */
export function toWallPulse(p: Pulse, situationTitle: string): WallPulse {
  return {
    id: p.id,
    name: p.name,
    title: p.title,
    actors_iso2: p.actors_iso2,
    situation: situationTitle,
    question: p.question,
    low_end: p.low_end,
    high_end: p.high_end,
    position: p.position,
    band: p.band,
    confidence: p.confidence,
    last_assessed: p.last_assessed,
    history: p.history,
    rationale: p.rationale,
  };
}

export const PERIODS = ["24h", "7d", "30d"] as const;
export type Period = (typeof PERIODS)[number];
export const DEFAULT_PERIOD: Period = "7d";
const PERIOD_MS: Record<Period, number> = { "24h": 86_400_000, "7d": 7 * 86_400_000, "30d": 30 * 86_400_000 };

export const SORTS = ["severity", "calm", "moves", "spiral", "recent"] as const;
export type SortKey = (typeof SORTS)[number];
export const DEFAULT_SORT: SortKey = "severity";
export const SORT_LABEL: Record<SortKey, string> = { severity: "Severity", calm: "Calm first", moves: "Biggest moves", spiral: "Spiral", recent: "Recent" };

export const parsePeriod = (v: string | null): Period => (PERIODS as readonly string[]).includes(v ?? "") ? (v as Period) : DEFAULT_PERIOD;
export const parseSort = (v: string | null): SortKey => (SORTS as readonly string[]).includes(v ?? "") ? (v as SortKey) : DEFAULT_SORT;

/** A Pulse plus the values the wall sorts and draws by, for the selected period. */
export type WallItem = { p: WallPulse; change: number | null; from: number | null };

/**
 * Change over the period: current position minus the latest history point at or before (asOf - period).
 * `from` is that baseline; both are null when the Pulse is unassessed or has no history that old.
 */
export function periodChange(p: WallPulse, period: Period, asOfMs: number): { change: number | null; from: number | null } {
  if (p.position === null || !Number.isFinite(asOfMs)) return { change: null, from: null };
  const cutoff = asOfMs - PERIOD_MS[period];
  let from: number | null = null;
  let best = -Infinity;
  for (const h of p.history) {
    const t = Date.parse(h.at);
    if (Number.isFinite(t) && t <= cutoff && t >= best) {
      best = t;
      from = h.position;
    }
  }
  return from === null ? { change: null, from: null } : { change: p.position - from, from };
}

const mag = (c: number | null) => (c === null ? -1 : Math.round(Math.abs(c) * 10) / 10);
const time = (s: string) => {
  const t = Date.parse(s);
  return Number.isFinite(t) ? t : -Infinity;
};

/** Movers first (largest |change|), then unchanged, then unknown. Ties fall back to severity. */
function byMove(a: WallItem, b: WallItem): number {
  const ma = mag(a.change);
  const mb = mag(b.change);
  const ra = ma > 0 ? 0 : ma === 0 ? 1 : 2;
  const rb = mb > 0 ? 0 : mb === 0 ? 1 : 2;
  return ra - rb || mb - ma || bySeverity(a, b);
}

function bySeverity(a: WallItem, b: WallItem): number {
  const pa = a.p.position;
  const pb = b.p.position;
  if (pa === null || pb === null) return pa === pb ? a.p.name.localeCompare(b.p.name) : pa === null ? 1 : -1;
  return pb - pa || a.p.name.localeCompare(b.p.name);
}

export function sortItems(items: WallItem[], sort: SortKey): WallItem[] {
  const out = items.slice();
  switch (sort) {
    case "calm":
      return out.sort((a, b) => {
        const pa = a.p.position;
        const pb = b.p.position;
        if (pa === null || pb === null) return pa === pb ? a.p.name.localeCompare(b.p.name) : pa === null ? 1 : -1;
        return pa - pb || a.p.name.localeCompare(b.p.name);
      });
    case "moves":
    case "spiral":
      return out.sort(byMove);
    case "recent":
      return out.sort((a, b) => time(b.p.last_assessed) - time(a.p.last_assessed) || bySeverity(a, b));
    default:
      return out.sort(bySeverity);
  }
}

/**
 * 1-based [row, column] cells for `n` tiles in a `cols`-wide grid, ordered as a square spiral from the
 * centre cell outward: the first tile takes the centre, later tiles ring it. The grid has
 * ceil(n/cols) rows; spiral cells that fall outside it are skipped, so any unfilled cells sit at the
 * outer edge (the end of the spiral), never inside it. No two tiles share a cell.
 */
export function spiralCells(n: number, cols: number): [number, number][] {
  if (n <= 0 || cols < 1) return [];
  const rows = Math.ceil(n / cols);
  let x = Math.floor((cols - 1) / 2);
  let y = Math.floor((rows - 1) / 2);
  const cells: [number, number][] = [];
  const dirs: [number, number][] = [[1, 0], [0, 1], [-1, 0], [0, -1]];
  let dir = 0;
  let run = 1;
  const inside = () => x >= 0 && x < cols && y >= 0 && y < rows;
  if (inside()) cells.push([y + 1, x + 1]);
  // Every in-bounds cell is reached once the spiral has grown past the longer side.
  const limit = 2 * Math.max(cols, rows) + 2;
  while (cells.length < n && run <= limit) {
    for (let leg = 0; leg < 2 && cells.length < n; leg++) {
      for (let s = 0; s < run && cells.length < n; s++) {
        x += dirs[dir][0];
        y += dirs[dir][1];
        if (inside()) cells.push([y + 1, x + 1]);
      }
      dir = (dir + 1) % 4;
    }
    run++;
  }
  return cells;
}
