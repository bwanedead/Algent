import type { DayBook, DayGroup, DayRunRow, WishRow } from "@/lib/track-record";

// The day book of the track record (backend `markets/day_report.py`): a paper agent that browses Polymarket itself and picks its own 0-2 day bets.
// Server-rendered. A group's win rate and P&L appear only once it holds the same number of closed trades the forecast verdict needs; before that, the count.

const usd = (v: number) => `${v < 0 ? "-" : v > 0 ? "+" : ""}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const pct = (v: number | null) => (v === null ? "n/a" : `${Math.round(v * 100)}%`);
const when = (iso: string) => iso.slice(0, 16).replace("T", " ") + "Z";

export function DayStats({ d }: { d: DayBook }) {
  const s = d.summary;
  return (
    <ul className="tr-stats">
      <li><span className={`tr-stat-n ${s.pnl > 0 ? "tr-good" : s.pnl < 0 ? "tr-bad" : ""}`}>{usd(s.pnl)}</span><span className="tr-stat-l">P&amp;L, worth ${Math.round(s.equity).toLocaleString("en-US")}</span></li>
      <li><span className="tr-stat-n">{s.open}</span><span className="tr-stat-l">positions held</span></li>
      <li><span className="tr-stat-n">{s.buys + s.sells}</span><span className="tr-stat-l">trades ({s.buys} buys, {s.sells} sells)</span></li>
      <li><span className="tr-stat-n">{s.closed}</span><span className="tr-stat-l">closed ({s.wins}W {s.losses}L{s.closed < d.min_for_verdict ? `; rates shown from ${d.min_for_verdict}` : ""})</span></li>
      <li><span className="tr-stat-n">{d.avg_hold_h === null ? "n/a" : `${d.avg_hold_h.toFixed(1)} h`}</span><span className="tr-stat-l">average hold</span></li>
      <li><span className="tr-stat-n">${d.spend_usd.toFixed(2)}</span><span className="tr-stat-l">spent on its own thinking so far (cap ${d.caps.max_usd_per_day.toFixed(2)} a day)</span></li>
    </ul>
  );
}

function Rows({ rows }: { rows: DayGroup[] }) {
  return (
    <>
      {rows.map((g) => (
        <tr key={g.label}>
          <td>{g.label}</td>
          <td className="n">{g.n}</td>
          <td className="n">{g.shown ? pct(g.hit_rate) : "withheld"}</td>
          <td className={`n ${g.pnl !== null && g.pnl > 0 ? "tr-good" : g.pnl !== null && g.pnl < 0 ? "tr-bad" : ""}`}>{g.shown && g.pnl !== null ? usd(g.pnl) : "withheld"}</td>
        </tr>
      ))}
    </>
  );
}

export function DayGroups({ d }: { d: DayBook }) {
  return (
    <div className="tr-scroll">
      <table className="tr-table" aria-label="Day book results by horizon and category">
        <thead>
          <tr><th>Closed trades by time left when bought</th><th className="n">Closed</th><th className="n">In profit</th><th className="n">P&amp;L</th></tr>
        </thead>
        <tbody>
          <Rows rows={d.by_horizon} />
          {d.by_category.length > 0 && (
            <tr><th colSpan={4}>By category (first tag of the market)</th></tr>
          )}
          <Rows rows={d.by_category} />
        </tbody>
      </table>
      <p className="tr-note">Win rate and P&amp;L are withheld until a group holds {d.min_for_verdict} closed trades, the same rule as the forecast verdict.</p>
    </div>
  );
}

function Run({ r }: { r: DayRunRow }) {
  return (
    <li>
      <b>{when(r.at)}</b> <span className="tr-muted">{r.turns} turns, {r.tool_calls} tool calls, {r.n_considered} markets looked at, {r.n_queries} corpus queries, ${r.usd.toFixed(3)}</span>
      {r.summary && <span className="tr-why">{r.summary}</span>}
      {r.orders.length === 0 ? <span className="tr-why">No orders: it held cash.</span> : (
        <ul>
          {r.orders.map((o, i) => (
            <li key={`${o.market_id}-${i}`}>
              <span className="tr-tag">{o.action === "hold" ? "refused" : o.action.replace("_", " ")}</span> {o.question} {o.action !== "hold" && <span className="tr-muted">${Math.round(o.stake)} at {Math.round(o.price * 100)}c</span>}
              {o.reason && <span className="tr-why">{o.reason}</span>}
              {o.clips.length > 0 && <span className="tr-why">Trimmed by the book&apos;s limits: {o.clips.join("; ")}</span>}
            </li>
          ))}
        </ul>
      )}
      {(r.considered.length > 0 || r.queries.length > 0) && (
        <details>
          <summary>What it browsed</summary>
          {r.considered.length > 0 && <p className="tr-note">Markets: {r.considered.map((c) => c.question).join("; ")}</p>}
          {r.queries.length > 0 && <p className="tr-note">Corpus queries: {r.queries.join("; ")}</p>}
        </details>
      )}
    </li>
  );
}

export function DayRuns({ rows }: { rows: DayRunRow[] }) {
  if (rows.length === 0) return <p className="tr-empty">The day book has not run yet.</p>;
  return <ul className="tr-gaps">{rows.map((r) => <Run key={r.id} r={r} />)}</ul>;
}

export function Wishes({ rows }: { rows: WishRow[] }) {
  if (rows.length === 0) return <p className="tr-empty">It has not named anything the corpus is missing yet.</p>;
  return (
    <ul className="tr-gaps">
      {rows.map((w) => (
        <li key={w.topic}>
          <b>{w.topic}</b> <span className="tr-muted">wanted in {w.runs} run{w.runs === 1 ? "" : "s"}, last {w.last}</span>
          {w.why && <span className="tr-why">{w.why}</span>}
          {w.source && <span className="tr-why">Would come from: {w.source}</span>}
          {w.markets.length > 0 && <span className="tr-why">For: {w.markets.map((m) => m.question).filter(Boolean).slice(0, 2).join("; ")}</span>}
        </li>
      ))}
    </ul>
  );
}
