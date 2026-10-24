import Link from "next/link";

import type { CurvePoint, TraderPosition, TradeRow } from "@/lib/track-record";

// The trader, made watchable: its equity against the mechanical baseline and against doing nothing, what it holds and why, and every trade it has made with
// how it turned out. Server-rendered, no client code. Green is ahead of the start / a winning outcome, red is behind / a losing one.

const pct = (p: number | null) => (p === null ? "n/a" : `${Math.round(p * 100)}%`);
const cents = (p: number | null) => (p === null ? "n/a" : `${Math.round(p * 100)}c`);
const usd = (v: number) => `${v < 0 ? "-" : v > 0 ? "+" : ""}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const money = (v: number) => `$${Math.round(v).toLocaleString("en-US")}`;

function Q({ url, text }: { url: string; text: string }) {
  return url ? (
    <a href={url} rel="noopener noreferrer" className="xt">
      {text}
    </a>
  ) : (
    <>{text}</>
  );
}

const W = 520;
const H = 210;
const L = 52;
const R = 64;
const T = 12;
const B = 24;

export function EquityCurve({ curve, bankroll, name = "Trader", id = "tr-eq", showRule = true }: { curve: CurvePoint[]; bankroll: number; name?: string; id?: string; showRule?: boolean }) {
  if (curve.length === 0) {
    return <p className="tr-empty">The {name.toLowerCase()} has not been marked yet. Its first mark will start this line at ${bankroll.toLocaleString("en-US")}.</p>;
  }
  const vals = curve.flatMap((c) => [c.trader, showRule ? c.rule : null, c.flat]).filter((v): v is number => v !== null);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = Math.max(50, (hi - lo) * 0.15);
  const y0 = lo - pad;
  const y1 = hi + pad;
  const n = curve.length;
  const px = (i: number) => (n === 1 ? (L + W - R) / 2 : L + (i / (n - 1)) * (W - L - R));
  const py = (v: number) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  const path = (pick: (c: CurvePoint) => number | null) => {
    let d = "";
    curve.forEach((c, i) => {
      const v = pick(c);
      if (v !== null) d += `${d ? "L" : "M"}${px(i).toFixed(1)} ${py(v).toFixed(1)} `;
    });
    return d;
  };
  const last = curve[n - 1];
  const ticks = [y0 + pad, (y0 + y1) / 2, y1 - pad].map((v) => Math.round(v / 10) * 10);
  const ahead = last.trader !== null && last.trader >= bankroll;
  const end = (label: string, v: number | null, cls: string) =>
    v === null ? null : (
      <text x={W - R + 6} y={py(v) + 3} className={`tr-endlabel ${cls}`}>
        {label} {money(v)}
      </text>
    );
  return (
    <figure className="tr-fig tr-fig-wide">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={`${id}-t ${id}-d`} className="tr-svg">
        <title id={`${id}-t`}>Paper equity over time: {name}</title>
        <desc id={`${id}-d`}>Daily value of the {name.toLowerCase()}&apos;s paper portfolio{showRule ? ", of the rule-based baseline," : ""} and of the flat starting bankroll.</desc>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={py(v)} y2={py(v)} className="tr-grid" />
            <text x={L - 6} y={py(v) + 3} textAnchor="end" className="tr-tick">{money(v)}</text>
          </g>
        ))}
        <path d={path((c) => c.flat)} className="tr-eq-flat" fill="none" />
        {showRule && <path d={path((c) => c.rule)} className="tr-eq-rule" fill="none" />}
        <path d={path((c) => c.trader)} className={`tr-eq-trader ${ahead ? "tr-ahead" : "tr-behind"}`} fill="none" />
        {n === 1 && last.trader !== null && <circle cx={px(0)} cy={py(last.trader)} r={3} className="tr-pt-ours" />}
        {end(name, last.trader, ahead ? "tr-good" : "tr-bad")}
        {showRule && end("Rules", last.rule, "tr-muted")}
        <text x={W - R + 6} y={py(last.flat) + (last.trader !== null && Math.abs(py(last.flat) - py(last.trader)) < 11 ? 14 : 3)} className="tr-endlabel tr-muted">Start {money(last.flat)}</text>
        <text x={L} y={H - 6} className="tr-tick">{curve[0].day}</text>
        <text x={W - R} y={H - 6} textAnchor="end" className="tr-tick">{last.day}</text>
      </svg>
      <figcaption className="tr-cap">
        Value of each paper portfolio at the end of each day, from the same ${bankroll.toLocaleString("en-US")}. Solid: the {name.toLowerCase()}.{" "}
        {showRule && "Thin: a fixed rule that buys whenever our forecast and the price differ by enough. "}Dotted: doing nothing.
      </figcaption>
    </figure>
  );
}

const VERDICT: Record<string, string> = { sufficient: "evidence sufficient", thin: "evidence thin", gap: "evidence gap" };

// What the position was decided on: the corpus items the bot cited, newest first, linked to the entity or situation page when the site has one.
function Trail({ r }: { r: TraderPosition }) {
  if (r.trail.length === 0) return null;
  return (
    <details className="tr-trail">
      <summary>
        Evidence trail: {r.trail.length} corpus item{r.trail.length === 1 ? "" : "s"}
        {r.evidence && `, ${VERDICT[r.evidence]}`}
      </summary>
      <ul>
        {r.trail.map((t) => (
          <li key={t.id}>
            <span className="tr-tag">{t.kind || "item"}</span> {t.href ? <Link href={t.href} className="xt">{t.title}</Link> : t.title}
            {t.date && <span className="tr-muted"> {t.date.slice(0, 10)}</span>}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function TraderPositions({ rows, empty = "The trader holds nothing right now." }: { rows: TraderPosition[]; empty?: string }) {
  if (rows.length === 0) return <p className="tr-empty">{empty}</p>;
  return (
    <div className="tr-scroll">
      <table className="tr-table">
        <thead>
          <tr>
            <th>Position</th>
            <th>Side</th>
            <th className="n">Bought at</th>
            <th className="n">Now</th>
            <th className="n">Paid in</th>
            <th className="n">Worth</th>
            <th className="n">P&amp;L</th>
            <th>Ends</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.market_id}>
              <td className="q">
                <Q url={r.url} text={r.question} />
                {r.rationale && <span className="tr-why">{r.rationale}{r.rationale_on && ` (${r.rationale_on})`}</span>}
                <Trail r={r} />
              </td>
              <td>{r.side.toUpperCase()}</td>
              <td className="n">{cents(r.entry)}</td>
              <td className="n">{cents(r.now)}</td>
              <td className="n">{money(r.cost)}</td>
              <td className="n">{money(r.value)}</td>
              <td className={`n ${r.pnl > 0 ? "tr-good" : r.pnl < 0 ? "tr-bad" : ""}`}>{usd(r.pnl)}</td>
              <td>{r.ends}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const VERB: Record<TradeRow["action"], string> = { buy_yes: "Bought YES", buy_no: "Bought NO", sell: "Sold", settle: "Paid out" };

export function TradeLog({ rows }: { rows: TradeRow[] }) {
  if (rows.length === 0) return <p className="tr-empty">The trader has not made a trade yet.</p>;
  return (
    <div className="tr-scroll">
      <table className="tr-table" aria-label="Trade log">
        <thead>
          <tr>
            <th>Date</th>
            <th>Trade</th>
            <th className="n">Price</th>
            <th className="n">Amount</th>
            <th>Outcome</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className={r.result === "lost" || (r.pnl !== null && r.pnl < 0) ? "is-miss" : r.result === "won" || (r.pnl !== null && r.pnl > 0) ? "is-win" : undefined}>
              <td>{r.day}</td>
              <td className="q">
                <b className="tr-verb">{VERB[r.action]}</b> <Q url={r.url} text={r.question} />
                {r.rationale && <span className="tr-why">{r.rationale}</span>}
                {r.clips.length > 0 && <span className="tr-why">Trimmed by the book&apos;s limits: {r.clips.join("; ")}</span>}
              </td>
              <td className="n">{r.action === "settle" ? "n/a" : cents(r.price)}</td>
              <td className="n">${r.stake.toLocaleString("en-US", { maximumFractionDigits: 0 })}</td>
              <td>
                {r.pnl !== null ? (
                  <span className={r.pnl > 0 ? "tr-good" : r.pnl < 0 ? "tr-bad" : ""}>{usd(r.pnl)}{r.action === "settle" && r.outcome ? ` (${r.outcome === "void" ? "split" : r.outcome.toUpperCase()})` : ""}</span>
                ) : r.result === "won" ? (
                  <span className="tr-tag is-hit">won, market {r.outcome.toUpperCase()}</span>
                ) : r.result === "lost" ? (
                  <span className="tr-tag is-miss">lost, market {r.outcome.toUpperCase()}</span>
                ) : r.result === "void" ? (
                  <span className="tr-tag">split 50-50</span>
                ) : (
                  <span className="tr-tag">open</span>
                )}
                {r.action !== "settle" && r.ours !== null && r.market !== null && <span className="tr-why">we said {pct(r.ours)}, market {pct(r.market)}</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
