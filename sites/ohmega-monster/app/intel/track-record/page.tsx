import type { Metadata } from "next";
import Link from "next/link";

import type { ReactNode } from "react";

import JudgmentsSwitch from "@/components/JudgmentsSwitch";
import PageTag from "@/components/PageTag";

import { BrierSeries, CalibrationChart, ChartCard } from "@/components/track/TrackCharts";
import { AccuracyByEvidence, EvidenceStats, GapsList, HorizonTable, LoopSummary, LoopTable, MissingSummary, MissingTable } from "@/components/track/EvidencePanel";
import { DayGroups, Wishes } from "@/components/track/DayBook";
import { Books, ValueChart } from "@/components/track/Portfolio";
import { Disagreements, Resolved } from "@/components/track/TrackTables";
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

// A collapsed section: the headline is always visible, the detail is one click away.
function Fold({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="tr-fold">
      <summary>{title}</summary>
      {children}
    </details>
  );
}

export default async function TrackRecordPage() {
  const t = await trackRecord();
  const s = t?.scores;
  const need = t?.rules.min_for_verdict ?? 30;
  const early = !t || !s || s.compared < need;
  const skill = s?.brier_skill ?? null;
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="judgment" detail="Forecasts · scored" />
      </p>
      <h1 className="th-claim">Paper trader and track record</h1>
      <JudgmentsSwitch current="scored" />
      {!t || !s ? (
        <p className="th-asof">No track record has been published yet. The mirror and the first forecasts have to run, and markets have to resolve, before there is anything to score.</p>
      ) : (
        <>
          <ValueChart t={t} />
          <Books t={t} />
          <p className="tr-paper">
            <b>Paper trading only</b>
            No money is staked, no order is ever placed, nothing here is financial advice. Fills pay {Math.round(t.trader.limits.slippage * 100)} point of slippage; at most{" "}
            {Math.round(t.trader.limits.max_position_frac * 100)}% of the starting money goes into one market and {Math.round(t.trader.limits.max_exposure_frac * 100)}% into all of them. Prices are the
            latest snapshot we hold (the time is shown on each position). Click a bot to see what it holds and every trade.
          </p>

          <Fold title="How good are the forecasts?">
            <p className={`tr-verdict${early ? " is-early" : ""}`}>{s.verdict}</p>
            <ul className="tr-stats">
              <li><span className="tr-stat-n">{s.compared}</span><span className="tr-stat-l">markets resolved and compared</span></li>
              <li><span className="tr-stat-n">{early ? "n/a" : f3(s.brier_ours)}</span><span className="tr-stat-l">our error score (lower is better)</span></li>
              <li><span className="tr-stat-n">{early ? "n/a" : f3(s.brier_market)}</span><span className="tr-stat-l">the market&apos;s, same markets</span></li>
              <li>
                <span className={`tr-stat-n ${early || skill === null ? "" : skill > 0 ? "tr-good" : "tr-bad"}`}>{early || skill === null ? "n/a" : `${skill > 0 ? "+" : ""}${(skill * 100).toFixed(1)}%`}</span>
                <span className="tr-stat-l">better than the market&apos;s prices</span>
              </li>
              <li><span className="tr-stat-n">{t.market_beat_us}</span><span className="tr-stat-l">markets where the market was closer</span></li>
              <li><span className="tr-stat-n">{t.markets.open}</span><span className="tr-stat-l">markets open, {t.forecasts} forecasts</span></li>
            </ul>
            <div className="tr-figs">
              <ChartCard title="When we say 70%, does it happen 70% of the time?" guide="Dots on the diagonal mean honest probabilities; dots below it mean we were overconfident. Filled: us. Hollow: the market&apos;s prices." have={s.compared} need={need}>
                <CalibrationChart ours={s.calibration_ours} market={s.calibration_market} />
              </ChartCard>
              <ChartCard title="Are our forecasts beating the market&apos;s prices?" guide="Below the line = our forecasts beat the market&apos;s prices; above it the market was the better forecaster." have={s.compared} need={need}>
                <BrierSeries series={s.brier_diff_series} />
              </ChartCard>
            </div>
            <h3 className="tr-h3">Where we disagree with the market now</h3>
            <p className="tr-note">Our newest forecast against the current price. A gap means we disagree, not that we are right.</p>
            <Disagreements rows={t.disagreements} />
          </Fold>

          {t.evidence && (
            <Fold title="Did our corpus serve the bots?">
              <p className="tr-note">
                The bots read only our own corpus (no web search). Each decision rates its evidence sufficient, thin or a gap, and names the items it used, so this measures how much of the outcome the corpus explains.
              </p>
              <EvidenceStats e={t.evidence} />
              <AccuracyByEvidence e={t.evidence} />
            </Fold>
          )}

          <Fold title="What it looked for and wished we knew">
            {t.evidence && (
              <>
                <h3 className="tr-h3">Topics the bots asked us to research</h3>
                <p className="tr-note">Researched into the corpus by a daily job (at most ${t.evidence.caps.gap_fill_usd_per_day.toFixed(2)} a day); the bots only see what lands in the corpus afterwards.</p>
                <GapsList rows={t.evidence.top_gaps} />
              </>
            )}
            {t.day && (
              <>
                <h3 className="tr-h3">Data the day bot wished we had, across all runs</h3>
                <p className="tr-note">Our to-do list for which data sources to add: what it wanted, why, and where it would come from.</p>
                <Wishes rows={t.day.wishes} />
              </>
            )}
          </Fold>

          {t.evidence?.routing && t.evidence.routing.asks > 0 && (
            <Fold title="What the bots asked for that we don't hold">
              <MissingSummary r={t.evidence.routing} />
              <MissingTable r={t.evidence.routing} />
            </Fold>
          )}

          {t.evidence?.loop && t.evidence.loop.fills + t.evidence.loop.failed > 0 && (
            <Fold title="Did the research help?">
              <LoopSummary l={t.evidence.loop} />
              <LoopTable l={t.evidence.loop} />
            </Fold>
          )}

          {t.day && (
            <Fold title="Day book: results by horizon">
              <p className="tr-note">Does it do better on bets that resolve in hours or in days? Win rate and P&amp;L stay hidden until a group has enough closed trades.</p>
              <DayGroups d={t.day} />
              {t.horizons && (
                <>
                  <h3 className="tr-h3">Forecast accuracy by time to resolution</h3>
                  <HorizonTable h={t.horizons} />
                </>
              )}
            </Fold>
          )}

          {t.worst_misses.length > 0 && (
            <Fold title="Our worst misses">
              <p className="tr-note">Largest errors of ours among resolved markets, whoever was closer. Shown on purpose.</p>
              <Resolved rows={t.worst_misses} label="Worst misses" />
            </Fold>
          )}

          <Fold title={`Resolved markets (${t.resolved.length})`}>
            <p className="tr-note">Newest first. Rows shaded red are markets where the market was closer to the outcome than we were. Each market counts once, by our first forecast of it.</p>
            <Resolved rows={t.resolved} label="Resolved markets" />
          </Fold>

          <Fold title="How it is scored, and our older calls">
            {(t.other.judgments || t.other.watches) && (
              <>
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
              For every Polymarket market on a topic we cover, a model reads the question, the market&apos;s own resolution rules and what the desk knows, and states a probability. It is never
              shown the market&apos;s price, and the forecast is stored with its timestamp and never edited. When the market resolves, the Brier score (mean squared error; 0 is perfect, 0.25 is a
              constant 50%) and log loss are computed for our probability and for the market&apos;s price at the same moment on the same markets. Void resolutions are not scored. Until {need} markets
              have been compared the numbers are noise and say so. Prices: <a href="https://polymarket.com" rel="noopener noreferrer" className="xt">Polymarket</a> public data, read-only. Machine
              access: <Link href="/api/v1/track-record" className="xt">/api/v1/track-record</Link>. As of {t.as_of.slice(0, 16).replace("T", " ")} UTC.
            </p>
          </Fold>
        </>
      )}
    </div>
  );
}
