import type { Metadata } from "next";
import Link from "next/link";

import JudgmentsSwitch from "@/components/JudgmentsSwitch";
import PageTag from "@/components/PageTag";

import { BrierSeries, CalibrationChart } from "@/components/track/TrackCharts";
import { AccuracyByEvidence, BookComparison, EvidenceStats, GapsList, HorizonTable } from "@/components/track/EvidencePanel";
import { DayGroups, DayRuns, DayStats, Wishes } from "@/components/track/DayBook";
import { EquityCurve, TraderPositions, TradeLog } from "@/components/track/TraderBook";
import { Disagreements, OpenPositions, Resolved } from "@/components/track/TrackTables";
import { hitRateView } from "@/lib/stats/render";
import { trackRecord } from "@/lib/track-record";

import "@/app/daily/daily.css";
import "@/app/situations/situations.css";
import "@/components/track/track.css";

export const metadata: Metadata = {
  title: "Paper trader and track record",
  description: "A paper-money trader that manages a Polymarket portfolio every day, its equity curve and every trade it makes, plus Ohmega's own probability forecasts scored against market prices. Paper trading only.",
  alternates: { canonical: "/intel/track-record", types: { "application/json": "/api/v1/track-record" } },
};

// The reality feedback loop (backend `markets/`): for each Polymarket market on a topic we cover, the desk forecasts BLIND to the price, the forecast is stored
// immutably, and when the market resolves both we and the market are scored against what happened. Internal-first and unflattering by design: the losses and
// the markets that beat us are listed as prominently as the wins. Paper trading only; nothing here is financial advice.
export const revalidate = 3600; // lib/store.ts TTL.static: slow products (markets every 4 h, benchmarks every 12 h)

const f3 = (v: number | null) => (v === null ? "n/a" : v.toFixed(3));
const usd = (v: number) => `${v < 0 ? "-" : v > 0 ? "+" : ""}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

export default async function TrackRecordPage() {
  const t = await trackRecord();
  const s = t?.scores;
  const early = !t || !s || s.compared < t.rules.min_for_verdict;
  const skill = s?.brier_skill ?? null;
  const traderHit = t ? hitRateView(t.trader.summary.hit_rate, t.trader.summary.wins + t.trader.summary.losses, t.rules.min_for_verdict) : { text: "–", note: "" };
  const paperHit = t ? hitRateView(t.portfolio.hit_rate, t.portfolio.wins + t.portfolio.losses, t.rules.min_for_verdict) : { text: "–", note: "" };
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="judgment" detail="Forecasts · scored" />
      </p>
      <h1 className="th-claim">Paper trader and track record</h1>
      <JudgmentsSwitch current="scored" />
      <p className="tr-paper">
        <b>Paper trading only</b>
        A trading agent manages a pretend portfolio on a prediction market&apos;s questions, and our own probability forecasts are scored against the market&apos;s prices. No money is
        staked, no order is ever placed, and nothing here is financial advice. It exists so our judgment is scored by the world, not by ourselves.
      </p>
      {!t || !s ? (
        <p className="th-asof">No track record has been published yet. The mirror and the first forecasts have to run, and markets have to resolve, before there is anything to score.</p>
      ) : (
        <>
          <h2 className="tr-h2">The trader</h2>
          <p className="tr-note">
            Every day the trader is shown a batch of markets, our own forecast for each, the market&apos;s price and what we know, and decides whether to buy, sell or stand aside with its{" "}
            ${t.trader.limits.bankroll.toLocaleString("en-US")} of paper money. Fills pay {Math.round(t.trader.limits.slippage * 100)} point of slippage; no more than{" "}
            {Math.round(t.trader.limits.max_position_frac * 100)}% of the starting money goes into one market or {Math.round(t.trader.limits.max_exposure_frac * 100)}% into all of them.
            {t.trader.since && ` Trading since ${t.trader.since}.`}
          </p>
          <ul className="tr-stats">
            <li>
              <span className={`tr-stat-n ${t.trader.summary.pnl > 0 ? "tr-good" : t.trader.summary.pnl < 0 ? "tr-bad" : ""}`}>{usd(t.trader.summary.pnl)}</span>
              <span className="tr-stat-l">trader P&amp;L, worth ${Math.round(t.trader.summary.equity).toLocaleString("en-US")}</span>
            </li>
            <li>
              <span className={`tr-stat-n ${t.trader.rule.total_pnl > 0 ? "tr-good" : t.trader.rule.total_pnl < 0 ? "tr-bad" : ""}`}>{usd(t.trader.rule.total_pnl)}</span>
              <span className="tr-stat-l">fixed-rule baseline P&amp;L</span>
            </li>
            <li><span className="tr-stat-n">{t.trader.summary.open}</span><span className="tr-stat-l">positions held</span></li>
            <li><span className="tr-stat-n">{t.trader.summary.buys + t.trader.summary.sells}</span><span className="tr-stat-l">trades ({t.trader.summary.buys} buys, {t.trader.summary.sells} sells)</span></li>
            <li>
              <span className="tr-stat-n">{traderHit.text}</span>
              <span className="tr-stat-l">closed positions in profit ({t.trader.summary.wins}W {t.trader.summary.losses}L){traderHit.note && `; ${traderHit.note}`}</span>
            </li>
            <li><span className="tr-stat-n">${Math.round(t.trader.summary.cash).toLocaleString("en-US")}</span><span className="tr-stat-l">cash</span></li>
          </ul>
          <EquityCurve curve={t.trader.curve} bankroll={t.trader.limits.bankroll} />
          {t.trader.today.decided > 0 && (
            <p className="tr-today">
              Latest pass: looked at {t.trader.today.decided} markets, bought {t.trader.today.bought}, sold {t.trader.today.sold}, stood aside on {t.trader.today.held}.
            </p>
          )}

          <h2 className="tr-h2">What it holds now</h2>
          <TraderPositions rows={t.trader.open_positions} />

          {t.fast && (
            <>
              <h2 className="tr-h2">The fast book</h2>
              <p className="tr-note">
                The same trader on a short clock: only markets that settle within {t.fast.horizon_days} days, decided every {t.fast.every_hours} hours with its own $
                {t.fast.limits.bankroll.toLocaleString("en-US")} of paper money, so its wins and losses arrive in days instead of months. Set beside the daily trader it shows how well the same
                judgement predicts at different time scales.
                {t.fast.since ? ` Trading since ${t.fast.since}.` : " It has not traded yet."}
              </p>
              <BookComparison daily={t.trader} fast={t.fast} h={t.horizons} />
              <EquityCurve curve={t.fast.curve} bankroll={t.fast.limits.bankroll} name="Fast book" id="tr-fast" showRule={false} />
              <TraderPositions rows={t.fast.open_positions} empty="The fast book holds nothing right now." />
              {t.horizons && (
                <>
                  <h3 className="tr-h3">Forecast accuracy by time to resolution</h3>
                  <HorizonTable h={t.horizons} />
                </>
              )}
            </>
          )}

          {t.day && (
            <>
              <h2 className="tr-h2">The day book</h2>
              <p className="tr-note">
                A third paper book with its own ${t.day.limits.bankroll.toLocaleString("en-US")}. It is handed no list of markets: {t.day.run_hours.length} times a day
                ({t.day.run_hours.map((h) => `${String(h).padStart(2, "0")}:${String(t.day?.run_minute ?? 0).padStart(2, "0")}`).join(", ")} UTC) it searches Polymarket for markets that settle
                within {t.day.horizon_hours} hours, reads our corpus, and buys or sells whatever it judges worth it, or holds cash. It can sell at any time, so a win can be a profit taken early.
                {t.day.since ? ` Trading since ${t.day.since}.` : " It has not traded yet."}
              </p>
              <DayStats d={t.day} />
              <EquityCurve curve={t.day.curve} bankroll={t.day.limits.bankroll} name="Day book" id="tr-day" showRule={false} />
              <h3 className="tr-h3">What it holds now, and when each bet resolves</h3>
              <TraderPositions rows={t.day.open_positions} empty="The day book holds nothing right now." />
              <h3 className="tr-h3">Results by horizon</h3>
              <DayGroups d={t.day} />
              <h3 className="tr-h3">Every trade, with its reason</h3>
              <TradeLog rows={t.day.log} />
              <h3 className="tr-h3">Recent runs: what it browsed and why</h3>
              <DayRuns rows={t.day.runs} />
              <h3 className="tr-h3">What it wished we knew</h3>
              <p className="tr-note">At the end of each run it says what information it wanted that our corpus does not hold. This is our to-do list for which data sources to add.</p>
              <Wishes rows={t.day.wishes} />
            </>
          )}

          <h2 className="tr-h2">Every trade, newest first</h2>
          <p className="tr-note">Green: the position paid off or was closed at a profit. Red: it lost. Reasons are the trader&apos;s own, written when it acted.</p>
          <TradeLog rows={t.trader.log} />

          {t.evidence && (
            <>
              <h2 className="tr-h2">Evidence</h2>
              <p className="tr-note">
                The bots read only our own corpus: a planning step picks up to {t.evidence.caps.queries_per_round} queries per market over {t.evidence.caps.rounds} rounds, they run against the corpus
                index, and the decision reads the results. There is no web search in the decision. Each decision says whether that evidence was sufficient, thin or a gap, and which items it
                used, so this measures how much of the outcome the corpus explains.
              </p>
              <EvidenceStats e={t.evidence} />
              <AccuracyByEvidence e={t.evidence} />

              <h2 className="tr-h2">What it looked for</h2>
              <p className="tr-note">
                When the corpus lacked something a decision needed, the bot asked for it. A daily job (at most ${t.evidence.caps.gap_fill_usd_per_day.toFixed(2)} a day) researches the most-asked
                topics into the corpus; the bots never see that research directly, only what lands in the corpus afterwards.
              </p>
              <GapsList rows={t.evidence.top_gaps} />
            </>
          )}

          <h2 className="tr-h2">How good are our forecasts</h2>
          <p className={`tr-verdict${early ? " is-early" : ""}`}>{s.verdict}</p>
          <ul className="tr-stats">
            <li><span className="tr-stat-n">{s.compared}</span><span className="tr-stat-l">resolved, compared</span></li>
            <li><span className="tr-stat-n">{f3(s.brier_ours)}</span><span className="tr-stat-l">our Brier (lower is better)</span></li>
            <li><span className="tr-stat-n">{f3(s.brier_market)}</span><span className="tr-stat-l">market Brier, same markets</span></li>
            <li>
              <span className={`tr-stat-n ${skill === null ? "" : skill > 0 ? "tr-good" : "tr-bad"}`}>{skill === null ? "n/a" : `${skill > 0 ? "+" : ""}${(skill * 100).toFixed(1)}%`}</span>
              <span className="tr-stat-l">skill vs market</span>
            </li>
            <li><span className="tr-stat-n">{f3(s.log_loss_ours)}</span><span className="tr-stat-l">our log loss (market {f3(s.log_loss_market)})</span></li>
            <li><span className="tr-stat-n">{t.market_beat_us}</span><span className="tr-stat-l">markets where the market was closer</span></li>
            <li>
              <span className={`tr-stat-n ${t.portfolio.total_pnl > 0 ? "tr-good" : t.portfolio.total_pnl < 0 ? "tr-bad" : ""}`}>{usd(t.portfolio.total_pnl)}</span>
              <span className="tr-stat-l">paper P&amp;L on ${t.portfolio.bankroll.toLocaleString("en-US")}</span>
            </li>
            <li>
              <span className="tr-stat-n">{paperHit.text}</span>
              <span className="tr-stat-l">paper hit rate ({t.portfolio.wins}W {t.portfolio.losses}L){paperHit.note && `; ${paperHit.note}`}</span>
            </li>
            <li><span className="tr-stat-n">{t.markets.open}</span><span className="tr-stat-l">markets open, {t.forecasts} forecasts</span></li>
          </ul>

          <h2 className="tr-h2">Calibration and error over time</h2>
          <div className="tr-figs">
            <CalibrationChart ours={s.calibration_ours} market={s.calibration_market} />
            <BrierSeries series={s.brier_diff_series} />
          </div>

          <h2 className="tr-h2">Fixed-rule baseline: open positions</h2>
          <p className="tr-note">
            The baseline has no judgement: it takes a position whenever our forecast differs from the market&apos;s price by {Math.round(t.rules.edge_min * 100)} points or more, sized at a {Math.round(t.rules.kelly_fraction * 100)}% fraction of
            Kelly and capped at {Math.round(t.rules.max_position_frac * 100)}% of the fixed ${t.rules.bankroll.toLocaleString("en-US")} bankroll. Never sold early; marked daily, settled when the market resolves.
            {t.portfolio.open > 0 && ` ${t.portfolio.open} open, $${t.portfolio.staked_open.toLocaleString("en-US", { maximumFractionDigits: 0 })} staked, unrealised ${usd(t.portfolio.unrealised_pnl)}.`}
          </p>
          <OpenPositions rows={t.open_positions} />

          <h2 className="tr-h2">Where we disagree with the market now</h2>
          <p className="tr-note">Our newest forecast against the current price. A gap means we disagree, not that we are right.</p>
          <Disagreements rows={t.disagreements} />

          {t.worst_misses.length > 0 && (
            <>
              <h2 className="tr-h2">Our worst misses</h2>
              <p className="tr-note">Largest errors of ours among resolved markets, whoever was closer. These are shown first on purpose.</p>
              <Resolved rows={t.worst_misses} label="Worst misses" />
            </>
          )}

          <h2 className="tr-h2">Resolved markets</h2>
          <p className="tr-note">Newest first. Rows shaded red are markets where the market was closer to the outcome than we were. Each market counts once, by our first forecast of it.</p>
          <Resolved rows={t.resolved} label="Resolved markets" />

          {(t.other.judgments || t.other.watches) && (
            <>
              <h2 className="tr-h2">Our older calls</h2>
              {t.other.judgments && (
                <p className="tr-note">
                  Desk judgments in briefs: {t.other.judgments.resolved} resolved, {t.other.judgments.open} open
                  {t.other.judgments.brier !== null && `, Brier ${t.other.judgments.brier.toFixed(3)} (0.25 is a coin flip)`}. See <Link href="/intel/forecasts" className="xt">the open forecasts</Link>.
                </p>
              )}
              {t.other.watches && (
                <p className="tr-note">
                  Pulse watches: {t.other.watches.triggered} triggered, {t.other.watches.expired} expired, {t.other.watches.open} open
                  {t.other.watches.trigger_rate !== null && `; ${Math.round(t.other.watches.trigger_rate * 100)}% of settled watches triggered`}. {t.other.watches.note}
                </p>
              )}
            </>
          )}

          <p className="th-asof">
            How it is scored. For every Polymarket market on a topic we cover, a model reads the question, the market&apos;s own resolution rules and what the desk knows, and states a
            probability. It is never shown the market&apos;s price (an anchored forecast would only measure how well we copy), and the forecast is stored with its timestamp and never edited.
            When the market resolves, the Brier score (mean squared error; 0 is perfect, 0.25 is a constant 50%) and log loss are computed for our probability and for the market&apos;s
            price at the same moment on the same markets. Void (50-50) resolutions are not scored. Until {t.rules.min_for_verdict} markets have been compared the numbers are noise and say so.
            Prices: <a href="https://polymarket.com" rel="noopener noreferrer" className="xt">Polymarket</a> public data, read-only. Machine access: <Link href="/api/v1/track-record" className="xt">/api/v1/track-record</Link>.
            As of {t.as_of.slice(0, 16).replace("T", " ")} UTC.
          </p>
        </>
      )}
    </div>
  );
}
