"use client";

import Link from "next/link";

import { Delta } from "@/components/vl/primitives";

import type { PanelProps } from "../types";

const W = 300;
const H = 84;
const usd = (n: number): string => `$${Math.round(n).toLocaleString("en-US")}`;
const signedUsd = (n: number): string => `${n > 0 ? "+" : n < 0 ? "−" : ""}$${Math.abs(Math.round(n)).toLocaleString("en-US")}`;

/** The paper trader's equity (amber) against the flat bankroll (grey, doing nothing). Paper only: no money is staked. */
export default function TraderPanel({ ctx }: PanelProps) {
  const t = ctx.data.trader;
  if (!t) return <p className="hud-none">The paper trader has not started yet.</p>;
  const curve = t.curve;
  const all = curve.flatMap((c) => [c.trader, c.flat]);
  const lo = Math.min(...all);
  const span = Math.max(...all) - lo || 1;
  const line = (pick: (c: (typeof curve)[number]) => number) =>
    curve.map((c, i) => `${((i / (curve.length - 1)) * W).toFixed(1)},${(H - 3 - ((pick(c) - lo) / span) * (H - 6)).toFixed(1)}`).join(" ");
  return (
    <>
      <p className="hud-big">
        <span className="hud-big-n">{usd(t.equity)}</span> <Delta text={`${signedUsd(t.pnl)} on ${usd(t.bankroll)}`} sign={t.pnl} />
      </p>
      {curve.length >= 2 && (<svg className="hud-chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`Paper trader equity against the flat bankroll, ${t.curve.length} days`}>
        <polyline className="hud-line-flat" points={line((c) => c.flat)} />
        <polyline className="hud-line-main" points={line((c) => c.trader)} />
      </svg>)}
      <p className="hud-cap">{curve.length >= 2 ? <><span className="hud-key hud-key-main" /> Trader <span className="hud-key hud-key-flat" /> Flat bankroll · {curve[0].day} to {curve[curve.length - 1].day}</> : <>Day one, {curve[0].day}: the curve draws from tomorrow</>}</p>
      {t.positions.length > 0 && (
        <>
          <p className="hud-cap">Open positions ({t.open})</p>
          <ul className="hud-rows hud-table">
            {t.positions.map((p, i) => (
              <li key={`${p.question}-${i}`}>
                <span className="hud-row">
                  <span className="hud-tag">{p.side}</span>
                  {p.url ? <a href={p.url} className="hud-row-text" target="_blank" rel="noopener noreferrer">{p.question}</a> : <span className="hud-row-text">{p.question}</span>}
                  <Delta text={signedUsd(p.pnl)} sign={p.pnl} />
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="hud-foot"><Link href="/intel/track-record">Track record</Link> · paper only, not advice</p>
    </>
  );
}
