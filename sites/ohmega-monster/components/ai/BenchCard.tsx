import { daysSince, fmtDate, fmtDelta, fmtScore, type Bench } from "@/lib/ai-benchmarks";
import { labColor } from "@/lib/ai-labs";

import { FrontierChart } from "./AiCharts";

// One benchmark as a small multiple: the leader as a numeral, the frontier over time, and one line of what it means (how close to the ceiling, how far
// it moved this year). "As of" is the date of the newest measured result, so a reader sees how fresh each picture is; a stale source or a benchmark nobody
// has run for months says so in words, in the same place.

const OLD_DAYS = 180;

export default function BenchCard({ bench, sourceStale }: { bench: Bench; sourceStale: boolean }) {
  const best = bench.best;
  const age = bench.as_of ? daysSince(bench.as_of) : 0;
  const notes: string[] = [];
  if (bench.saturation !== null) notes.push(`${Math.round(bench.saturation * 100)}% of the ceiling`);
  if (bench.velocity !== null) notes.push(`${fmtDelta(bench.unit, bench.velocity)} in 12 months`);
  if (bench.open_lag_days !== null && bench.open_lag_days > 30) notes.push(`open weights ~${Math.round(bench.open_lag_days / 30)} months behind`);
  return (
    <article className="ai-card">
      <header className="ai-card-h">
        <h3 className="ai-card-t">
          <a href={bench.source_url || undefined}>{bench.name}</a>
        </h3>
        <span className={`ai-asof${sourceStale || age > OLD_DAYS ? " is-stale" : ""}`} title="Date of the newest measured result for this benchmark">
          {bench.as_of ? `as of ${fmtDate(bench.as_of)}` : "no results"}
        </span>
      </header>
      {best && (
        <p className="ai-lead">
          <span className="ai-num">{fmtScore(bench.unit, best.s)}</span>
          <span className="ai-lead-m">
            <i className="ai-chip" style={{ background: labColor(best.l) }} aria-hidden="true" /> {best.m}
          </span>
        </p>
      )}
      {bench.frontier.length > 0 ? (
        <FrontierChart bench={bench} />
      ) : (
        <p className="ai-empty">{bench.n_models} model{bench.n_models === 1 ? "" : "s"} measured: too few for a trend.</p>
      )}
      {notes.length > 0 && <p className="ai-notes">{notes.join(" · ")}</p>}
      {bench.claimed.length > 0 && (
        <p className="ai-notes ai-claimnote">
          <span className="ai-diamond" aria-hidden="true">◇</span> {bench.claimed.length} lab claim{bench.claimed.length === 1 ? "" : "s"}, not independently measured
        </p>
      )}
      {sourceStale && <p className="ai-notes is-stale">Its source is not updating: read this as the last known state.</p>}
      {!sourceStale && age > OLD_DAYS && <p className="ai-notes is-stale">No new results in {age} days.</p>}
    </article>
  );
}
