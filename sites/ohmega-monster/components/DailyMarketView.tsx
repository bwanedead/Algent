import Link from "next/link";

import type { MarketView } from "@/lib/daily";

// "Where we disagree with the market": our own forecasts set against Polymarket prices where the gap is large. Attached mechanically by the backend
// (markets/desk.py) AFTER the day's writers finished, so nothing in the report above was written with a market price in view. It is our forecast, labelled
// as such, never advice; the note says so and the link goes to the track record, where it shows who has actually been closer.

const pct = (p: number) => `${Math.round(p * 100)}%`;

export default function DailyMarketView({ view }: { view: MarketView }) {
  return (
    <section className="geo-sweep" aria-label="Where we disagree with the market">
      <h2 className="geo-h2">Where we disagree with the market</h2>
      <ul>
        {view.lines.map((l) => (
          <li key={l.url || l.question} className="geo-sw-item" style={{ gridTemplateColumns: "minmax(0, 1fr)" }}>
            <span className="geo-sw-line">
              {l.url ? (
                <a href={l.url} rel="noopener noreferrer" className="xt">{l.question}</a>
              ) : (
                l.question
              )}{" "}
              <span style={{ fontVariantNumeric: "tabular-nums" }}>
                Our forecast {pct(l.ours)} (made {l.made_at}); the market prices it at {pct(l.market)}.
              </span>
            </span>
          </li>
        ))}
      </ul>
      <p className="geo-micro">
        {view.note}
        {view.page && (
          <>
            {" "}
            <Link href={view.page} className="xt">Track record →</Link>
          </>
        )}
      </p>
    </section>
  );
}
