import type { ReactNode } from "react";

import type { CurvePoint, TrackRecord, Trader, TraderPosition, TradeRow } from "@/lib/track-record";

import { DayRuns, Wishes } from "./DayBook";
import { OpenPositions } from "./TrackTables";

// The top of /intel/track-record: ONE portfolio-value chart (a line per bot, each labelled at its end in its own colour) and ONE summary row per bot that
// expands to that bot's open positions and trades. Server-rendered, no client code. Prices are the latest snapshot we hold ("as of HH:MM"), never invented.

const money = (v: number) => `$${Math.round(v).toLocaleString("en-US")}`;
const usd = (v: number) => `${v < 0 ? "-" : v > 0 ? "+" : ""}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const cents = (p: number | null) => (p === null ? "n/a" : `${Math.round(p * 100)}c`);
const tone = (v: number) => (v > 0 ? "tr-good" : v < 0 ? "tr-bad" : "");
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-10-24T08:40" -> "Oct 24 08:40Z". */
export function stamp(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso);
  return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])} ${m[4]}:${m[5]}Z` : iso || "never";
}
const left = (h: number | null) => (h === null ? "" : h < 48 ? `${Math.max(0, Math.round(h))} h left` : `${Math.round(h / 24)} d left`);

type Line = { id: string; name: string; cls: string; pts: Map<string, number> };

function lines(t: TrackRecord): Line[] {
  const pick = (curve: CurvePoint[], key: "trader" | "rule") => new Map(curve.flatMap((c) => (c[key] === null ? [] : [[c.day, c[key] as number] as const])));
  const out: Line[] = [{ id: "daily", name: "Daily trader", cls: "daily", pts: pick(t.trader.curve, "trader") }];
  if (t.fast) out.push({ id: "fast", name: "Fast book", cls: "fast", pts: pick(t.fast.curve, "trader") });
  if (t.day) out.push({ id: "day", name: "Day book", cls: "day", pts: pick(t.day.curve, "trader") });
  out.push({ id: "rule", name: "Fixed rule", cls: "rule", pts: pick(t.trader.curve, "rule") });
  return out.filter((l) => l.pts.size > 0);
}

const W = 640;
const H = 230;
const L = 50;
const R = 138;
const T = 12;
const B = 24;

export function ValueChart({ t }: { t: TrackRecord }) {
  const start = t.trader.limits.bankroll;
  const ls = lines(t);
  if (ls.length === 0) return <p className="tr-empty">No bot has been marked yet. The first mark starts every line at {money(start)}.</p>;
  const days = [...new Set(ls.flatMap((l) => [...l.pts.keys()]))].sort();
  const vals = [start, ...ls.flatMap((l) => [...l.pts.values()])];
  const pad = Math.max(40, (Math.max(...vals) - Math.min(...vals)) * 0.2);
  const y0 = Math.min(...vals) - pad;
  const y1 = Math.max(...vals) + pad;
  const px = (d: string) => (days.length === 1 ? (L + W - R) / 2 : L + (days.indexOf(d) / (days.length - 1)) * (W - L - R));
  const py = (v: number) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  const ends = ls.map((l) => {
    const ks = [...l.pts.keys()].sort();
    const d = ks[ks.length - 1];
    return { l, d, v: l.pts.get(d) as number, y: py(l.pts.get(d) as number) };
  });
  const ly = new Map<string, number>();                                      // labels sit at their line's end, nudged apart so none overlap
  [...ends].sort((a, b) => a.y - b.y).forEach((e, i, all) => ly.set(e.l.id, i === 0 ? e.y : Math.max(e.y, (ly.get(all[i - 1].l.id) as number) + 12)));
  const ticks = [y0 + pad, (y0 + y1) / 2, y1 - pad].map((v) => Math.round(v / 10) * 10);
  return (
    <figure className="tr-fig tr-fig-wide tr-top">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="tr-vc-t tr-vc-d" className="tr-svg">
        <title id="tr-vc-t">Portfolio value of each paper bot over time</title>
        <desc id="tr-vc-d">One line per bot with its name and current value at the end of the line. The dotted line is the {money(start)} starting money.</desc>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={py(v)} y2={py(v)} className="tr-grid" />
            <text x={L - 6} y={py(v) + 3} textAnchor="end" className="tr-tick">{money(v)}</text>
          </g>
        ))}
        <line x1={L} x2={W - R} y1={py(start)} y2={py(start)} className="tr-eq-flat" />
        <text x={L + 4} y={py(start) - 4} className="tr-tick">Start {money(start)}</text>
        {ls.map((l) => {
          const keys = [...l.pts.keys()].sort();
          return (
            <g key={l.id}>
              <path d={keys.map((d, i) => `${i ? "L" : "M"}${px(d).toFixed(1)} ${py(l.pts.get(d) as number).toFixed(1)}`).join(" ")} className={`tr-l tr-l-${l.cls}`} fill="none" />
              {keys.length === 1 && <circle cx={px(keys[0])} cy={py(l.pts.get(keys[0]) as number)} r={3} className={`tr-d-${l.cls}`} />}
            </g>
          );
        })}
        {ends.map((e) => (
          <text key={e.l.id} x={W - R + 6} y={(ly.get(e.l.id) ?? e.y) + 3} className={`tr-end tr-t-${e.l.cls}`}>
            {e.l.name} {money(e.v)}
          </text>
        ))}
        <text x={L} y={H - 6} className="tr-tick">{days[0]}</text>
        <text x={W - R} y={H - 6} textAnchor="end" className="tr-tick">{days[days.length - 1]}</text>
      </svg>
      <figcaption className="tr-cap">Paper money, each bot starts at {money(start)}. Value is cash plus open positions at their latest price, marked once a day.</figcaption>
    </figure>
  );
}

// ── one expandable row per bot ───────────────────────────────────────────────────────────────────
type Row = { id: string; name: string; cls: string; blurb: string; t: Trader };

function WinRate({ t, min }: { t: Trader["summary"]; min: number }) {
  const n = t.wins + t.losses;
  return <>{n >= min && t.hit_rate !== null ? `${Math.round(t.hit_rate * 100)}% (${t.wins}W ${t.losses}L)` : `n=${n}, too early`}</>;
}

function Cell({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return <span className={`tr-c ${className}`} data-label={label}>{children}</span>;
}

function Positions({ rows }: { rows: TraderPosition[] }) {
  if (rows.length === 0) return <p className="tr-empty">Nothing held right now.</p>;
  return (
    <table className="tr-table tr-stack" aria-label="Open positions">
      <thead>
        <tr><th>Market</th><th>Side</th><th className="n">Entry</th><th className="n">Now</th><th className="n">Stake</th><th className="n">Unrealised</th><th>Resolves</th></tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.market_id}>
            <td className="q" data-label="Market">
              {r.url ? <a href={r.url} rel="noopener noreferrer" className="xt" title={r.rationale}>{r.question}</a> : r.question}
              {r.rationale && <details className="tr-why-d"><summary>why</summary>{r.rationale}</details>}
            </td>
            <td data-label="Side">{r.side.toUpperCase()}</td>
            <td className="n" data-label="Entry">{cents(r.entry)}</td>
            <td className="n" data-label={r.now_at ? `Now, as of ${r.now_at.slice(11, 16)}Z` : "Now"}>{cents(r.now)}</td>
            <td className="n" data-label="Stake">{money(r.cost)}</td>
            <td className={`n ${tone(r.pnl)}`} data-label="Unrealised">{usd(r.pnl)}</td>
            <td data-label="Resolves">{r.ends_at ? stamp(r.ends_at) : r.ends}{r.hours_left !== null && <span className="tr-why">{left(r.hours_left)}</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const VERB: Record<TradeRow["action"], string> = { buy_yes: "Buy YES", buy_no: "Buy NO", sell: "Sell", settle: "Settled" };

function Trades({ rows }: { rows: TradeRow[] }) {
  if (rows.length === 0) return <p className="tr-empty">No trades yet.</p>;
  return (
    <table className="tr-table tr-stack" aria-label="Trade log">
      <thead>
        <tr><th>Date</th><th>Trade</th><th>Market</th><th className="n">Price</th><th className="n">Amount</th><th className="n">Realised</th><th>Reason</th></tr>
      </thead>
      <tbody>
        {rows.slice(0, 40).map((r) => (
          <tr key={r.id}>
            <td data-label="Date">{r.day}</td>
            <td data-label="Trade"><b className="tr-verb">{VERB[r.action]}</b></td>
            <td className="q" data-label="Market">{r.url ? <a href={r.url} rel="noopener noreferrer" className="xt">{r.question}</a> : r.question}</td>
            <td className="n" data-label="Price">{r.action === "settle" ? "n/a" : cents(r.price)}</td>
            <td className="n" data-label="Amount">{money(r.stake)}</td>
            <td className={`n ${r.pnl === null ? "" : tone(r.pnl)}`} data-label="Realised">{r.pnl === null ? (r.result ? r.result : "open") : usd(r.pnl)}</td>
            <td className="why1" data-label="Reason" title={[r.rationale, ...r.clips.map((c) => `trimmed: ${c}`)].join(" | ")}>{r.rationale || "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function BookRow({ row, min, children }: { row: Row; min: number; children?: ReactNode }) {
  const s = row.t.summary;
  const bank = row.t.limits.bankroll;
  return (
    <details className={`tr-book tr-b-${row.cls}`}>
      <summary className="tr-row">
        <Cell label="Bot" className="tr-name"><i className={`tr-sw tr-bg-${row.cls}`} aria-hidden="true" /> <b>{row.name}</b><span className="tr-why">{row.blurb}</span></Cell>
        <Cell label="Value" className="n">{money(s.equity)}</Cell>
        <Cell label="P&L" className={`n ${tone(s.pnl)}`}>{usd(s.pnl)} ({s.pnl >= 0 ? "+" : ""}{((s.pnl / bank) * 100).toFixed(1)}%)</Cell>
        <Cell label="Open" className="n">{s.open}</Cell>
        <Cell label="Cash" className="n">{money(s.cash)}</Cell>
        <Cell label="Trades" className="n">{s.buys + s.sells}</Cell>
        <Cell label="Win rate" className="n"><WinRate t={s} min={min} /></Cell>
        <Cell label="Last run" className="n">{stamp(row.t.last_at)}</Cell>
      </summary>
      <div className="tr-detail">
        <h3 className="tr-h3">Open positions</h3>
        <Positions rows={row.t.open_positions} />
        <h3 className="tr-h3">Trades, newest first</h3>
        <Trades rows={row.t.log} />
        {children}
      </div>
    </details>
  );
}

export function Books({ t }: { t: TrackRecord }) {
  const min = t.rules.min_for_verdict;
  const rows: Row[] = [{ id: "daily", name: "Daily trader", cls: "daily", blurb: "once a day, markets we forecast", t: t.trader }];
  if (t.fast) rows.push({ id: "fast", name: "Fast book", cls: "fast", blurb: `settles within ${t.fast.horizon_days} days, every ${t.fast.every_hours} h`, t: t.fast });
  const rule = t.portfolio;
  const ruleValue = rule.bankroll + rule.total_pnl;
  return (
    <div className="tr-books" role="group" aria-label="Bots">
      <div className="tr-row tr-rowhead" aria-hidden="true">
        <span>Bot</span><span className="n">Value</span><span className="n">P&amp;L</span><span className="n">Open</span><span className="n">Cash</span><span className="n">Trades</span><span className="n">Win rate</span><span className="n">Last run</span>
      </div>
      {rows.map((r) => <BookRow key={r.id} row={r} min={min} />)}
      {t.day && (
        <BookRow row={{ id: "day", name: "Day book", cls: "day", blurb: `picks its own bets, ${t.day.horizon_hours} h out, ${t.day.run_hours.length} runs a day`, t: t.day }} min={min}>
          <h3 className="tr-h3">Latest run: what it browsed and why</h3>
          <DayRuns rows={t.day.runs.slice(0, 1)} />
          <h3 className="tr-h3">What it wished we knew</h3>
          <Wishes rows={t.day.wishes.slice(0, 3)} />
        </BookRow>
      )}
      <details className="tr-book tr-b-rule">
        <summary className="tr-row">
          <Cell label="Bot" className="tr-name"><i className="tr-sw tr-bg-rule" aria-hidden="true" /> <b>Fixed rule</b><span className="tr-why">baseline: no judgement, never sells early</span></Cell>
          <Cell label="Value" className="n">{money(ruleValue)}</Cell>
          <Cell label="P&L" className={`n ${tone(rule.total_pnl)}`}>{usd(rule.total_pnl)} ({rule.total_pnl >= 0 ? "+" : ""}{((rule.total_pnl / rule.bankroll) * 100).toFixed(1)}%)</Cell>
          <Cell label="Open" className="n">{rule.open}</Cell>
          <Cell label="Cash" className="n">{money(rule.bankroll - rule.staked_open + rule.realised_pnl)}</Cell>
          <Cell label="Trades" className="n">{rule.open + rule.settled}</Cell>
          <Cell label="Win rate" className="n">{rule.wins + rule.losses >= min && rule.hit_rate !== null ? `${Math.round(rule.hit_rate * 100)}% (${rule.wins}W ${rule.losses}L)` : `n=${rule.wins + rule.losses}, too early`}</Cell>
          <Cell label="Last run" className="n">{stamp(t.as_of)}</Cell>
        </summary>
        <div className="tr-detail">
          <h3 className="tr-h3">Open positions</h3>
          <OpenPositions rows={t.open_positions} />
        </div>
      </details>
    </div>
  );
}
