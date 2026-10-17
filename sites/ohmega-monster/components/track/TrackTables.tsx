import type { Disagreement, OpenPosition, ResolvedRow } from "@/lib/track-record";

const pct = (p: number | null) => (p === null ? "n/a" : `${Math.round(p * 100)}%`);
const usd = (v: number) => `${v < 0 ? "-" : v > 0 ? "+" : ""}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

function Q({ url, text }: { url: string; text: string }) {
  return url ? (
    <a href={url} rel="noopener noreferrer" className="xt">
      {text}
    </a>
  ) : (
    <>{text}</>
  );
}

export function Disagreements({ rows }: { rows: Disagreement[] }) {
  if (rows.length === 0) return <p className="tr-empty">No open market differs from our latest forecast by 15 points or more right now.</p>;
  return (
    <div className="tr-scroll">
      <table className="tr-table">
        <thead>
          <tr>
            <th>Question</th>
            <th className="n">Ours</th>
            <th className="n">Market</th>
            <th className="n">Gap</th>
            <th>Made</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.market_id}>
              <td className="q">
                <Q url={r.url} text={r.question} />
                {r.rationale && <span className="tr-why">{r.rationale}</span>}
              </td>
              <td className="n">{pct(r.ours)}</td>
              <td className="n">{pct(r.market)}</td>
              <td className="n">{r.gap > 0 ? "+" : ""}{Math.round(r.gap * 100)} pts</td>
              <td>{r.made_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function OpenPositions({ rows }: { rows: OpenPosition[] }) {
  if (rows.length === 0) return <p className="tr-empty">No open paper positions: no forecast of ours has differed from its market by enough yet.</p>;
  return (
    <div className="tr-scroll">
      <table className="tr-table">
        <thead>
          <tr>
            <th>Question</th>
            <th>Side</th>
            <th className="n">Ours</th>
            <th className="n">Market then</th>
            <th className="n">Market now</th>
            <th className="n">Stake</th>
            <th className="n">P&amp;L</th>
            <th>Ends</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.market_id}>
              <td className="q"><Q url={r.url} text={r.question} /></td>
              <td>{r.side.toUpperCase()}</td>
              <td className="n">{pct(r.ours)}</td>
              <td className="n">{pct(r.market_at_open)}</td>
              <td className="n">{pct(r.market_now)}</td>
              <td className="n">${r.stake.toLocaleString("en-US", { maximumFractionDigits: 0 })}</td>
              <td className={`n ${r.pnl > 0 ? "tr-good" : r.pnl < 0 ? "tr-bad" : ""}`}>{usd(r.pnl)}</td>
              <td>{r.ends}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Resolved({ rows, label }: { rows: ResolvedRow[]; label: string }) {
  if (rows.length === 0) return <p className="tr-empty">Nothing has resolved against a forecast of ours yet.</p>;
  return (
    <div className="tr-scroll">
      <table className="tr-table" aria-label={label}>
        <thead>
          <tr>
            <th>Question</th>
            <th>Result</th>
            <th className="n">Ours</th>
            <th className="n">Market</th>
            <th className="n">Our error</th>
            <th>Closer</th>
            <th>Resolved</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.market_id}-${r.made_at}`} className={r.ours_closer === false ? "is-miss" : undefined}>
              <td className="q">
                <Q url={r.url} text={r.question} />
                {r.rationale && <span className="tr-why">{r.rationale}</span>}
              </td>
              <td>{r.outcome.toUpperCase()}</td>
              <td className="n">{pct(r.ours)}</td>
              <td className="n">{pct(r.market)}</td>
              <td className="n">{r.brier_ours.toFixed(3)}</td>
              <td>
                {r.ours_closer === null ? <span className="tr-tag">unpriced</span> : r.ours_closer ? <span className="tr-tag is-hit">us</span> : <span className="tr-tag is-miss">market</span>}
              </td>
              <td>{r.resolved_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
