import Link from "next/link";

import { Delta, Spark } from "@/components/vl/primitives";
import { fmtPct, type Cell, type DayChart, type Mover } from "@/lib/glance";
import { assetUrl } from "@/lib/assets";

import "./home.css";

// "At a glance": the day's key movers as a hairline-ruled band of cells, each a big tabular numeral, its change against the
// series' own normal, and a hairline of the recent past. Each cell links to where the number lives. Beside it (or below, on a
// phone) sits the chart of the day. Data: lib/glance.ts.

export function GlanceBand({ cells }: { cells: Cell[] }) {
  if (cells.length === 0) return null;
  return (
    <section className="hm-glance" aria-label="At a glance">
      <p className="hm-sub">
        <span>At a glance</span>
        <span className="hm-sub-note">our own counts, against their usual</span>
      </p>
      <ul className="hm-cells">
        {cells.map((c) => (
          <li key={c.key}>
            <Link href={c.href} className="hm-cell" title={c.foot}>
              <span className="vl-label hm-cell-label">{c.label}</span>
              <span className="hm-cell-main">
                <span className="hm-cell-num">{c.value}</span>
                <span className="hm-cell-unit">{c.unit}</span>
              </span>
              <span className="hm-cell-foot">
                {c.delta ? <Delta text={c.delta.text} sign={c.delta.sign} /> : <span className="vl-delta">{c.foot}</span>}
                <Spark values={c.spark} label={`${c.label}: ${c.foot}`} />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The day's best drawn visual, small, with a link to its section; else a table of the instruments that moved most. */
export function ChartOfDay({ chart, movers }: { chart: DayChart | null; movers: Mover[] }) {
  if (!chart && movers.length === 0) return null;
  if (chart) {
    const v = chart.visual;
    const src = v.preview || v.asset;
    return (
      <section className="hm-chart" aria-label="Chart of the day">
        <p className="hm-sub">
          <span>Chart of the day</span>
        </p>
        <Link href={`/geopolitics#${chart.anchor}`} className="hm-chart-link">
          <span className="hm-chart-frame">
            <img src={assetUrl(src)} alt={v.title} loading="lazy" />
          </span>
          <span className="hm-chart-title">{v.title}</span>
          <span className="vl-label">{chart.theater.name}</span>
        </Link>
      </section>
    );
  }
  return (
    <section className="hm-chart" aria-label="Biggest movers">
      <p className="hm-sub">
        <span>Biggest movers</span>
        <span className="hm-sub-note">instruments, own step</span>
      </p>
      <ul className="hm-movers">
        {movers.map((m) => (
          <li key={m.id}>
            <Link href={m.href} className="hm-mover" title={`${m.name}: ${m.stepLabel}`}>
              <span className="hm-mover-name">{m.name}</span>
              <Delta text={fmtPct(m.pct)} sign={m.pct} />
              <Spark values={m.spark} label={`${m.name}: recent readings`} />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
