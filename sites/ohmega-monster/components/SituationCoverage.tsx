import Link from "next/link";

import { COVERAGE_DISPLAY } from "@/lib/intel";
import type { CoverageItem, CoverageView } from "@/lib/situation";

// COVERAGE: which Theaters are taking a bigger share of the world's headlines. Small multiples:
// every Theater is the same shape on the SAME bar scale (the tallest day across the group), so the
// eye learns one chart and reads the differences. Neutral grey on purpose: coverage is not severity.

function Bars({ item, max }: { item: CoverageItem; max: number }) {
  const n = item.counts.length;
  if (n === 0) return <span className="intel-muted">—</span>;
  const slot = 6;
  const W = n * slot;
  const H = 30;
  return (
    <svg className="sit-bars" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`${item.name}: headlines per day, ${item.days[0]} to ${item.days[n - 1]}`}>
      <line x1={0} x2={W} y1={H - 0.5} y2={H - 0.5} className="sit-bars-base" />
      {item.counts.map((c, i) => {
        const h = c > 0 ? Math.max(1.5, (c / max) * (H - 3)) : 0;
        return <rect key={i} x={i * slot} y={H - 1 - h} width={slot - 2} height={h} className={i === n - 1 ? "sit-bar sit-bar-last" : "sit-bar"} />;
      })}
    </svg>
  );
}

function Multiple({ item, max }: { item: CoverageItem; max: number }) {
  const c = COVERAGE_DISPLAY[item.coverage];
  const body = (
    <>
      <span className="sit-cov-name">{item.name}</span>
      <Bars item={item} max={max} />
      <span className="sit-cov-meta">
        <b className="intel-num-sm">{item.share < 10 ? item.share.toFixed(1) : Math.round(item.share)}%</b>
        <span className="intel-micro" title="Share of the world’s headlines about this Theater">of headlines</span>
        <span className="intel-micro sit-cov-tag" title={`Headlines, recent vs prior: ${item.recent} vs ${item.prior}`}>
          <span aria-hidden="true">{c.glyph}</span> {c.label} · {item.recent} vs {item.prior}
        </span>
      </span>
    </>
  );
  return item.href ? (
    <Link href={item.href} className="sit-cov-card" aria-label={`${item.name}: open the ${item.hrefLabel.toLowerCase()}`}>
      {body}
    </Link>
  ) : (
    <div className="sit-cov-card">{body}</div>
  );
}

export default function SituationCoverage({ coverage }: { coverage: CoverageView }) {
  const { gaining, items } = coverage;
  if (items.length === 0) return null;
  const max = Math.max(1, ...items.flatMap((i) => i.counts));
  const n = items.length;
  return (
    <section className="sit-sec" aria-labelledby="sit-cov-h">
      <div className="sit-head">
        <h2 id="sit-cov-h">
          {gaining ? `${n} ${n === 1 ? "Theater is" : "Theaters are"} gaining coverage` : "No Theater is gaining coverage"}
        </h2>
        <span className="intel-micro">{gaining ? "Daily headlines, same scale" : "Most covered, for context · daily headlines, same scale"}</span>
      </div>
      <ul className="sit-cov">
        {items.map((i) => (
          <li key={i.id}>
            <Multiple item={i} max={max} />
          </li>
        ))}
      </ul>
    </section>
  );
}
