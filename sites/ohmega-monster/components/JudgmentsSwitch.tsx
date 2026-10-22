import Link from "next/link";

import "./hubs.css";

// The two views of our forecasting, under one name ("Forecasts") and one shared explanation of "the desk": open forecasts on a timeline
// (/intel/forecasts) and the same calls scored against the world and against market prices (/intel/track-record). Both pages wear
// this header so a reader never meets two forecasting systems with two vocabularies. Server component.
const VIEWS = [
  { id: "open", href: "/intel/forecasts", label: "Open forecasts" },
  { id: "scored", href: "/intel/track-record", label: "Scored against the market" },
] as const;

export default function JudgmentsSwitch({ current }: { current: (typeof VIEWS)[number]["id"] }) {
  return (
    <>
      <nav className="jd-switch" aria-label="Forecasts">
        {VIEWS.map((v) =>
          v.id === current ? (
            <span key={v.id} className="is-on" aria-current="page">{v.label}</span>
          ) : (
            <Link key={v.id} href={v.href}>{v.label}</Link>
          ),
        )}
      </nav>
      <p className="jd-desk">
        &ldquo;The desk&rdquo; is Ohmega&apos;s own forecasting. For each question it writes a probability before the answer is known, blind to any market price, and stores it unchanged.
        Open forecasts are the ones still waiting for an outcome; the scored view marks resolved ones against what happened and against Polymarket&apos;s prices, misses included.
        Paper only: nothing here is financial advice.
      </p>
    </>
  );
}
