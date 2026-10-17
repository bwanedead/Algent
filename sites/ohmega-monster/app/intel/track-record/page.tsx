import type { Metadata } from "next";
import Link from "next/link";

import { BrierSeries, CalibrationChart } from "@/components/track/TrackCharts";
import { Disagreements, OpenPositions, Resolved } from "@/components/track/TrackTables";
import { trackRecord } from "@/lib/track-record";

import "@/app/geopolitics/geopolitics.css";
import "../theaters/theaters.css";
import "@/components/track/track.css";

export const metadata: Metadata = {
  title: "Track record",
  description: "Ohmega's own probability forecasts scored against Polymarket prices at the same moment: Brier score, calibration, misses and a paper portfolio. Paper trading only.",
  alternates: { canonical: "/intel/track-record", types: { "application/json": "/api/v1/track-record" } },
};

// The reality feedback loop (backend `markets/`): for each Polymarket market on a topic we cover, the desk forecasts BLIND to the price, the forecast is stored
// immutably, and when the market resolves both we and the market are scored against what happened. Internal-first and unflattering by design: the losses and
// the markets that beat us are listed as prominently as the wins. Paper trading only; nothing here is financial advice.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

const f3 = (v: number | null) => (v === null ? "n/a" : v.toFixed(3));
const usd = (v: number) => `${v < 0 ? "-" : v > 0 ? "+" : ""}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

export default async function TrackRecordPage() {
  const t = await trackRecord();
  const s = t?.scores;
  const early = !t || !s || s.compared < t.rules.min_for_verdict;
  const skill = s?.brier_skill ?? null;
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <span>Intelligence</span> <Link href="/intel/situation" className="xt">situation room →</Link>
      </p>
      <h1 className="th-claim">Track record</h1>
      <p className="tr-paper">
        <b>Paper trading only</b>
        These are Ohmega&apos;s own probability forecasts compared with a prediction market&apos;s prices. No money is staked, no order is ever placed, and nothing here is
        financial advice. It exists so our judgment is scored by the world, not by ourselves.
      </p>
      {!t || !s ? (
        <p className="th-asof">No track record has been published yet. The mirror and the first forecasts have to run, and markets have to resolve, before there is anything to score.</p>
      ) : (
        <>
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
              <span className="tr-stat-n">{t.portfolio.hit_rate === null ? "n/a" : `${Math.round(t.portfolio.hit_rate * 100)}%`}</span>
              <span className="tr-stat-l">paper hit rate ({t.portfolio.wins}W {t.portfolio.losses}L)</span>
            </li>
            <li><span className="tr-stat-n">{t.markets.open}</span><span className="tr-stat-l">markets open, {t.forecasts} forecasts</span></li>
          </ul>

          <h2 className="tr-h2">Calibration and error over time</h2>
          <div className="tr-figs">
            <CalibrationChart ours={s.calibration_ours} market={s.calibration_market} />
            <BrierSeries series={s.brier_diff_series} />
          </div>

          <h2 className="tr-h2">Open paper positions</h2>
          <p className="tr-note">
            A position is taken when our forecast differs from the market&apos;s price by {Math.round(t.rules.edge_min * 100)} points or more, sized at a {Math.round(t.rules.kelly_fraction * 100)}% fraction of
            Kelly and capped at {Math.round(t.rules.max_position_frac * 100)}% of the fixed ${t.rules.bankroll.toLocaleString("en-US")} bankroll. Marked to market daily, settled when the market resolves.
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
                  {t.other.judgments.brier !== null && `, Brier ${t.other.judgments.brier.toFixed(3)} (0.25 is a coin flip)`}. See <Link href="/intel/situation" className="xt">the situation room</Link>.
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
