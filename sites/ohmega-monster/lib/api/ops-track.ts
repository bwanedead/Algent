import { trackRecord } from "@/lib/track-record";

import { abs, notFound, type ApiResult } from "./util";

// Op over the track record (backend `markets/`): Ohmega's blind probability forecasts scored against Polymarket prices at the same instants, plus a paper
// portfolio. PAPER ONLY, not financial advice.

export async function trackRecordOp(): Promise<ApiResult> {
  const t = await trackRecord();
  if (!t) throw notFound("track record");
  return {
    data: {
      markets: t.markets,
      forecasts: t.forecasts,
      scores: t.scores,
      portfolio: t.portfolio,
      trader: t.trader,
      fast: t.fast,
      evidence: t.evidence,
      horizons: t.horizons,
      open_positions: t.open_positions,
      disagreements: t.disagreements,
      worst_misses: t.worst_misses,
      market_beat_us: t.market_beat_us,
      resolved: t.resolved,
      other: t.other,
      rules: t.rules,
    },
    as_of: t.as_of || null,
    cite_as: abs("/intel/track-record"),
    source: "ohmega.track-record/2",
    verification: "ohmega_derived",
    note:
      `${t.disclaimer} trader is an agent-managed paper portfolio started from the same bankroll as the rule-based baseline (portfolio): trader.curve gives each day's equity for both and the flat bankroll, trader.log every buy, sell and settlement with its reason. Probabilities are 0..1. Forecasts are made blind to the market price and stored immutably; the Brier score is the mean squared error ` +
      "(lower is better, 0.25 is a constant 50%); brier_skill is 1 - ours/market on the same markets (positive means we beat the market). " +
      `Until ${t.rules.min_for_verdict} markets are compared the scores are noise: read scores.verdict. ` +
      "fast is the same trader on markets that settle within days, decided every few hours (its own bankroll, same shape as trader). evidence says how the corpus served the bots: " +
      "coverage (sufficient, thin or gap, as the bot rated its own evidence), citations, tools, top_gaps (what they asked the corpus for) and accuracy split by evidence richness " +
      "(withheld until a group has enough resolved items). horizons gives forecast accuracy by time to resolution.",
  };
}
