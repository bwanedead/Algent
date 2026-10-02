import type { Snapshot } from "@/lib/intel";
import type { ResolvedItem } from "@/lib/situation";

import { CalibrationChart, ProbBar } from "./IntelViz";
import Popover from "./Popover";
import { NewDot } from "./SituationVisit";

// JUST RESOLVED + TRACK RECORD: how well are we calling it. A resolved call shows the probability we
// stated next to what happened, so a 30% call that happened is visibly a miss. The Brier score sits
// on a scale with its landmarks (perfect, coin flip) so the number carries its own meaning.

const OUTCOME = {
  yes: { cls: "sit-chip-yes", label: "Happened" },
  no: { cls: "sit-chip-no", label: "Didn’t happen" },
  void: { cls: "sit-chip-void", label: "Void" },
} as const;

const BRIER_MAX = 0.5; // the axis stops at 0.5: anything worse than a coin flip is simply "far right"

function BrierMeter({ brier }: { brier: number }) {
  const at = `${Math.min(1, Math.max(0, brier / BRIER_MAX)) * 100}%`;
  return (
    <svg className="sit-brier" width="100%" height="38" role="img" aria-label={`Brier score ${brier.toFixed(3)} on a scale from 0, perfect, to 0.25, a coin flip`}>
      <line x1="0%" x2="100%" y1={12} y2={12} className="sit-brier-base" />
      {[0, 50, 100].map((x) => (
        <line key={x} x1={`${x}%`} x2={`${x}%`} y1={7} y2={17} className="sit-brier-tick" />
      ))}
      <line x1="0%" x2={at} y1={12} y2={12} className="sit-brier-fill" />
      <circle cx={at} cy={12} r={5} className="sit-brier-dot" />
      <text x="0%" y={32} textAnchor="start" className="sit-brier-lab">0 · perfect</text>
      <text x="50%" y={32} textAnchor="middle" className="sit-brier-lab">0.25 · coin flip</text>
      <text x="100%" y={32} textAnchor="end" className="sit-brier-lab">0.5</text>
    </svg>
  );
}

function ResolvedDetail({ r }: { r: ResolvedItem }) {
  const o = OUTCOME[r.outcome];
  return (
    <div className="sit-pop">
      <p className="sit-pop-prob">
        <span className={`sit-chip ${o.cls}`}>{o.label}</span>
        {r.against && <span className="intel-micro sit-miss"> Against our call</span>}
      </p>
      <p className="sit-pop-prob">
        <b className="intel-num">{r.probability}%</b> <span className="intel-micro">is what we said{r.resolvedAt ? ` · resolved ${r.resolvedAt.slice(0, 10)}` : ""}</span>
      </p>
      <ProbBar value={r.probability} />
      <p className="sit-pop-st">{r.statement}</p>
      {r.evidence && <p className="sit-pop-p intel-muted">{r.evidence}</p>}
    </div>
  );
}

export default function SituationRecord({ resolved, scorecard }: { resolved: ResolvedItem[]; scorecard: Snapshot["forecasts"]["scorecard"] }) {
  if (scorecard.resolved === 0 && resolved.length === 0) {
    return <p className="intel-note sit-quiet">No forecasts resolved yet — the record starts now.</p>;
  }
  const { brier } = scorecard;
  return (
    <div className="sit-record">
      {resolved.length > 0 && (
        <ul className="sit-res" aria-label="Just resolved">
          {resolved.map((r) => {
            const o = OUTCOME[r.outcome];
            return (
              <li key={r.key}>
                <NewDot at={r.resolvedAt} />
                <Popover
                  label={`${o.label}: ${r.statement.slice(0, 60)}`}
                  triggerClassName="sit-res-btn"
                  wide
                  trigger={
                    <>
                      <span className={`sit-chip ${o.cls}`}>{o.label}</span>
                      <span className="sit-res-p intel-tab" title="The probability we stated">
                        said {r.probability}%
                      </span>
                      <span className="sit-res-st">{r.statement}</span>
                      {r.against && <span className="intel-micro sit-miss">Against our call</span>}
                    </>
                  }
                >
                  <ResolvedDetail r={r} />
                </Popover>
              </li>
            );
          })}
        </ul>
      )}

      {brier !== null && (
        <div className="sit-rec">
          <div className="sit-rec-score">
            <h3 className="sit-sub">
              <b className="intel-num">{brier.toFixed(2)}</b> Brier score over {scorecard.resolved} resolved {scorecard.resolved === 1 ? "forecast" : "forecasts"}
            </h3>
            <BrierMeter brier={brier} />
            <p className="intel-note">0 is perfect, 0.25 is a coin flip — lower is better.</p>
          </div>
          {scorecard.calibration.length > 0 && (
            <figure className="sit-calib">
              <CalibrationChart buckets={scorecard.calibration} />
              <figcaption className="intel-note">When we say 70%, it should happen about 70% of the time: dots on the diagonal mean we are calibrated.</figcaption>
            </figure>
          )}
        </div>
      )}
    </div>
  );
}
