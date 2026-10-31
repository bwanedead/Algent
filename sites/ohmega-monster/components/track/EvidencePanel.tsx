import { ReliabilityChart } from "@/components/track/TrackCharts";
import type { BookHorizon, Evidence, EvidenceGroup, EvidenceMoney, FastBook, GapLoop, GapRouting, GapRow, Horizons, LabBlock, LoopRow, Trader } from "@/lib/track-record";

// The Evidence section of the track record (backend `markets/research_report.py`): how well OUR corpus served the bots, what they went looking for and the
// book that trades the short horizon beside the daily one. Server-rendered. A ratio with nothing under it reads "n/a"; a group below the verdict threshold
// shows its count and nothing else, the same rule as the forecast verdict.

const pct = (v: number | null) => (v === null ? "n/a" : `${Math.round(v * 100)}%`);
const f3 = (v: number | null) => (v === null ? "n/a" : v.toFixed(3));
const usd = (v: number) => `${v < 0 ? "-" : v > 0 ? "+" : ""}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const days = (v: number | null) => (v === null ? "n/a" : `${v.toFixed(1)} d`);

export function EvidenceStats({ e }: { e: Evidence }) {
  const c = e.coverage;
  return (
    <ul className="tr-stats">
      <li>
        <span className="tr-stat-n">{pct(c.share_sufficient)}</span>
        <span className="tr-stat-l">of {c.rated} rated decisions found the corpus sufficient</span>
      </li>
      <li>
        <span className="tr-stat-n">{c.thin + c.gap}</span>
        <span className="tr-stat-l">decisions asked for something the corpus lacked ({c.thin} thin, {c.gap} gap)</span>
      </li>
      <li>
        <span className="tr-stat-n">{e.citations.mean === null ? "n/a" : e.citations.mean.toFixed(1)}</span>
        <span className="tr-stat-l">corpus items cited per decision (none cited: {pct(e.citations.none_share)})</span>
      </li>
      <li>
        <span className="tr-stat-n">{e.tools.queries}</span>
        <span className="tr-stat-l">
          corpus queries, {e.tools.mean_results === null ? "n/a" : e.tools.mean_results.toFixed(1)} results each, {pct(e.tools.empty_share)} empty
        </span>
      </li>
      <li>
        <span className="tr-stat-n">{e.tools.median_latency_ms === null ? "n/a" : `${(e.tools.median_latency_ms / 1000).toFixed(1)}s`}</span>
        <span className="tr-stat-l">median research time per decision{e.tools.mean_usd !== null && `, $${e.tools.mean_usd.toFixed(3)} each`}</span>
      </li>
      <li>
        <span className="tr-stat-n">{e.gap_spend.asks}</span>
        <span className="tr-stat-l">gap requests, {e.gap_spend.fills} research runs (${e.gap_spend.usd.toFixed(2)} of a ${e.caps.gap_fill_usd_per_day.toFixed(2)} daily cap)</span>
      </li>
    </ul>
  );
}

function GroupRow({ g }: { g: EvidenceGroup }) {
  return (
    <tr>
      <td>{g.label}</td>
      <td className="n">{g.n}</td>
      <td className="n">{g.shown ? f3(g.brier_ours) : "too few"}</td>
      <td className="n">{g.shown ? f3(g.brier_market) : "too few"}</td>
      <td className={`n ${g.skill === null ? "" : g.skill > 0 ? "tr-good" : "tr-bad"}`}>{g.shown && g.skill !== null ? `${g.skill > 0 ? "+" : ""}${(g.skill * 100).toFixed(1)}%` : "n/a"}</td>
    </tr>
  );
}

function MoneyRow({ g }: { g: EvidenceMoney }) {
  return (
    <tr>
      <td>{g.label}</td>
      <td className="n">{g.n}</td>
      <td className={`n ${g.pnl === null ? "" : g.pnl > 0 ? "tr-good" : g.pnl < 0 ? "tr-bad" : ""}`}>{g.shown && g.pnl !== null ? usd(g.pnl) : "too few"}</td>
      <td className="n">{g.shown ? pct(g.hit_rate) : "too few"}</td>
    </tr>
  );
}

export function AccuracyByEvidence({ e }: { e: Evidence }) {
  const a = e.accuracy;
  return (
    <>
      <div className="tr-scroll">
        <table className="tr-table" aria-label="Forecast accuracy by evidence richness">
          <thead>
            <tr><th>Forecasts that</th><th className="n">Resolved</th><th className="n">Our Brier</th><th className="n">Market Brier</th><th className="n">Skill</th></tr>
          </thead>
          <tbody>{a.forecasts.map((g) => <GroupRow key={g.label} g={g} />)}</tbody>
        </table>
      </div>
      <div className="tr-scroll">
        <table className="tr-table" aria-label="Trade results by evidence richness">
          <thead>
            <tr><th>Closed positions</th><th className="n">Closed</th><th className="n">P&amp;L</th><th className="n">In profit</th></tr>
          </thead>
          <tbody>{a.trades.map((g) => <MoneyRow key={g.label} g={g} />)}</tbody>
        </table>
      </div>
      <p className="tr-note">{a.note}</p>
    </>
  );
}

// The recipe lab (backend `markets/lab_block.py`): in plain words, whether the best way of forecasting we have found beats the market and whether correcting its
// systematic lean would have helped. Scores are our Brier minus the market's at the same moment, so below zero beats the market. Nothing here changes any bot's trading.
const signed = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(3)}`;
const CHART_CAPTION = "Hollow: what it said. Filled: after correcting the lean using only forecasts that had already resolved. Dot area is how many forecasts; the dashed diagonal is honest.";

export function RecipeLab({ lab }: { lab: LabBlock }) {
  const { best, live } = lab;
  return (
    <>
      <p className="tr-note">
        We try different ways of forecasting on markets that have already resolved and score each against the market&apos;s own price at the same moment. A score below zero means the way of forecasting beat the market; above zero, the market was closer.
        Nothing here changes what the bots trade.
      </p>
      {best && (
        <p className="tr-note">
          Best so far{best.protocol ? `: ${best.protocol}` : ""}. Over {best.n} past questions it scored {signed(best.raw)} as it said them and {signed(best.calibrated)} once its probabilities were corrected
          ({best.n_fitted} of {best.n} could be corrected from earlier results; the rest had too little history).
        </p>
      )}
      {live && (
        <p className="tr-note">
          The live bots: if we had corrected their probabilities the same way, their score against the market would be {signed(live.calibrated)} instead of {signed(live.raw)} on {live.n} resolved forecasts.
        </p>
      )}
      <div className="tr-figs">
        {best && <ReliabilityChart raw={best.bins_raw} calibrated={best.bins_calibrated} title="Best recipe: when it says X%, how often does it happen?" caption={CHART_CAPTION} />}
        {live && <ReliabilityChart raw={live.bins_raw} calibrated={live.bins_calibrated} title="Live bots: when they say X%, how often does it happen?" caption={CHART_CAPTION} />}
      </div>
    </>
  );
}

export function HorizonTable({ h }: { h: Horizons }) {
  return (
    <div className="tr-scroll">
      <table className="tr-table" aria-label="Forecast accuracy by time to resolution">
        <thead>
          <tr><th>Market ended in</th><th className="n">Resolved</th><th className="n">Our Brier</th><th className="n">Market Brier</th><th className="n">Skill</th></tr>
        </thead>
        <tbody>{h.by_horizon.map((g) => <GroupRow key={g.label} g={g} />)}</tbody>
      </table>
    </div>
  );
}

export function GapsList({ rows }: { rows: GapRow[] }) {
  if (rows.length === 0) return <p className="tr-empty">The bots have not asked for anything the corpus lacked yet.</p>;
  return (
    <ul className="tr-gaps">
      {rows.map((g) => (
        <li key={g.topic}>
          <span className={`tr-tag ${g.status === "filled" ? "is-hit" : ""}`}>{g.status === "filled" ? `researched ${g.filled}` : g.status === "tried" ? "tried" : "open"}</span>{" "}
          <b>{g.topic}</b> <span className="tr-muted">asked {g.asks} time{g.asks === 1 ? "" : "s"}, last {g.last}</span>
          {g.why && <span className="tr-why">{g.why}</span>}
          {g.markets.length > 0 && <span className="tr-why">For: {g.markets.map((m) => m.question).filter(Boolean).slice(0, 2).join("; ")}</span>}
        </li>
      ))}
    </ul>
  );
}

// What the bots asked for that we don't hold: one sentence, a small table by kind of ask, then the feeds worth adding first. Plain words only; the counts are asks.
export function MissingSummary({ r }: { r: GapRouting }) {
  const parts = [
    r.held_missed > 0 && `${r.held_missed} are in a feed we already run but the bot did not find them`,
    r.not_held > 0 && `${r.not_held} are in a feed that does not hold them yet`,
    r.no_feed > 0 && `${r.no_feed} have no feed and need a paid research run`,
    r.unknowable > 0 && `${r.unknowable} cannot be known yet`,
    r.unchecked > 0 && `${r.unchecked} are not checked yet`,
  ].filter(Boolean);
  return <p className="tr-note">Of {r.asks} things the bots asked for{parts.length > 0 && `, ${parts.join(", ")}`}.</p>;
}

export function MissingTable({ r }: { r: GapRouting }) {
  if (r.rows.length === 0) return <p className="tr-empty">The bots have not asked for anything the corpus lacked yet.</p>;
  return (
    <>
      <div className="tr-scroll">
        <table className="tr-table" aria-label="What the bots asked for, and whether we hold it">
          <thead>
            <tr><th>They asked for</th><th className="n">Asks</th><th>Should come from</th><th className="n">We hold it, the bot did not find it</th><th className="n">We do not hold it</th></tr>
          </thead>
          <tbody>
            {r.rows.map((x) => {
              const feed = x.route.startsWith("feed:");
              return (
                <tr key={`${x.kind}-${x.route}`}>
                  <td>{x.label}</td>
                  <td className="n">{x.asks}</td>
                  <td>{x.route_label}</td>
                  <td className="n">{feed ? x.held_missed : "–"}</td>
                  <td className="n">{feed ? x.not_held : "–"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {r.wanted.length > 0 && (
        <>
          <h3 className="tr-h3">Feeds to add or fill first</h3>
          <ul className="tr-gaps">
            {r.wanted.map((w) => (
              <li key={w.kind}>
                <b>{w.label}</b> <span className="tr-muted">asked {w.asks} time{w.asks === 1 ? "" : "s"}, {w.product ? `the ${w.route_label} does not hold it` : "no feed covers it"}</span>
                {w.topics.length > 0 && <span className="tr-why">For example: {w.topics.join("; ")}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="tr-note">{r.basis}</p>
    </>
  );
}

// Did the research help? One plain sentence, then a row per research run the bots asked for, newest first. The edge is the bot's lead over the market price
// (market Brier minus ours, higher is better); until both sides of the run hold enough resolved forecasts it reads "too early".
const edge = (e: LoopRow["edge"]) => {
  if (!e.shown || e.before === null || e.after === null) return `too early (${e.n_before} and ${e.n_after} of ${e.min} resolved)`;
  return `${e.before.toFixed(3)} → ${e.after.toFixed(3)}`;
};
const VERDICT_CLASS: Record<string, string> = { answered: "is-hit", "asked again": "is-miss" };

export function LoopSummary({ l }: { l: GapLoop }) {
  const parts = [`${l.answered} answered`, `${l.unused} unused`, `${l.asked_again} asked again`, `${l.too_early} too early`, ...(l.unlinked > 0 ? [`${l.unlinked} not traceable`] : [])];
  return (
    <p className="tr-note">
      {l.fills} research run{l.fills === 1 ? "" : "s"} from bot requests: {parts.join(", ")}, ${l.usd.toFixed(2)} spent{l.failed > 0 && ` (${l.failed} more failed)`}.
    </p>
  );
}

export function LoopTable({ l }: { l: GapLoop }) {
  if (l.rows.length === 0) return <p className="tr-empty">No research run has been made for a bot request yet.</p>;
  return (
    <>
      <div className="tr-scroll">
        <table className="tr-table" aria-label="Research runs and what the bots did afterwards">
          <thead>
            <tr><th>Topic</th><th className="n">Asked by</th><th>Verdict</th><th className="n">Cited after</th><th className="n">Asked again</th><th className="n">Edge over market, before → after</th></tr>
          </thead>
          <tbody>
            {l.rows.map((r) => (
              <tr key={`${r.topic}-${r.at}`}>
                <td>{r.topic}{r.refill && " (second run)"} <span className="tr-muted">{r.at}</span></td>
                <td className="n">{r.asks}</td>
                <td><span className={`tr-tag ${VERDICT_CLASS[r.verdict] ?? ""}`}>{r.verdict}</span></td>
                <td className="n">{r.cited_after === null ? "n/a" : r.cited_after}</td>
                <td className="n">{r.reasks_after}</td>
                <td className="n">{edge(r.edge)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="tr-note">{l.basis}</p>
    </>
  );
}

const hit = (t: Trader["summary"]) => (t.wins + t.losses > 0 ? `${Math.round((t.wins / (t.wins + t.losses)) * 100)}% (${t.wins}W ${t.losses}L)` : "n/a");

// Daily trader and fast book side by side, with how long their positions took to resolve: the same agent at two time scales.
export function BookComparison({ daily, fast, h }: { daily: Trader; fast: FastBook; h: Horizons | null }) {
  const rows: { name: string; t: Trader["summary"]; bh: BookHorizon | undefined }[] = [
    { name: "Daily trader", t: daily.summary, bh: h?.books.daily },
    { name: `Fast book (settles within ${fast.horizon_days} days, every ${fast.every_hours} h)`, t: fast.summary, bh: h?.books.fast },
  ];
  return (
    <div className="tr-scroll">
      <table className="tr-table" aria-label="Daily trader and fast book compared">
        <thead>
          <tr><th>Book</th><th className="n">P&amp;L</th><th className="n">Held</th><th className="n">Closed</th><th className="n">In profit</th><th className="n">Median time to resolution</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name}>
              <td>{r.name}</td>
              <td className={`n ${r.t.pnl > 0 ? "tr-good" : r.t.pnl < 0 ? "tr-bad" : ""}`}>{usd(r.t.pnl)}</td>
              <td className="n">{r.t.open}</td>
              <td className="n">{r.t.closed}</td>
              <td className="n">{hit(r.t)}</td>
              <td className="n">{days(r.bh?.median_days_to_resolution ?? null)}{r.bh && r.bh.positions > 0 && ` (${r.bh.resolved}/${r.bh.positions})`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
