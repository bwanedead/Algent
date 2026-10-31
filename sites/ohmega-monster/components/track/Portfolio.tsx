import type { ReactNode } from "react";

import type { CurvePoint, ForecastStats, RestingFill, RestingOrder, Strategy, TrackRecord, Trader, TraderPosition, TradeRow } from "@/lib/track-record";

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

// Short chart names (the line is labelled at its end; the table below has the full names). "MT" = must trade.
const SHORT: Record<string, string> = {
  day: "Day", daily: "Daily", fast: "Fast", hourly: "Hourly", "base-rate": "Base rate", delineation: "Delineation", "delineation-base-rate": "Delin.+base rate",
  "baseline-must-trade": "Baseline MT", "delineation-must-trade": "Delin. MT",
};

function lines(t: TrackRecord): Line[] {
  const pick = (curve: CurvePoint[], key: "trader" | "rule") => new Map(curve.flatMap((c) => (c[key] === null ? [] : [[c.day, c[key] as number] as const])));
  const out: Line[] = t.strategies.length
    ? t.strategies.map((x) => ({ id: x.id, name: SHORT[x.id] ?? x.name, cls: x.id, pts: pick(x.curve, "trader") }))
    : [
        { id: "daily", name: "Daily trader", cls: "daily", pts: pick(t.trader.curve, "trader") },
        ...(t.fast ? [{ id: "fast", name: "Fast book", cls: "fast", pts: pick(t.fast.curve, "trader") }] : []),
        ...(t.day ? [{ id: "day", name: "Day book", cls: "day", pts: pick(t.day.curve, "trader") }] : []),
      ];
  out.push({ id: "rule", name: "Fixed rule (retired)", cls: "rule", pts: pick(t.trader.curve, "rule") });
  return out.filter((l) => l.pts.size > 0);
}

const W = 640;
const H = 270;
const L = 50;
const R = 150;
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
type Row = { id: string; name: string; cls: string; bot: string; botName: string; desk: string; deskAbout: string; style: string; next: string; mustTrade?: number; minFillsDay?: number; t: Trader; lastRun: string; s?: Strategy };

// A bot is a reasoning method stack; its desks are cadences/horizons, one book each. One-line "how it reasons" per bot (the lab mind ids, backend `markets/methods.py`).
const BOT_ABOUT: Record<string, string> = {
  p0b: "Researches the corpus and states its own probability; no extra method.",
  "p0b+prior": "Starts from the base rate of the reference class; trades only on edge the evidence earns.",
  b: "Maps the possible outcomes first; trades the ones the price mis-states.",
  "b+prior": "Base rate first, then maps the possible outcomes.",
};

/** "8 made, 3 resolved, Brier 0.21" once enough have resolved; before that "n=3, too early". */
function forecastLine(f: ForecastStats): string {
  if (!f.made) return "none yet";
  return f.shown && f.brier !== null ? `${f.made} made, ${f.resolved} resolved, Brier ${f.brier.toFixed(3)}` : `${f.made} made, ${f.resolved} resolved (n=${f.resolved}, too early)`;
}
const signed3 = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(3)}`;

/** The pill's second sub line: our Brier edge over the market's price at the same moment, or "n=8, too early". Null when nothing has resolved. */
function skillSub(f: ForecastStats | undefined): { text: string; cls: string } | null {
  const a = f?.skill.all;
  if (!a || (!a.n && !f?.made)) return null;
  return a.shown && a.mean !== null ? { text: `vs market ${signed3(a.mean)} (n=${a.n})`, cls: tone(a.mean) } : { text: `vs market: n=${a.n}, too early`, cls: "" };
}

/** "Against the market price at the same moment: +0.012 Brier on 24 resolved (contested only: -0.004 on 9)." Empty until the first numbers are shown. */
function skillSentence(f: ForecastStats): string {
  const { all, contested } = f.skill;
  if (!all.shown || all.mean === null) return all.n ? `Against the market price at the same moment: n=${all.n} resolved, too early.` : "";
  const c = contested.shown && contested.mean !== null ? ` (contested only: ${signed3(contested.mean)} on ${contested.n})` : ` (contested only: n=${contested.n}, too early)`;
  return `Against the market price at the same moment: ${signed3(all.mean)} Brier on ${all.n} resolved${c}.`;
}

const pct0 = (v: number) => `${Math.round(v * 100)}%`;

function Forecasts({ f }: { f: ForecastStats }) {
  if (!f.recent.length) return <p className="tr-note">No forecasts recorded yet.</p>;
  return (
    <table className="tr-table tr-stack" aria-label="Recent forecasts">
      <thead><tr><th>Market</th><th className="n">Its view</th><th className="n">Market</th><th className="n">Outcome</th></tr></thead>
      <tbody>
        {f.recent.map((r) => (
          <tr key={`${r.market_id}-${r.at}`}>
            <td className="q" data-label="Market" title={r.reason}>{r.question}</td>
            <td className="n" data-label="Its view">{pct0(r.p)}</td>
            <td className="n" data-label="Market">{r.market === null ? "n/a" : pct0(r.market)}</td>
            <td className="n" data-label="Outcome">{r.outcome ? r.outcome.toUpperCase() : "open"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function WinRate({ t, min }: { t: Trader["summary"]; min: number }) {
  const n = t.wins + t.losses;
  return <>{n >= min && t.hit_rate !== null ? `${Math.round(t.hit_rate * 100)}% (${t.wins}W ${t.losses}L)` : `n=${n}, too early`}</>;
}

function Cell({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return <span className={`tr-c ${className}`} data-label={label}>{children}</span>;
}

/** A detail section with a clear band for its heading, so one ends and the next begins at a glance. */
function Sec({ title, children }: { title: string; children: ReactNode }) {
  return <section className="tr-sec"><h3 className="tr-h3">{title}</h3><div className="tr-sec-b">{children}</div></section>;
}

/** YES / NO as two neutral badge styles: the side is not good or bad. */
const Side = ({ side }: { side: string }) => <b className={`tr-side tr-side-${side.toLowerCase() === "no" ? "no" : "yes"}`}>{side.toUpperCase()}</b>;

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
            <td data-label="Side"><Side side={r.side} /></td>
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

/** Resting limit orders: what each waits for (the limit is the all-in price per share on its side), its size, and when it gives up. Filled ones are listed beneath. */
function Resting({ open, fills }: { open: RestingOrder[]; fills: RestingFill[] }) {
  if (open.length === 0 && fills.length === 0) return <p className="tr-empty">No resting orders.</p>;
  return (
    <>
      {open.length > 0 && (
        <table className="tr-table tr-stack" aria-label="Resting orders">
          <thead><tr><th>Order</th><th>Market</th><th className="n">Limit</th><th className="n">Now</th><th className="n">Size</th><th>Expires</th></tr></thead>
          <tbody>
            {open.map((o) => (
              <tr key={o.id}>
                <td data-label="Order"><b className="tr-verb">{o.action === "sell" ? "Sell" : "Buy"}</b> {o.side && <Side side={o.side} />}</td>
                <td className="q" data-label="Market">
                  {o.url ? <a href={o.url} rel="noopener noreferrer" className="xt" title={o.reason}>{o.question}</a> : o.question}
                  {o.reason && <details className="tr-why-d"><summary>why</summary>{o.reason}</details>}
                </td>
                <td className="n" data-label={o.action === "sell" ? "Sells at or above" : "Buys at or below"}>{cents(o.limit)}</td>
                <td className="n" data-label="Now">{cents(o.now)}</td>
                <td className="n" data-label="Size">{o.action === "sell" ? `${Math.round(o.fraction * 100)}% of position` : money(o.usd)}</td>
                <td data-label="Expires">{stamp(o.expires_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {fills.length > 0 && (
        <p className="tr-note">
          Recent fills from resting orders: {fills.map((f) => `${f.action === "sell" ? "sold" : "bought"} ${f.side.toUpperCase()} ${money(f.stake)} at ${cents(f.price)} (${stamp(f.at)}) - ${clip(f.question, 40)}`).join("; ")}.
        </p>
      )}
    </>
  );
}

type Held = { side: string; question: string; stake: number; pnl: number };
const clip = (q: string, n = 60) => (q.length > n ? `${q.slice(0, n - 1).trimEnd()}…` : q);

/** What a bot holds, at a glance: count and money at risk, then its three biggest stakes. */
function Holding({ held, note, resting = 0 }: { held: Held[]; note?: string; resting?: number }) {
  const rest = resting > 0 ? <span className="tr-muted">+{resting} resting</span> : null;
  if (held.length === 0) return <span className="tr-hold"><span className="tr-muted">{note ?? "nothing held"}</span>{rest}</span>;
  const top = [...held].sort((a, b) => b.stake - a.stake);
  return (
    <span className="tr-hold">
      <span className="tr-hold-sum">{note ?? `${held.length} open · ${money(held.reduce((a, h) => a + h.stake, 0))} at risk`}</span>
      {top.slice(0, 3).map((h, i) => (
        <span key={i} className="tr-hold-l" title={h.question}>
          <Side side={h.side} />
          <span className="tr-hold-q">{clip(h.question)}</span>
          <span className="n">{money(h.stake)}</span>
          <span className={`n ${tone(h.pnl)}`}>{usd(h.pnl)}</span>
        </span>
      ))}
      {top.length > 3 && <span className="tr-muted">+{top.length - 3} more</span>}
      {rest}
    </span>
  );
}

function Runs({ last, next }: { last: string; next: string }) {
  if (next === "retired") return <span className="tr-muted">retired</span>;
  return (
    <span className="tr-runs">
      <span>last {stamp(last)}</span>
      <span className="tr-muted">{next ? `next ${stamp(next)}` : "next n/a"}</span>
    </span>
  );
}

/** One bot's own value line (its colour), from its marked days plus the live equity as "now"; a dotted line marks the starting bankroll. */
function BotChart({ row }: { row: Row }) {
  const start = row.t.limits.bankroll;
  const pts: { d: string; v: number }[] = row.t.curve.flatMap((c) => (c.trader === null ? [] : [{ d: c.day, v: c.trader }]));
  if (pts.length === 0) return <p className="tr-empty">Not marked yet.</p>;
  const eq = row.t.summary.equity;
  if (pts[pts.length - 1].v !== eq) pts.push({ d: "now", v: eq });
  const w = 640, h = 150, l = 50, r = 90, tp = 10, bt = 22;
  const vals = [start, ...pts.map((p) => p.v)];
  const pad = Math.max(40, (Math.max(...vals) - Math.min(...vals)) * 0.2);
  const y0 = Math.min(...vals) - pad;
  const y1 = Math.max(...vals) + pad;
  const px = (i: number) => (pts.length === 1 ? (l + w - r) / 2 : l + (i / (pts.length - 1)) * (w - l - r));
  const py = (v: number) => tp + (1 - (v - y0) / (y1 - y0)) * (h - tp - bt);
  const last = pts[pts.length - 1];
  const ticks = [y0 + pad, y1 - pad].map((v) => Math.round(v / 10) * 10);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} role="img" className="tr-svg tr-botchart">
      <title>{`${row.desk}: portfolio value over time, now ${money(eq)}, started at ${money(start)}`}</title>
      {ticks.map((v) => (
        <g key={v}>
          <line x1={l} x2={w - r} y1={py(v)} y2={py(v)} className="tr-grid" />
          <text x={l - 6} y={py(v) + 3} textAnchor="end" className="tr-tick">{money(v)}</text>
        </g>
      ))}
      <line x1={l} x2={w - r} y1={py(start)} y2={py(start)} className="tr-eq-flat" />
      <text x={l + 4} y={py(start) - 4} className="tr-tick">Start {money(start)}</text>
      <path d={pts.map((p, i) => `${i ? "L" : "M"}${px(i).toFixed(1)} ${py(p.v).toFixed(1)}`).join(" ")} className="tr-botline" fill="none" />
      {pts.length === 1 && <circle cx={px(0)} cy={py(pts[0].v)} r={3} className="tr-botdot" />}
      <text x={w - r + 6} y={py(last.v) + 3} className="tr-end tr-botend">{money(last.v)}</text>
      <text x={l} y={h - 6} className="tr-tick">{pts[0].d}</text>
      {pts.length > 1 && <text x={w - r} y={h - 6} textAnchor="end" className="tr-tick">{last.d}</text>}
    </svg>
  );
}

function BookRow({ row, min, children }: { row: Row; min: number; children?: ReactNode }) {
  const s = row.t.summary;
  const bank = row.t.limits.bankroll;
  return (
    <details className={`tr-book tr-b-${row.cls}`}>
      <summary className="tr-row">
        <Cell label="Desk" className="tr-name">
          <i className={`tr-sw tr-bg-${row.cls}`} aria-hidden="true" /> <b>{row.desk}</b>{row.mustTrade ? <span className="tr-tag" title={`Fills at least ${row.mustTrade} order(s) every run, for faster feedback`}>must trade</span> : null}
          {row.minFillsDay ? <span className="tr-tag" title={`Fills at least ${row.minFillsDay} order(s) every UTC day, enforced on the day's last run; an unmet day is recorded as unmet`}>{row.minFillsDay}+ fill / day</span> : null}
          <span className="tr-sub">{row.deskAbout}</span>
        </Cell>
        <Cell label="Value" className="n">
          {money(s.equity)}
          <span className={`tr-sub ${tone(s.pnl)}`}>{usd(s.pnl)} ({s.pnl >= 0 ? "+" : ""}{((s.pnl / bank) * 100).toFixed(1)}%)</span>
          {(() => { const k = skillSub(row.s?.forecasts); return k ? <span className={`tr-sub ${k.cls}`}>{k.text}</span> : null; })()}
        </Cell>
        <Cell label="Holding"><Holding held={row.t.open_positions.map((p) => ({ side: p.side, question: p.question, stake: p.cost, pnl: p.pnl }))} resting={row.s?.resting.open.length ?? 0} /></Cell>
        <Cell label="Runs" className="n"><Runs last={row.lastRun} next={row.next} /></Cell>
      </summary>
      <div className="tr-detail">
        <Sec title="Value over time"><BotChart row={row} /></Sec>
        <p className="tr-note">
          Style: {row.style}. Forecasts: {row.s ? forecastLine(row.s.forecasts) : "n/a"}.{row.s && skillSentence(row.s.forecasts) ? ` ${skillSentence(row.s.forecasts)}` : ""}
          {row.s?.exposure ? ` Exposure ${pct0(row.s.exposure.pct)} (floor ${pct0(row.s.exposure.floor_pct)}).` : ""} {s.buys + s.sells} trades.
          {" "}Win rate: <WinRate t={s} min={min} />. Cash {money(s.cash)}.
        </p>
        {row.s ? (
          <>
            <Sec title="Recent forecasts"><Forecasts f={row.s.forecasts} /></Sec>
            {row.s.floor?.opened ? (
              <p className="tr-note">
                Floor positions (opened only to keep exposure up, no real edge): {row.s.floor.opened} opened.{" "}
                {row.s.floor.groups.map((g) => `${g.label}: ${g.n} closed${g.shown && g.pnl !== null ? `, ${usd(g.pnl)}` : ""}`).join("; ")}.
              </p>
            ) : null}
          </>
        ) : null}
        <Sec title={`Open positions (${row.t.open_positions.length})`}><Positions rows={row.t.open_positions} /></Sec>
        {row.s?.resting && (row.s.resting.open.length > 0 || row.s.resting.fills.length > 0) ? (
          <Sec title={`Resting orders (${row.s.resting.open.length})`}><Resting open={row.s.resting.open} fills={row.s.resting.fills} /></Sec>
        ) : null}
        <Sec title="Trades, newest first"><Trades rows={row.t.log} /></Sec>
        {children}
      </div>
      <div className="tr-end-band" aria-hidden="true">end of {row.desk} · {row.botName}</div>
    </details>
  );
}

const BOT_ORDER = ["p0b", "p0b+prior", "b", "b+prior"];

function fromStrategy(x: Strategy): Row {
  return { id: x.id, name: x.name, cls: x.id, bot: x.bot, botName: x.bot_name, desk: x.desk_name || x.name, deskAbout: x.desk_about, minFillsDay: x.min_fills_day || undefined, style: x.style, next: x.next_run, mustTrade: x.must_trade ? x.min_orders : undefined, t: x, lastRun: x.runs[0]?.at || x.last_at, s: x };
}

export function Books({ t }: { t: TrackRecord }) {
  const min = t.rules.min_for_verdict;
  // Every bot is its own forecaster (no shared desk forecast), so there is one roster, grouped by reasoning method. A document from before the roster
  // falls back to the three books it knew.
  const strategies = t.strategies.length
    ? t.strategies
    : [];
  const rows: Row[] = strategies.length
    ? strategies.map(fromStrategy)
    : [
        { id: "daily", name: "Daily trader", cls: "daily", bot: "p0b", botName: "Desk forecast", desk: "Daily trader", deskAbout: "", style: "once a day, markets we forecast", next: "", t: t.trader, lastRun: t.trader.last_at },
        ...(t.fast ? [{ id: "fast", name: "Fast book", cls: "fast", bot: "p0b", botName: "Desk forecast", desk: "Fast book", deskAbout: "", style: `settles within ${t.fast.horizon_days} days`, next: "", t: t.fast, lastRun: t.fast.last_at }] : []),
        ...(t.day ? [{ id: "day", name: "Day book", cls: "day", bot: "p0b", botName: "Baseline research", desk: "Day book", deskAbout: "", style: `picks its own bets, ${t.day.horizon_hours} h out`, next: "", t: t.day, lastRun: t.day.last_at }] : []),
      ];
  const bots = [...new Set([...BOT_ORDER, ...rows.map((r) => r.bot)])].filter((b) => rows.some((r) => r.bot === b));
  const rule = t.portfolio;
  const ruleValue = rule.bankroll + rule.total_pnl;
  return (
    <>
    <p className="tr-note">{rows.length} independent paper bots, {money(t.trader.limits.bankroll)} each. Each researches our corpus, forms its own probabilities and trades. A bot is one way of reasoning; its desks run it on different cadences and horizons. Click a desk for its full positions and trades.</p>
    <div className="tr-books" role="group" aria-label="Bots">
      <div className="tr-row tr-rowhead" aria-hidden="true">
        <span>Desk</span><span className="n">Value</span><span>Holding</span><span className="n">Runs</span>
      </div>
      {bots.map((b) => {
        const members = rows.filter((r) => r.bot === b);
        return (
        <section key={b} className="tr-bot" data-bot={b} aria-label={members[0].botName}>
          <header className="tr-bot-h">
            <b>{members[0].botName}</b>
            <span className="tr-bot-n">{members.length} desk{members.length === 1 ? "" : "s"}</span>
            {BOT_ABOUT[b] && <span className="tr-bot-about">{BOT_ABOUT[b]}</span>}
          </header>
          {members.map((r) => {
            const x = strategies.find((q) => q.id === r.id);
            return (
              <BookRow key={r.id} row={r} min={min}>
                {x && (
                  <>
                    <Sec title="Latest run: what it browsed and why">
                      {x.runs[0]?.must_trade ? <p className="tr-note">Fill check for this run: {x.runs[0].must_trade}.</p> : null}
                      <DayRuns rows={x.runs.slice(0, 1)} />
                    </Sec>
                    <Sec title="What it wished we knew"><Wishes rows={x.wishes.slice(0, 3)} /></Sec>
                  </>
                )}
              </BookRow>
            );
          })}
        </section>
        );
      })}
      <details className="tr-fold">
        <summary>Retired: fixed rule (history only)</summary>
        <details className="tr-book tr-b-rule">
          <summary className="tr-row">
            <Cell label="Desk" className="tr-name">
              <i className="tr-sw tr-bg-rule" aria-hidden="true" /> <b>Fixed rule</b>
              <span className="tr-sub">Edge rule on the desk forecast</span>
            </Cell>
            <Cell label="Value" className="n">
              {money(ruleValue)}
              <span className={`tr-sub ${tone(rule.total_pnl)}`}>{usd(rule.total_pnl)} ({rule.total_pnl >= 0 ? "+" : ""}{((rule.total_pnl / rule.bankroll) * 100).toFixed(1)}%)</span>
            </Cell>
            <Cell label="Holding"><Holding held={t.open_positions.map((p) => ({ side: p.side, question: p.question, stake: p.stake, pnl: p.pnl }))} note={`${rule.open} open, history only`} /></Cell>
            <Cell label="Runs" className="n"><Runs last="" next="retired" /></Cell>
          </summary>
          <div className="tr-detail">
            <p className="tr-note">Retired: it needed a shared forecast, so it opens nothing now. {rule.open + rule.settled} trades in all.</p>
            <Sec title="Open positions"><OpenPositions rows={t.open_positions} /></Sec>
          </div>
          <div className="tr-end-band" aria-hidden="true">end of Fixed rule · retired</div>
        </details>
      </details>
    </div>
    </>
  );
}
