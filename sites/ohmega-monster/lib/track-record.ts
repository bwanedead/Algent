import { intelDoc } from "./store";

// The track record (backend `markets/`): Ohmega's own probability forecasts scored against Polymarket prices at the same instants, plus a paper portfolio.
// One document, `data/track-record.json`, written by `newsroom markets refresh|forecast`. Parsed defensively: a missing or malformed document is "nothing yet".
// PAPER ONLY: no money is staked and nothing here is financial advice; the page and the API say so.

export type Bucket = { low: number; high: number; n: number; mean_p: number; hit_rate: number };
export type DiffPoint = { n: number; at: string; diff: number };
export type Scores = {
  resolved_with_forecast: number;
  compared: number;
  brier_ours: number | null;
  brier_market: number | null;
  brier_ours_all: number | null;
  log_loss_ours: number | null;
  log_loss_market: number | null;
  brier_skill: number | null;
  calibration_ours: Bucket[];
  calibration_market: Bucket[];
  brier_diff_series: DiffPoint[];
  yes_rate: number | null;
  mean_forecast: number | null;
  verdict: string;
};
export type Portfolio = {
  bankroll: number;
  open: number;
  settled: number;
  staked_open: number;
  realised_pnl: number;
  unrealised_pnl: number;
  total_pnl: number;
  return_on_bankroll: number;
  wins: number;
  losses: number;
  hit_rate: number | null;
};
export type OpenPosition = {
  market_id: string; question: string; url: string; ends: string; side: "yes" | "no"; stake: number; entry: number;
  ours: number; market_at_open: number; market_now: number | null; value: number; pnl: number; opened: string; theaters: string[];
};
export type Disagreement = { market_id: string; question: string; url: string; ours: number; market: number; gap: number; made_at: string; rationale: string; theaters: string[] };
export type ResolvedRow = {
  market_id: string; question: string; url: string; resolved_at: string; outcome: "yes" | "no"; ours: number; market: number | null; made_at: string;
  brier_ours: number; brier_market: number | null; ours_closer: boolean | null; rationale: string; theaters: string[];
};
export type TrackRecord = {
  as_of: string;
  disclaimer: string;
  markets: { open: number; resolved: number; void: number };
  forecasts: number;
  scores: Scores;
  portfolio: Portfolio;
  open_positions: OpenPosition[];
  disagreements: Disagreement[];
  worst_misses: ResolvedRow[];
  market_beat_us: number;
  resolved: ResolvedRow[];
  other: {
    watches: { open: number; triggered: number; expired: number; invalidated: number; trigger_rate: number | null; note: string } | null;
    judgments: { resolved: number; void: number; open: number; brier: number | null; calibration: { range: string; count: number; hit_rate: number }[] } | null;
  };
  rules: { bankroll: number; edge_min: number; kelly_fraction: number; max_position_frac: number; max_exposure_frac: number; slippage: number; min_for_verdict: number };
};

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const n0 = (v: unknown): number => num(v) ?? 0;
const str = (v: unknown): string => (typeof v === "string" ? v : "");
const list = (v: unknown): Obj[] => (Array.isArray(v) ? v.filter(isObj) : []);
const httpOnly = (v: unknown): string => (/^https:\/\/polymarket\.com\//.test(str(v)) ? str(v) : "");

const bucket = (b: Obj): Bucket => ({ low: n0(b.low), high: n0(b.high), n: n0(b.n), mean_p: n0(b.mean_p), hit_rate: n0(b.hit_rate) });

function resolvedRow(r: Obj): ResolvedRow | null {
  const ours = num(r.ours);
  if (!str(r.question) || ours === null || (r.outcome !== "yes" && r.outcome !== "no")) return null;
  return {
    market_id: str(r.market_id), question: str(r.question), url: httpOnly(r.url), resolved_at: str(r.resolved_at), outcome: r.outcome, ours, market: num(r.market),
    made_at: str(r.made_at), brier_ours: n0(r.brier_ours), brier_market: num(r.brier_market), ours_closer: typeof r.ours_closer === "boolean" ? r.ours_closer : null,
    rationale: str(r.rationale), theaters: Array.isArray(r.theaters) ? r.theaters.filter((x): x is string => typeof x === "string") : [],
  };
}

export function parseTrackRecord(raw: unknown): TrackRecord | null {
  if (!isObj(raw) || raw.schema !== "ohmega.track-record/1") return null;
  const s = isObj(raw.scores) ? raw.scores : {};
  const p = isObj(raw.portfolio) ? raw.portfolio : {};
  const m = isObj(raw.markets) ? raw.markets : {};
  const other = isObj(raw.other) ? raw.other : {};
  const w = isObj(other.watches) ? other.watches : null;
  const j = isObj(other.judgments) ? other.judgments : null;
  const rules = isObj(raw.rules) ? raw.rules : {};
  return {
    as_of: str(raw.as_of),
    disclaimer: str(raw.disclaimer) || "Paper trading only. Not financial advice.",
    markets: { open: n0(m.open), resolved: n0(m.resolved), void: n0(m.void) },
    forecasts: n0(raw.forecasts),
    scores: {
      resolved_with_forecast: n0(s.resolved_with_forecast), compared: n0(s.compared), brier_ours: num(s.brier_ours), brier_market: num(s.brier_market),
      brier_ours_all: num(s.brier_ours_all), log_loss_ours: num(s.log_loss_ours), log_loss_market: num(s.log_loss_market), brier_skill: num(s.brier_skill),
      calibration_ours: list(s.calibration_ours).map(bucket), calibration_market: list(s.calibration_market).map(bucket),
      brier_diff_series: list(s.brier_diff_series).map((d) => ({ n: n0(d.n), at: str(d.at), diff: n0(d.diff) })),
      yes_rate: num(s.yes_rate), mean_forecast: num(s.mean_forecast), verdict: str(s.verdict),
    },
    portfolio: {
      bankroll: n0(p.bankroll), open: n0(p.open), settled: n0(p.settled), staked_open: n0(p.staked_open), realised_pnl: n0(p.realised_pnl),
      unrealised_pnl: n0(p.unrealised_pnl), total_pnl: n0(p.total_pnl), return_on_bankroll: n0(p.return_on_bankroll), wins: n0(p.wins), losses: n0(p.losses),
      hit_rate: num(p.hit_rate),
    },
    open_positions: list(raw.open_positions).map((r) => ({
      market_id: str(r.market_id), question: str(r.question), url: httpOnly(r.url), ends: str(r.ends), side: r.side === "no" ? "no" : "yes", stake: n0(r.stake),
      entry: n0(r.entry), ours: n0(r.ours), market_at_open: n0(r.market_at_open), market_now: num(r.market_now), value: n0(r.value), pnl: n0(r.pnl),
      opened: str(r.opened), theaters: Array.isArray(r.theaters) ? r.theaters.filter((x): x is string => typeof x === "string") : [],
    })),
    disagreements: list(raw.disagreements).map((r) => ({
      market_id: str(r.market_id), question: str(r.question), url: httpOnly(r.url), ours: n0(r.ours), market: n0(r.market), gap: n0(r.gap),
      made_at: str(r.made_at), rationale: str(r.rationale), theaters: Array.isArray(r.theaters) ? r.theaters.filter((x): x is string => typeof x === "string") : [],
    })),
    worst_misses: list(raw.worst_misses).map(resolvedRow).filter((r): r is ResolvedRow => r !== null),
    market_beat_us: n0(raw.market_beat_us),
    resolved: list(raw.resolved).map(resolvedRow).filter((r): r is ResolvedRow => r !== null),
    other: {
      watches: w ? { open: n0(w.open), triggered: n0(w.triggered), expired: n0(w.expired), invalidated: n0(w.invalidated), trigger_rate: num(w.trigger_rate), note: str(w.note) } : null,
      judgments: j
        ? { resolved: n0(j.resolved), void: n0(j.void), open: n0(j.open), brier: num(j.brier), calibration: list(j.calibration).map((c) => ({ range: str(c.range), count: n0(c.count), hit_rate: n0(c.hit_rate) })) }
        : null,
    },
    rules: {
      bankroll: n0(rules.bankroll), edge_min: n0(rules.edge_min), kelly_fraction: n0(rules.kelly_fraction), max_position_frac: n0(rules.max_position_frac),
      max_exposure_frac: n0(rules.max_exposure_frac), slippage: n0(rules.slippage), min_for_verdict: n0(rules.min_for_verdict),
    },
  };
}

/** The published track record, or null when none has been published yet. */
export async function trackRecord(): Promise<TrackRecord | null> {
  return parseTrackRecord(await intelDoc("data/track-record.json"));
}
