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
// The trader (backend `markets/trader*.py`): an agent that manages its own paper book from the same $10k, once a day. Its equity curve is set against the
// mechanical rule-based baseline and against the flat bankroll (doing nothing).
export type CurvePoint = { day: string; flat: number; trader: number | null; rule: number | null };
export type TraderSummary = {
  equity: number; pnl: number; cash: number; realised: number; unrealised: number; open: number; buys: number; sells: number;
  closed: number; wins: number; losses: number; hit_rate: number | null;
};
// One corpus item a decision cited: where it came from and, when the site has a page for it, a same-site link ("" otherwise).
export type TrailItem = { id: string; kind: string; title: string; date: string; href: string };
export type TraderPosition = {
  market_id: string; question: string; url: string; ends: string; side: "yes" | "no"; shares: number; entry: number; now: number | null; cost: number;
  value: number; pnl: number; opened: string; rationale: string; rationale_on: string; ours: number | null;
  evidence: "" | "sufficient" | "thin" | "gap"; trail: TrailItem[];
  // Additive: when it ends (to the minute, UTC) and hours left; null on documents from before the day book.
  ends_at: string; hours_left: number | null; now_at: string;
};
export type TradeRow = {
  id: string; market_id: string; question: string; url: string; day: string; action: "buy_yes" | "buy_no" | "sell" | "settle"; side: "yes" | "no";
  price: number; stake: number; shares: number; pnl: number | null; result: "" | "won" | "lost" | "void"; outcome: string; rationale: string;
  ours: number | null; market: number | null; clips: string[];
};
export type Trader = {
  summary: TraderSummary;
  rule: Portfolio;
  curve: CurvePoint[];
  open_positions: TraderPosition[];
  log: TradeRow[];
  today: { decided: number; bought: number; sold: number; held: number; clipped: number };
  since: string;
  last_at: string;
  limits: { bankroll: number; max_position_frac: number; max_exposure_frac: number; slippage: number; min_ticket: number };
};
// The fast book (backend `markets/books.py`): the same trader on markets that settle within days, decided every few hours. Shaped like the daily trader.
// A roster strategy (backend `markets/strategies.py`): every bot is its own forecaster. Shaped like the day book plus what it is and when it runs next.
// Additive: its own forecast feedback (scored apart from trading; Brier null until `min_resolved` forecasts have resolved), its share of the bankroll at risk against the
// activity floor, and how the floor-tagged positions did against chosen ones. A document from before these existed parses to zeros.
export type ForecastRow = { market_id: string; question: string; at: string; p: number; market: number | null; confidence: string; outcome: string; reason: string };
// Additive: mean of (market Brier - bot Brier) over one forecast per resolved market, positive = ahead of the market price; mean/se are null until `shown` (n >= min_resolved).
export type SkillBlock = { n: number; shown: boolean; mean: number | null; se: number | null };
export type ForecastStats = { skill: { all: SkillBlock; contested: SkillBlock }; made: number; resolved: number; min_resolved: number; shown: boolean; brier: number | null; brier_market: number | null; skill_vs_market: number | null; recent: ForecastRow[] };
// A paper limit order a bot left to wait between its runs (backend `markets/resting.py`). `limit` is the all-in price per share on its own side; a buy fills at or
// below it, a sell at or above it. `usd` sizes a buy, `fraction` a sell. `now` is the latest price on its side (null when none is on file).
export type RestingOrder = {
  id: string; market_id: string; question: string; url: string; action: "buy_yes" | "buy_no" | "sell"; side: string; limit: number; usd: number; fraction: number; now: number | null;
  p_yes: number; reason: string; placed_at: string; expires_at: string;
};
export type RestingFill = { id: string; order_id: string; market_id: string; question: string; action: string; side: string; price: number; stake: number; at: string };
export type RestingSection = { open: RestingOrder[]; fills: RestingFill[] };
export type Strategy = DayBookBase & {
  id: string; name: string; method: string; method_name: string; style: string; must_trade: boolean; min_orders: number; next_run: string;
  bot: string; bot_name: string; desk: string; desk_name: string; desk_about: string; min_fills_day: number;   // bot = reasoning method stack, desk = cadence/horizon; one book per pair
  forecasts: ForecastStats; exposure: { pct: number; floor_pct: number } | null; floor: { opened: number; groups: DayGroup[] } | null; resting: RestingSection;
};
export type FastBook = Trader & { horizon_days: number; every_hours: number; enabled: boolean };
// The day book (backend `markets/day*.py`): an agent that browses Polymarket itself and chooses its own 0-2 day bets, three runs a day. Shaped like the daily
// trader plus its own parts. A horizon/category group's win rate and P&L are null (shown=false) until it holds min_for_verdict closed trades.
export type DayGroup = { label: string; n: number; shown: boolean; wins: number | null; hit_rate: number | null; pnl: number | null };
export type DayOrder = { market_id: string; question: string; action: string; side: string; stake: number; requested: number; price: number; reason: string; clips: string[] };
export type DayRunRow = {
  id: string; at: string; usd: number; turns: number; tool_calls: number; stopped: string; summary: string; considered: { id: string; question: string; ends: string }[];
  n_considered: number; queries: string[]; n_queries: number; orders: DayOrder[]; equity: number | null; must_trade: string;   // "" unless the strategy must trade ("met: 2 of 2" / "unmet: 1 of 2")
};
// What the agent wished the corpus held (product feedback on which data sources to add), merged across runs.
export type WishRow = { topic: string; runs: number; asks: number; why: string; source: string; last: string; markets: { market_id: string; question: string }[] };
export type DayBook = DayBookBase;
export type DayBookBase = Trader & {
  horizon_hours: number; run_hours: number[]; run_minute: number; enabled: boolean; min_for_verdict: number; spend_usd: number; spend_today: number; avg_hold_h: number | null;
  by_horizon: DayGroup[]; by_category: DayGroup[]; runs: DayRunRow[]; wishes: WishRow[]; watchlist: { market_id: string; question: string; note: string; since: string }[];
  caps: { max_usd_per_day: number; max_usd_per_run: number };
};
// How the corpus served the bots (backend `markets/research_report.py`). Every ratio can be null: nothing to divide yet.
export type Coverage = { n: number; rated: number; sufficient: number; thin: number; gap: number; share_sufficient: number | null; share_gap_requested: number | null };
export type GapRow = { topic: string; asks: number; why: string; last: string; status: "open" | "tried" | "filled"; filled: string; markets: { market_id: string; question: string }[] };
// A group's numbers are withheld (shown=false, nulls) until it holds min_for_verdict resolved items.
export type EvidenceGroup = { label: string; n: number; shown: boolean; brier_ours: number | null; brier_market: number | null; skill: number | null };
export type EvidenceMoney = { label: string; n: number; shown: boolean; pnl: number | null; hit_rate: number | null };
// Did each bot-requested research run help (backend `markets/gap_loop.py`)? Counts of later asks and cites; edge (market Brier minus ours) is null until both sides hold min_for_verdict.
export type LoopVerdict = "answered" | "unused" | "asked again" | "too early" | "unlinked";
export type LoopRow = {
  topic: string; at: string; asks: number; refill: boolean; verdict: LoopVerdict; linked: boolean; reasks_before: number; reasks_after: number;
  returned_after: number | null; cited_after: number | null; decisions_after: number;
  edge: { shown: boolean; min: number; n_before: number; n_after: number; before: number | null; after: number | null };
};
export type GapLoop = {
  fills: number; failed: number; answered: number; unused: number; asked_again: number; too_early: number; unlinked: number; usd: number; rows: LoopRow[];
  min_for_verdict: number; settle_days: number; reask_min: number; basis: string;
};
export type Evidence = {
  coverage: Coverage & { forecasts: Coverage; trades: Coverage };
  citations: { n: number; mean: number | null; median: number | null; none_share: number | null };
  tools: {
    traces: number; corpus: number; fallback: number; queries: number; by_tool: Record<string, number>; mean_results: number | null; empty_share: number | null;
    error_share: number | null; median_latency_ms: number | null; mean_usd: number | null; mean_tokens: number | null; mean_rounds: number | null;
  };
  top_gaps: GapRow[];
  accuracy: { rich_min_cited: number; min_for_verdict: number; forecasts: EvidenceGroup[]; trades: EvidenceMoney[]; note: string };
  caps: { rounds: number; queries_per_round: number; rows_per_query: number; gap_fill_usd_per_day: number; corpus_only: boolean };
  gap_spend: { asks: number; fills: number; usd: number };
  loop: GapLoop | null;
};
export type BookHorizon = { positions: number; resolved: number; median_days_to_resolution: number | null; mean_days_to_resolution: number | null };
export type Horizons = { by_horizon: EvidenceGroup[]; min_for_verdict: number; books: Record<string, BookHorizon> };
export type TrackRecord = {
  as_of: string;
  disclaimer: string;
  markets: { open: number; resolved: number; void: number };
  forecasts: number;
  trader: Trader;
  fast: FastBook | null;
  day: DayBook | null;
  // Additive: one section per roster strategy, in roster order. Empty on documents from before the roster (the page then falls back to trader / fast / day).
  strategies: Strategy[];
  evidence: Evidence | null;
  horizons: Horizons | null;
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

const verdict = (v: unknown): "" | "sufficient" | "thin" | "gap" => (v === "sufficient" || v === "thin" || v === "gap" ? v : "");
// Only same-site paths are kept as links; anything else is shown as plain text.
const sitePath = (v: unknown): string => (typeof v === "string" && v.startsWith("/") && !v.startsWith("//") ? v : "");
const trailItem = (t: Obj): TrailItem => ({ id: str(t.id), kind: str(t.kind), title: str(t.title) || str(t.id), date: str(t.date), href: sitePath(t.href) });

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

const portfolio = (p: Obj): Portfolio => ({
  bankroll: n0(p.bankroll), open: n0(p.open), settled: n0(p.settled), staked_open: n0(p.staked_open), realised_pnl: n0(p.realised_pnl),
  unrealised_pnl: n0(p.unrealised_pnl), total_pnl: n0(p.total_pnl), return_on_bankroll: n0(p.return_on_bankroll), wins: n0(p.wins), losses: n0(p.losses),
  hit_rate: num(p.hit_rate),
});

// A document from before the trader existed (schema /1) parses to an empty trader, so the page shows "not started" rather than failing.
function parseTrader(raw: unknown, fallbackRule: Portfolio): Trader {
  const t = isObj(raw) ? raw : {};
  const s = isObj(t.summary) ? t.summary : {};
  const lim = isObj(t.limits) ? t.limits : {};
  const td = isObj(t.today) ? t.today : {};
  return {
    summary: {
      equity: n0(s.equity), pnl: n0(s.pnl), cash: n0(s.cash), realised: n0(s.realised), unrealised: n0(s.unrealised), open: n0(s.open), buys: n0(s.buys),
      sells: n0(s.sells), closed: n0(s.closed), wins: n0(s.wins), losses: n0(s.losses), hit_rate: num(s.hit_rate),
    },
    rule: isObj(t.rule) ? portfolio(t.rule) : fallbackRule,
    curve: list(t.curve).map((c) => ({ day: str(c.day), flat: n0(c.flat), trader: num(c.trader), rule: num(c.rule) })),
    open_positions: list(t.open_positions).map((r) => ({
      market_id: str(r.market_id), question: str(r.question), url: httpOnly(r.url), ends: str(r.ends), side: r.side === "no" ? "no" : "yes", shares: n0(r.shares),
      entry: n0(r.entry), now: num(r.now), cost: n0(r.cost), value: n0(r.value), pnl: n0(r.pnl), opened: str(r.opened), rationale: str(r.rationale),
      rationale_on: str(r.rationale_on), ours: num(r.ours), evidence: verdict(r.evidence), trail: list(r.trail).map(trailItem),
      ends_at: str(r.ends_at), hours_left: num(r.hours_left), now_at: str(r.now_at),
    })),
    log: list(t.log).map((r) => ({
      id: str(r.id), market_id: str(r.market_id), question: str(r.question), url: httpOnly(r.url), day: str(r.day),
      action: r.action === "buy_no" || r.action === "sell" || r.action === "settle" ? r.action : "buy_yes", side: r.side === "no" ? "no" : "yes",
      price: n0(r.price), stake: n0(r.stake), shares: n0(r.shares), pnl: num(r.pnl),
      result: r.result === "won" || r.result === "lost" || r.result === "void" ? r.result : "", outcome: str(r.outcome), rationale: str(r.rationale),
      ours: num(r.ours), market: num(r.market), clips: Array.isArray(r.clips) ? r.clips.filter((x): x is string => typeof x === "string") : [],
    })),
    today: { decided: n0(td.decided), bought: n0(td.bought), sold: n0(td.sold), held: n0(td.held), clipped: n0(td.clipped) },
    since: str(t.since),
    last_at: str(t.last_at),
    limits: {
      bankroll: n0(lim.bankroll) || fallbackRule.bankroll, max_position_frac: n0(lim.max_position_frac), max_exposure_frac: n0(lim.max_exposure_frac),
      slippage: n0(lim.slippage), min_ticket: n0(lim.min_ticket),
    },
  };
}

function parseFast(raw: unknown, fallbackRule: Portfolio): FastBook | null {
  if (!isObj(raw)) return null;
  return { ...parseTrader(raw, fallbackRule), horizon_days: n0(raw.horizon_days), every_hours: n0(raw.every_hours), enabled: raw.enabled === true };
}

const dayGroup = (g: Obj): DayGroup => ({ label: str(g.label), n: n0(g.n), shown: g.shown === true, wins: num(g.wins), hit_rate: num(g.hit_rate), pnl: num(g.pnl) });
const strs = (v: unknown): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);

// A document from before the day book existed has none: the page then shows nothing for it.
function parseDay(raw: unknown, fallbackRule: Portfolio): DayBook | null {
  if (!isObj(raw)) return null;
  const lim = isObj(raw.limits) ? raw.limits : {};
  return {
    ...parseTrader(raw, fallbackRule), horizon_hours: n0(raw.horizon_hours), run_hours: (Array.isArray(raw.run_hours) ? raw.run_hours : []).map(n0), run_minute: n0(raw.run_minute),
    enabled: raw.enabled === true, min_for_verdict: n0(raw.min_for_verdict), spend_usd: n0(raw.spend_usd), spend_today: n0(raw.spend_today), avg_hold_h: num(raw.avg_hold_h),
    by_horizon: list(raw.by_horizon).map(dayGroup), by_category: list(raw.by_category).map(dayGroup),
    runs: list(raw.runs).map((r) => ({
      id: str(r.id), at: str(r.at), usd: n0(r.usd), turns: n0(r.turns), tool_calls: n0(r.tool_calls), stopped: str(r.stopped), summary: str(r.summary),
      considered: list(r.considered).map((c) => ({ id: str(c.id), question: str(c.question), ends: str(c.ends) })), n_considered: n0(r.n_considered), queries: strs(r.queries),
      n_queries: n0(r.n_queries), equity: num(r.equity), must_trade: str(r.must_trade),
      orders: list(r.orders).map((o) => ({ market_id: str(o.market_id), question: str(o.question), action: str(o.action), side: str(o.side), stake: n0(o.stake), requested: n0(o.requested), price: n0(o.price), reason: str(o.reason), clips: strs(o.clips) })),
    })),
    wishes: list(raw.wishes).map((w) => ({
      topic: str(w.topic), runs: n0(w.runs), asks: n0(w.asks), why: str(w.why), source: str(w.source), last: str(w.last),
      markets: list(w.markets).map((m) => ({ market_id: str(m.market_id), question: str(m.question) })),
    })),
    watchlist: list(raw.watchlist).map((w) => ({ market_id: str(w.market_id), question: str(w.question), note: str(w.note), since: str(w.since) })),
    caps: { max_usd_per_day: n0(lim.max_usd_per_day), max_usd_per_run: n0(lim.max_usd_per_run) },
  };
}

function parseSkill(raw: unknown): SkillBlock {
  const b = isObj(raw) ? raw : {};
  return { n: n0(b.n), shown: b.shown === true, mean: num(b.mean), se: num(b.se) };
}

function parseForecasts(raw: unknown): ForecastStats {
  const f = isObj(raw) ? raw : {};
  const k = isObj(f.skill) ? f.skill : {};
  return {
    skill: { all: parseSkill(k.all), contested: parseSkill(k.contested) },
    made: n0(f.made), resolved: n0(f.resolved), min_resolved: n0(f.min_resolved), shown: f.shown === true, brier: num(f.brier), brier_market: num(f.brier_market), skill_vs_market: num(f.skill_vs_market),
    recent: list(f.recent).map((x) => ({ market_id: str(x.market_id), question: str(x.question), at: str(x.at), p: n0(x.p), market: num(x.market), confidence: str(x.confidence), outcome: str(x.outcome), reason: str(x.reason) })),
  };
}

function parseResting(raw: unknown): RestingSection {
  const r = isObj(raw) ? raw : {};
  return {
    open: list(r.open).map((o) => ({
      id: str(o.id), market_id: str(o.market_id), question: str(o.question), url: str(o.url), action: o.action === "buy_no" || o.action === "sell" ? o.action : "buy_yes", side: str(o.side),
      limit: n0(o.limit), usd: n0(o.usd), fraction: n0(o.fraction), now: num(o.now), p_yes: n0(o.p_yes), reason: str(o.reason), placed_at: str(o.placed_at), expires_at: str(o.expires_at),
    })),
    fills: list(r.fills).map((f) => ({
      id: str(f.id), order_id: str(f.order_id), market_id: str(f.market_id), question: str(f.question), action: str(f.action), side: str(f.side), price: n0(f.price), stake: n0(f.stake), at: str(f.at),
    })),
  };
}

function parseStrategies(raw: unknown, fallbackRule: Portfolio): Strategy[] {
  return list(raw).flatMap((r) => {
    const d = parseDay(r, fallbackRule);
    const ex = isObj(r.exposure) ? r.exposure : null;
    const fl = isObj(r.floor) ? r.floor : null;
    return d ? [{
      ...d, id: str(r.id), name: str(r.name), method: str(r.method), method_name: str(r.method_name), bot: str(r.bot) || str(r.method), bot_name: str(r.bot_name) || str(r.method_name), desk: str(r.desk), desk_name: str(r.desk_name),
      desk_about: str(r.desk_about), min_fills_day: n0(r.min_fills_day), style: str(r.style), must_trade: r.must_trade === true, min_orders: n0(r.min_orders), next_run: str(r.next_run),
      forecasts: parseForecasts(r.forecasts), exposure: ex ? { pct: n0(ex.pct), floor_pct: n0(ex.floor_pct) } : null, floor: fl ? { opened: n0(fl.opened), groups: list(fl.groups).map(dayGroup) } : null,
      resting: parseResting(r.resting),
    }] : [];
  });
}

const coverage = (c: Obj): Coverage => ({
  n: n0(c.n), rated: n0(c.rated), sufficient: n0(c.sufficient), thin: n0(c.thin), gap: n0(c.gap), share_sufficient: num(c.share_sufficient), share_gap_requested: num(c.share_gap_requested),
});
const group = (g: Obj): EvidenceGroup => ({ label: str(g.label), n: n0(g.n), shown: g.shown === true, brier_ours: num(g.brier_ours), brier_market: num(g.brier_market), skill: num(g.skill) });

// A document from before the evidence section existed has none: the page then shows nothing for it rather than failing.
const VERDICTS: LoopVerdict[] = ["answered", "unused", "asked again", "too early", "unlinked"];

// Absent in documents from before the loop check existed: the page then shows no such section.
function parseLoop(raw: unknown): GapLoop | null {
  if (!isObj(raw)) return null;
  return {
    fills: n0(raw.fills), failed: n0(raw.failed), answered: n0(raw.answered), unused: n0(raw.unused), asked_again: n0(raw.asked_again), too_early: n0(raw.too_early),
    unlinked: n0(raw.unlinked), usd: n0(raw.usd), min_for_verdict: n0(raw.min_for_verdict), settle_days: n0(raw.settle_days), reask_min: n0(raw.reask_min), basis: str(raw.basis),
    rows: list(raw.rows).map((r) => {
      const e = isObj(r.edge) ? r.edge : {};
      return {
        topic: str(r.topic), at: str(r.at), asks: n0(r.asks), refill: r.refill === true, linked: r.linked === true, reasks_before: n0(r.reasks_before), reasks_after: n0(r.reasks_after),
        verdict: VERDICTS.find((v) => v === r.verdict) ?? "too early", returned_after: num(r.returned_after), cited_after: num(r.cited_after), decisions_after: n0(r.decisions_after),
        edge: { shown: e.shown === true, min: n0(e.min), n_before: n0(e.n_before), n_after: n0(e.n_after), before: num(e.before), after: num(e.after) },
      };
    }),
  };
}

function parseEvidence(raw: unknown): Evidence | null {
  if (!isObj(raw)) return null;
  const cov = isObj(raw.coverage) ? raw.coverage : {};
  const cit = isObj(raw.citations) ? raw.citations : {};
  const t = isObj(raw.tools) ? raw.tools : {};
  const acc = isObj(raw.accuracy) ? raw.accuracy : {};
  const caps = isObj(raw.caps) ? raw.caps : {};
  const gs = isObj(raw.gap_spend) ? raw.gap_spend : {};
  const byTool: Record<string, number> = {};
  if (isObj(t.by_tool)) for (const [k, v] of Object.entries(t.by_tool)) byTool[k] = n0(v);
  return {
    coverage: { ...coverage(cov), forecasts: coverage(isObj(cov.forecasts) ? cov.forecasts : {}), trades: coverage(isObj(cov.trades) ? cov.trades : {}) },
    citations: { n: n0(cit.n), mean: num(cit.mean), median: num(cit.median), none_share: num(cit.none_share) },
    tools: {
      traces: n0(t.traces), corpus: n0(t.corpus), fallback: n0(t.fallback), queries: n0(t.queries), by_tool: byTool, mean_results: num(t.mean_results), empty_share: num(t.empty_share),
      error_share: num(t.error_share), median_latency_ms: num(t.median_latency_ms), mean_usd: num(t.mean_usd), mean_tokens: num(t.mean_tokens), mean_rounds: num(t.mean_rounds),
    },
    top_gaps: list(raw.top_gaps).map((g) => ({
      topic: str(g.topic), asks: n0(g.asks), why: str(g.why), last: str(g.last), status: g.status === "filled" || g.status === "tried" ? g.status : "open", filled: str(g.filled),
      markets: list(g.markets).map((m) => ({ market_id: str(m.market_id), question: str(m.question) })),
    })),
    accuracy: {
      rich_min_cited: n0(acc.rich_min_cited), min_for_verdict: n0(acc.min_for_verdict), forecasts: list(acc.forecasts).map(group),
      trades: list(acc.trades).map((g) => ({ label: str(g.label), n: n0(g.n), shown: g.shown === true, pnl: num(g.pnl), hit_rate: num(g.hit_rate) })), note: str(acc.note),
    },
    caps: { rounds: n0(caps.rounds), queries_per_round: n0(caps.queries_per_round), rows_per_query: n0(caps.rows_per_query), gap_fill_usd_per_day: n0(caps.gap_fill_usd_per_day), corpus_only: caps.corpus_only === true },
    gap_spend: { asks: n0(gs.asks), fills: n0(gs.fills), usd: n0(gs.usd) },
    loop: parseLoop(raw.loop),
  };
}

function parseHorizons(raw: unknown): Horizons | null {
  if (!isObj(raw)) return null;
  const books: Record<string, BookHorizon> = {};
  if (isObj(raw.books)) {
    for (const [k, v] of Object.entries(raw.books)) {
      const b = isObj(v) ? v : {};
      books[k] = { positions: n0(b.positions), resolved: n0(b.resolved), median_days_to_resolution: num(b.median_days_to_resolution), mean_days_to_resolution: num(b.mean_days_to_resolution) };
    }
  }
  return { by_horizon: list(raw.by_horizon).map(group), min_for_verdict: n0(raw.min_for_verdict), books };
}

export function parseTrackRecord(raw: unknown): TrackRecord | null {
  if (!isObj(raw) || (raw.schema !== "ohmega.track-record/1" && raw.schema !== "ohmega.track-record/2")) return null;
  const s = isObj(raw.scores) ? raw.scores : {};
  const p = isObj(raw.portfolio) ? raw.portfolio : {};
  const m = isObj(raw.markets) ? raw.markets : {};
  const other = isObj(raw.other) ? raw.other : {};
  const w = isObj(other.watches) ? other.watches : null;
  const j = isObj(other.judgments) ? other.judgments : null;
  const rules = isObj(raw.rules) ? raw.rules : {};
  const rulePortfolio = portfolio(p);
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
    portfolio: rulePortfolio,
    trader: parseTrader(raw.trader, rulePortfolio),
    fast: parseFast(raw.fast, rulePortfolio),
    day: parseDay(raw.day, rulePortfolio),
    strategies: parseStrategies(raw.strategies, rulePortfolio),
    evidence: parseEvidence(raw.evidence),
    horizons: parseHorizons(raw.horizons),
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
