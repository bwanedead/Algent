import Link from "next/link";

import { ActorFlag, ScaleBar } from "@/components/actors/ActorParts";
import Popover from "@/components/Popover";
import { actorIds } from "@/lib/actors";
import type { NumbersActor, TheaterNumbers } from "@/lib/daily";

import ActorDetail, { showMetric } from "./ActorDetail";
import Sparkline from "./Sparkline";
import TrackerTile from "./TrackerTile";
import "./numbers.css";

// A theater's "Numbers" panel, in order: WHO the actors are by size (four bars each, one scale per column) and by
// balance sheet (debt, budget, current account, reserves), each cell with its value and a ten-year trend line;
// then the dated physical flows and policy rates sensing tied to the theater. These are ANNUAL statistics with
// their own years, not live data (the note says so; the tap-through shows each year and source). Details open in
// the shared Popover. Older records carry no numbers and render nothing.

const TRACKERS_SHOWN = 3;
type Col = { id: string; label: string; signed?: boolean };
const SIZE: Col[] = [
  { id: "gdp", label: "GDP" },
  { id: "gdp_pc", label: "Per person" },
  { id: "population", label: "People" },
  { id: "milex", label: "Arms $" },
];
const BOOKS: Col[] = [
  { id: "gov_debt_imf", label: "Debt/GDP" },
  { id: "fiscal_balance_imf", label: "Budget", signed: true },
  { id: "current_account_imf", label: "Curr. acct", signed: true },
  { id: "reserves_usd", label: "Reserves" },
];

/** A bar around zero: negative to the left, positive to the right, on one scale for the whole column. */
function SignedBar({ value, max, label }: { value: number; max: number; label: string }) {
  const half = max > 0 ? Math.min(50, (Math.abs(value) / max) * 50) : 0;
  return (
    <span className="num-div" role="img" aria-label={label}>
      <span className="num-div-fill" style={{ left: value < 0 ? `${50 - half}%` : "50%", width: `${Math.max(1.5, half)}%` }} />
    </span>
  );
}

function MetricTable({ title, cols, actors, asOfYear, known }: { title: string; cols: Col[]; actors: NumbersActor[]; asOfYear: number; known: Set<string> }) {
  const present = actors.filter((a) => cols.some((c) => a.metrics[c.id]));
  if (present.length === 0) return null;
  const max = (c: Col) => Math.max(0, ...present.map((a) => Math.abs(a.metrics[c.id]?.value ?? 0)));
  return (
    <div className="num-table">
      <p className="geo-micro">{title}</p>
      <div className="num-arow num-ahead" aria-hidden="true">
        <span />
        {cols.map((c) => (
          <span key={c.id}>{c.label}</span>
        ))}
      </div>
      <ul className="num-alist">
        {present.map((a) => (
          <li key={a.iso2}>
            <Popover
              label={`${a.name}: leaders, structure and trade`}
              triggerClassName="num-arow num-actor"
              wide
              trigger={
                <>
                  <span className="num-aname">
                    <ActorFlag iso2={a.iso2} name={a.name} /> {a.name}
                  </span>
                  {cols.map((c) => {
                    const m = a.metrics[c.id];
                    if (!m) {
                      return (
                        <span key={c.id} className="num-acell num-none">
                          —
                        </span>
                      );
                    }
                    const label = `${a.name} ${c.label}: ${showMetric(m)} (${m.year})`;
                    return (
                      <span key={c.id} className="num-acell" title={label}>
                        <span className="num-acv">{showMetric(m)}</span>
                        {c.signed ? <SignedBar value={m.value} max={max(c)} label={label} /> : <ScaleBar value={Math.abs(m.value)} max={max(c)} label={label} />}
                        {m.trend.length >= 3 && <Sparkline values={m.trend.map((p) => p[1])} label={`${a.name} ${c.label}, ${m.trend[0][0]} to ${m.trend[m.trend.length - 1][0]}`} />}
                      </span>
                    );
                  })}
                </>
              }
            >
              <ActorDetail a={a} linked={known.has(a.iso2)} asOfYear={asOfYear} />
            </Popover>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function TheaterNumbersPanel({ numbers, name }: { numbers: TheaterNumbers | null; name: string }) {
  if (!numbers || (numbers.trackers.length === 0 && numbers.actors.length === 0)) return null;
  const { trackers, actors } = numbers;
  const known = new Set(actorIds());
  const asOfYear = Number(numbers.as_of.slice(0, 4)) || new Date().getUTCFullYear();
  const unusual = trackers.filter((t) => t.unusual).length;
  const rest = trackers.slice(TRACKERS_SHOWN);
  return (
    <section className="num-panel" aria-label={`Numbers and power: ${name}`}>
      {actors.length > 0 && (
        <div className="num-actors">
          <MetricTable title="Who they are · size" cols={SIZE} actors={actors} asOfYear={asOfYear} known={known} />
          <MetricTable title="Balance sheet · debt, budget, current account, reserves" cols={BOOKS} actors={actors} asOfYear={asOfYear} known={known} />
          <p className="num-note">
            Annual statistics: latest year on record for each figure (IMF figures for this year are estimates), bars on one scale per column, line = the last ten years. Tap an actor for every year, rank, energy, ranked trade and sources.{" "}
            <Link href="/intel/actors">All actors →</Link>
          </p>
        </div>
      )}
      {trackers.length > 0 && (
        <div className="num-trackers">
          <p className="geo-micro">
            Flows and rates, dated
            {unusual > 0 && <span className="num-hot"> · {unusual} outside its normal</span>}
          </p>
          <ul className="num-grid">
            {trackers.slice(0, TRACKERS_SHOWN).map((t) => (
              <li key={t.id}>
                <TrackerTile t={t} />
              </li>
            ))}
          </ul>
          {rest.length > 0 && (
            <details className="num-more">
              <summary>
                {rest.length} more reading{rest.length === 1 ? "" : "s"}
              </summary>
              <ul className="num-grid">
                {rest.map((t) => (
                  <li key={t.id}>
                    <TrackerTile t={t} />
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  );
}
