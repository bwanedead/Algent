// Data layer for the Situation Room (/intel) and the home teaser. Server-only: it reads the latest
// snapshot (via lib/intel) and the agent feeds (data/changes.json, data/forecasts.json) through
// lib/store.ts, defensively — a missing or malformed feed yields an empty section, never a failure.
//
// Client components must only `import type` from here (this file imports the server-only store).
import { bandAt } from "./band";
import { fmtUtc, latestSnapshot, type Band, type Coverage, type Outcome, type Snapshot } from "./intel";
import { PERIODS, toWallPulse, type Period, type WallPulse } from "./pulse-wall";
import { intelDoc } from "./store";

// ---- defensive coercion ---------------------------------------------------------------------
type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string => (typeof v === "string" ? v : typeof v === "number" ? String(v) : "");
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const SLUG = /^[\w.-]+$/;
const DAY = 86_400_000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const ms = (iso: string): number => {
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : NaN;
};

/** "2 Oct" (UTC). */
export function fmtShort(t: number): string {
  if (!Number.isFinite(t)) return "";
  const d = new Date(t);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

// ---- 1. biggest moves -----------------------------------------------------------------------
const PERIOD_MS: Record<Period, number> = { "24h": DAY, "7d": 7 * DAY, "30d": 30 * DAY };

export type SituationMove = {
  pulse: WallPulse;
  from: number;
  to: number;
  delta: number;
  /** When the latest reading was taken (drives the "new since your last visit" dot). */
  at: string;
  /** True when the Pulse is younger than the period, so `from` is its first reading, not a reading at the period's start. */
  firstReading: boolean;
  fromBand: Band;
  toBand: Band;
};
export type MovesView = { top: SituationMove[]; crossed: number };
export type MovesByPeriod = Record<Period, MovesView>;

/**
 * Change over a period: the latest reading at or before (asOf − period) is the baseline; a Pulse
 * younger than the period is measured from its first reading (flagged), since its whole life is
 * inside the window. Null when there is nothing to compare (one reading, or no change).
 */
function moveOver(p: WallPulse, period: Period, asOfMs: number): SituationMove | null {
  const to = p.position;
  if (to === null) return null;
  const pts = p.history
    .map((h) => ({ t: ms(h.at), v: h.position, at: h.at }))
    .filter((h) => Number.isFinite(h.t))
    .sort((a, b) => a.t - b.t);
  if (pts.length === 0) return null;
  const cutoff = asOfMs - PERIOD_MS[period];
  let base: (typeof pts)[number] | null = null;
  for (const h of pts) if (h.t <= cutoff) base = h;
  const firstReading = base === null;
  if (base === null) base = pts[0];
  const last = pts[pts.length - 1];
  if (base.t >= last.t) return null;
  const delta = to - base.v;
  if (Math.round(delta * 10) === 0) return null;
  return { pulse: p, from: base.v, to, delta, at: last.at, firstReading, fromBand: bandAt(base.v), toBand: bandAt(to) };
}

function movesView(pulses: WallPulse[], period: Period, asOfMs: number, n: number): MovesView {
  const all = pulses.map((p) => moveOver(p, period, asOfMs)).filter((m): m is SituationMove => m !== null);
  all.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta) || b.to - a.to || a.pulse.name.localeCompare(b.pulse.name));
  return { top: all.slice(0, n), crossed: all.filter((m) => m.fromBand !== m.toBand).length };
}

// ---- 2. coverage ----------------------------------------------------------------------------
export type CoverageItem = {
  id: string;
  name: string;
  coverage: Coverage;
  /** Share of the world's headlines, in percent. */
  share: number;
  recent: number;
  prior: number;
  days: string[];
  counts: number[];
  href: string | null;
  hrefLabel: string;
};
export type CoverageView = { gaining: boolean; items: CoverageItem[] };

function coverageView(snap: Snapshot): CoverageView {
  const link = (t: Snapshot["theaters"][number]): { href: string | null; hrefLabel: string } => {
    if (t.brief && SLUG.test(t.brief)) return { href: `/intel/briefs/${t.brief}`, hrefLabel: "Brief" };
    const day = [...snap.daily].sort((a, b) => b.date.localeCompare(a.date)).find((d) => d.theaters.some((x) => x.theater_id === t.id));
    return day ? { href: `/geopolitics/${day.date}`, hrefLabel: "Daily" } : { href: null, hrefLabel: "" };
  };
  const item = (t: Snapshot["theaters"][number]): CoverageItem => ({
    id: t.id,
    name: t.name,
    coverage: t.coverage,
    share: t.heat,
    recent: t.recent,
    prior: t.prior,
    days: t.series.map((s) => s.day),
    counts: t.series.map((s) => s.count),
    ...link(t),
  });
  const gaining = snap.theaters
    .filter((t) => t.coverage === "rising" || t.coverage === "new")
    .sort((a, b) => b.recent - b.prior - (a.recent - a.prior) || b.heat - a.heat);
  if (gaining.length > 0) return { gaining: true, items: gaining.slice(0, 5).map(item) };
  // Nothing is gaining: say so, and show the most-covered Theaters for context.
  return { gaining: false, items: [...snap.theaters].sort((a, b) => b.heat - a.heat).slice(0, 3).map(item) };
}

// ---- 3. forecasts ---------------------------------------------------------------------------
export type ForecastPin = {
  id: string;
  statement: string;
  probability: number;
  horizon: string;
  horizonMs: number | null;
  basis: string;
  yes: string;
  no: string;
  briefUrl: string | null;
  theater: string;
  madeAt: string;
};
export type ResolvedItem = {
  key: string;
  statement: string;
  probability: number;
  outcome: Outcome;
  resolvedAt: string;
  whenLabel: string;
  evidence: string;
  /** The outcome went against the stated probability (a 30% call that happened, a 70% call that did not). */
  against: boolean;
};
export type ForecastsView = {
  open: ForecastPin[];
  resolved: ResolvedItem[];
  scorecard: Snapshot["forecasts"]["scorecard"];
  asOfMs: number;
};

const prob = (v: unknown): number | null => {
  const n = num(v);
  return n === null ? null : Math.min(99, Math.max(1, Math.round(n)));
};
const briefUrl = (url: string, slug: string): string | null =>
  /^\/intel\/briefs\/[\w.-]+$/.test(url) ? url : SLUG.test(slug) ? `/intel/briefs/${slug}` : null;
const dated = (h: string): number | null => (/^\d{4}-\d{2}-\d{2}/.test(h) && Number.isFinite(ms(h)) ? ms(h) : null);

function openForecasts(snap: Snapshot, feed: unknown): ForecastPin[] {
  const fromFeed: ForecastPin[] = isObj(feed)
    ? arr(feed.forecasts)
        .filter(isObj)
        .filter((o) => !str(o.status) || str(o.status) === "open")
        .map((o, i): ForecastPin | null => {
          const probability = prob(o.probability);
          const statement = str(o.statement);
          if (!statement || probability === null) return null;
          const horizon = str(o.horizon);
          return {
            id: str(o.id) || `fc-${i}`,
            statement,
            probability,
            horizon,
            horizonMs: dated(horizon),
            basis: str(o.basis),
            yes: str(o.resolves_yes_if),
            no: str(o.resolves_no_if),
            briefUrl: briefUrl(str(o.brief_url), str(o.brief_slug)),
            theater: str(o.theater),
            madeAt: str(o.made_at),
          };
        })
        .filter((f): f is ForecastPin => f !== null)
    : [];
  const open =
    fromFeed.length > 0
      ? fromFeed
      : snap.forecasts.open.map((o, i): ForecastPin => ({
          id: `fc-${i}`,
          statement: o.statement,
          probability: o.probability,
          horizon: o.horizon,
          horizonMs: dated(o.horizon),
          basis: "",
          yes: "",
          no: "",
          briefUrl: briefUrl("", o.brief_slug),
          theater: o.theater_name,
          madeAt: "",
        }));
  return open.sort((a, b) => (a.horizonMs ?? Infinity) - (b.horizonMs ?? Infinity));
}

function resolvedForecasts(snap: Snapshot): ResolvedItem[] {
  return snap.forecasts.resolved
    .map((r, i): ResolvedItem => ({
      key: `${r.resolved_at}-${i}`,
      statement: r.statement,
      probability: r.probability,
      outcome: r.outcome,
      resolvedAt: r.resolved_at,
      whenLabel: fmtShort(ms(r.resolved_at)),
      evidence: r.evidence,
      against: (r.outcome === "yes" && r.probability < 50) || (r.outcome === "no" && r.probability > 50),
    }))
    .sort((a, b) => (ms(b.resolvedAt) || 0) - (ms(a.resolvedAt) || 0))
    .slice(0, 5);
}

// The due-soon timeline: a window of the next ~60 days, widened only as far as it takes to show a
// few markers (a young record has few near horizons), with markers lane-stacked so none overlap.
export type TimelinePin = ForecastPin & { pos: number; lane: number };
export type Timeline = {
  days: number;
  pins: TimelinePin[];
  lanes: number;
  ticks: { pos: number; label: string }[];
  /** Open forecasts that resolve after the window (reachable through "all open forecasts"). */
  later: number;
};
const WINDOWS = [60, 120, 180, 365, 730];
const LANE_GAP = 11; // percent of the track: keeps 30px markers apart on a 280px track

export function buildTimeline(open: ForecastPin[], asOfMs: number): Timeline {
  const startMs = Math.floor(asOfMs / DAY) * DAY;
  const datedOpen = open.filter((f): f is ForecastPin & { horizonMs: number } => f.horizonMs !== null);
  const within = (days: number) => datedOpen.filter((f) => f.horizonMs <= startMs + days * DAY).length;
  const want = Math.min(3, datedOpen.length);
  let days = WINDOWS.find((d) => within(d) >= want) ?? 0;
  if (!days) days = datedOpen.length ? Math.ceil((datedOpen[datedOpen.length - 1].horizonMs - startMs) / DAY) + 7 : WINDOWS[0];
  const endMs = startMs + days * DAY;
  const inWindow = datedOpen.filter((f) => f.horizonMs <= endMs);
  const laneEnds: number[] = [];
  const pins = inWindow.map((f) => {
    const pos = Math.min(100, Math.max(0, ((f.horizonMs - startMs) / (endMs - startMs)) * 100)); // overdue pins sit at "Today"
    let lane = laneEnds.findIndex((end) => pos - end >= LANE_GAP);
    if (lane < 0) lane = laneEnds.length;
    laneEnds[lane] = pos;
    return { ...f, pos, lane };
  });
  const ticks: Timeline["ticks"] = [{ pos: 0, label: "Today" }];
  const s = new Date(startMs);
  let y = s.getUTCFullYear();
  let m = s.getUTCMonth() + 1;
  for (;;) {
    if (m > 11) {
      m = 0;
      y += 1;
    }
    const t = Date.UTC(y, m, 1);
    if (t > endMs) break;
    const pos = ((t - startMs) / (endMs - startMs)) * 100;
    if (pos >= 9 && pos <= 96 && (days <= 400 || m % 3 === 0)) ticks.push({ pos, label: m === 0 ? `Jan ${y}` : MONTHS[m] });
    m += 1;
  }
  return { days, pins, lanes: Math.max(1, laneEnds.length), ticks, later: open.length - pins.length };
}

// ---- 4. what is new -------------------------------------------------------------------------
export type ChangeItem = {
  key: string;
  kind: "brief" | "daily" | "pulses";
  at: string;
  whenLabel: string;
  title: string;
  detail: string;
  href: string;
};
const firstSentence = (s: string, max = 150): string => {
  const cut = s.search(/[.!?]\s/);
  const one = cut > 0 ? s.slice(0, cut + 1) : s;
  return one.length > max ? `${one.slice(0, max - 1).trimEnd()}…` : one;
};

function changes(snap: Snapshot, feed: unknown): { news: ChangeItem[]; times: string[] } {
  const bl = new Map(snap.briefs.map((b) => [b.slug, b.bottom_line]));
  const items: ChangeItem[] = [];
  const times: string[] = [];
  const created = new Map<string, { at: string; pulses: { id: string; name: string; position: number | null; band: Band }[] }>();
  const events = isObj(feed) ? arr(feed.events).filter(isObj) : [];

  for (const e of events) {
    const type = str(e.type);
    const at = str(e.at);
    if (!Number.isFinite(ms(at))) continue;
    if (type === "brief_published" && SLUG.test(str(e.slug))) {
      items.push({
        key: `b-${str(e.slug)}`,
        kind: "brief",
        at,
        whenLabel: fmtShort(ms(at)),
        title: str(e.title) || str(e.theater),
        detail: firstSentence(bl.get(str(e.slug)) ?? ""),
        href: `/intel/briefs/${str(e.slug)}`,
      });
      times.push(at);
    } else if (type === "daily_published" && str(e.headline)) {
      const url = str(e.url);
      items.push({
        key: `d-${str(e.date)}-${str(e.domain)}`,
        kind: "daily",
        at,
        whenLabel: fmtShort(ms(at)),
        title: str(e.headline),
        detail: "",
        href: /^\/geopolitics(\/[\w.-]+)?$/.test(url) ? url : "/geopolitics",
      });
      times.push(at);
    } else if (type === "pulse_created" && str(e.name)) {
      const k = at.slice(0, 16);
      const g = created.get(k) ?? { at, pulses: [] };
      const position = num(e.position);
      g.pulses.push({ id: str(e.pulse_id), name: str(e.name), position, band: position === null ? "unassessed" : bandAt(position) });
      created.set(k, g);
    } else if (type === "pulse_moved" || type === "forecast_made" || type === "forecast_resolved") {
      times.push(at);
    }
  }

  for (const [k, g] of created) {
    const n = g.pulses.length;
    const one = g.pulses[0];
    items.push({
      key: `p-${k}`,
      kind: "pulses",
      at: g.at,
      whenLabel: fmtShort(ms(g.at)),
      title: n === 1 ? one.name : `${n} new Pulses: ${g.pulses.slice(0, 2).map((p) => p.name).join(", ")}${n > 2 ? ` and ${n - 2} more` : ""}`,
      detail: n === 1 && one.position !== null ? `Starts at ${Math.round(one.position)} of 100` : "",
      href: n === 1 && one.id ? `/pulses#pulse-${one.id}` : "/pulses",
    });
    times.push(g.at);
  }

  if (items.length === 0) {
    // No change feed: fall back to what the snapshot itself knows.
    for (const b of snap.briefs)
      if (Number.isFinite(ms(b.as_of)))
        items.push({ key: `b-${b.slug}`, kind: "brief", at: b.as_of, whenLabel: fmtShort(ms(b.as_of)), title: b.title, detail: firstSentence(b.bottom_line), href: `/intel/briefs/${b.slug}` });
    for (const d of snap.daily)
      if (Number.isFinite(ms(d.date)))
        items.push({ key: `d-${d.date}`, kind: "daily", at: d.date, whenLabel: fmtShort(ms(d.date)), title: d.headline, detail: "", href: `/geopolitics/${d.date}` });
    times.push(...items.map((i) => i.at));
  }

  items.sort((a, b) => ms(b.at) - ms(a.at));
  return { news: items.slice(0, 5), times };
}

// ---- the room -------------------------------------------------------------------------------
export type SituationRoom = {
  asOfLabel: string;
  moves: MovesByPeriod;
  coverage: CoverageView;
  forecasts: ForecastsView;
  news: ChangeItem[];
  /** Timestamps of everything that changed (for the "N new since your last visit" count). */
  changeTimes: string[];
};

export async function situationRoom(): Promise<SituationRoom | null> {
  const snap = await latestSnapshot();
  if (!snap) return null;
  const [forecastsFeed, changesFeed] = await Promise.all([intelDoc("data/forecasts.json"), intelDoc("data/changes.json")]);
  const pulses = snap.situations.flatMap((s) => s.pulses.map((p) => toWallPulse(p, s.title)));
  let asOfMs = ms(snap.built_at);
  if (!Number.isFinite(asOfMs)) {
    asOfMs = -Infinity;
    for (const p of pulses) for (const h of p.history) asOfMs = Math.max(asOfMs, ms(h.at) || -Infinity);
    if (!Number.isFinite(asOfMs)) asOfMs = Date.now();
  }
  const moves = Object.fromEntries(PERIODS.map((p) => [p, movesView(pulses, p, asOfMs, 5)])) as MovesByPeriod;
  const { news, times } = changes(snap, changesFeed);
  return {
    asOfLabel: snap.built_at ? fmtUtc(snap.built_at) : "—",
    moves,
    coverage: coverageView(snap),
    forecasts: { open: openForecasts(snap, forecastsFeed), resolved: resolvedForecasts(snap), scorecard: snap.forecasts.scorecard, asOfMs },
    news,
    changeTimes: times,
  };
}
