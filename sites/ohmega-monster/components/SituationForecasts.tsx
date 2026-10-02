import Link from "next/link";
import type { CSSProperties } from "react";

import { buildTimeline, fmtShort, type ForecastPin, type ForecastsView, type TimelinePin } from "@/lib/situation";

import { ProbBar } from "./IntelViz";
import Popover from "./Popover";
import { NewDot } from "./SituationVisit";
import SituationRecord from "./SituationRecord";

// FORECASTS: what resolves soon, as a timeline (when), each call a marker sized and labelled by its
// probability (how sure). Detail — the statement, the basis, what would make it yes or no — waits
// in the shared popover. The track record sits below it (SituationRecord).

const LANE = 36;
const size = (p: number) => Math.round(20 + (p / 100) * 12);

function ForecastDetail({ f }: { f: ForecastPin }) {
  return (
    <div className="sit-pop">
      <p className="sit-pop-prob">
        <b className="intel-num">{f.probability}%</b> <span className="intel-micro">chance{f.horizon ? ` · by ${f.horizon}` : ""}</span>
      </p>
      <ProbBar value={f.probability} />
      <p className="sit-pop-st">{f.statement}</p>
      {f.theater && <p className="intel-micro">{f.theater}</p>}
      {f.basis && (
        <>
          <h4 className="intel-micro sit-pop-h">Why</h4>
          <p className="sit-pop-p">{f.basis}</p>
        </>
      )}
      {(f.yes || f.no) && (
        <dl className="sit-pop-cond">
          {f.yes && (
            <div>
              <dt className="intel-micro">Yes if</dt>
              <dd>{f.yes}</dd>
            </div>
          )}
          {f.no && (
            <div>
              <dt className="intel-micro">No if</dt>
              <dd>{f.no}</dd>
            </div>
          )}
        </dl>
      )}
      {f.briefUrl && (
        <p className="sit-pop-p">
          <Link href={f.briefUrl}>Read the Brief →</Link>
        </p>
      )}
    </div>
  );
}

function Pin({ f, lanes }: { f: TimelinePin; lanes: number }) {
  const d = size(f.probability);
  // No transform on this wrapper (it would become the containing block of the fixed popover): the
  // marker is centred on its date with a negative margin instead.
  const style = { left: `${f.pos}%`, top: f.lane * LANE, width: d, height: d, marginLeft: -d / 2, "--stem": `${(lanes - f.lane) * LANE + 2 - d}px` } as CSSProperties;
  return (
    <span className="sit-pin-wrap" style={style}>
      <Popover
        label={`${f.probability}% · by ${f.horizon}`}
        triggerClassName="sit-pin"
        trigger={
          <>
            <span aria-hidden="true">{f.probability}</span>
            <span className="intel-sr">
              {f.probability}% chance by {f.horizon}: {f.statement}
            </span>
            <NewDot at={f.madeAt} />
          </>
        }
      >
        <ForecastDetail f={f} />
      </Popover>
    </span>
  );
}

function AllOpen({ open }: { open: ForecastPin[] }) {
  return (
    <Popover label={`All ${open.length} open forecasts`} triggerClassName="sit-linkbtn" wide trigger={<>All {open.length} open →</>}>
      <ol className="sit-all">
        {open.map((f) => (
          <li key={f.id}>
            <b className="intel-tab">{f.probability}%</b>
            <span>
              {f.statement}
              <span className="intel-micro sit-all-meta">
                {f.horizon ? `by ${f.horizon}` : "no date"}
                {f.briefUrl && (
                  <>
                    {" · "}
                    <Link href={f.briefUrl}>Brief</Link>
                  </>
                )}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </Popover>
  );
}

export default function SituationForecasts({ forecasts }: { forecasts: ForecastsView }) {
  const { open, resolved, scorecard, asOfMs } = forecasts;
  const tl = buildTimeline(open, asOfMs);
  const next = open.find((f) => f.horizonMs !== null);
  const plotH = tl.lanes * LANE;
  return (
    <section className="sit-sec" aria-labelledby="sit-fc-h">
      <div className="sit-head">
        <h2 id="sit-fc-h">
          {open.length === 0
            ? "No forecasts are open"
            : `${open.length} ${open.length === 1 ? "forecast" : "forecasts"} open${next && next.horizonMs !== null ? ` — next resolves ${fmtShort(next.horizonMs)}` : ""}`}
        </h2>
        {open.length > 0 && (
          <div className="sit-ctl">
            {tl.later > 0 && <span className="intel-micro">+{tl.later} later than shown</span>}
            <AllOpen open={open} />
          </div>
        )}
      </div>

      {tl.pins.length > 0 && (
        <div className="sit-tl" role="group" aria-label={`Open forecasts by date, next ${tl.days} days; marker size and number are the probability`}>
          <div className="sit-tl-plot" style={{ height: plotH + 30 }}>
            <span className="sit-tl-line" style={{ top: plotH + 2 }} />
            {tl.ticks.map((t) => (
              <span key={t.label} className="sit-tl-tick" style={{ left: `${t.pos}%`, top: plotH + 2 }}>
                <span className="sit-tl-lab">{t.label}</span>
              </span>
            ))}
            {tl.pins.map((f) => (
              <Pin key={f.id} f={f} lanes={tl.lanes} />
            ))}
          </div>
        </div>
      )}

      <SituationRecord resolved={resolved} scorecard={scorecard} />
    </section>
  );
}
