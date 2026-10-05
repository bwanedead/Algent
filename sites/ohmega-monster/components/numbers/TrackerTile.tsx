import Popover from "@/components/Popover";
import type { Tracker, TrackerHorizon } from "@/lib/daily";
import { shortDay } from "@/lib/daily";

import { arrow, fmtChange, fmtValue, HORIZON_LABEL, PREV_LABEL, REASON, shortName } from "./format";
import Sparkline from "./Sparkline";
import "./numbers.css";

// One measured flow or policy rate as a tile: name, value, change from -> to, shape, and ALWAYS the day the reading
// is for (a ship count is published with a lag and a policy rate changes rarely: neither is a live quote). It opens
// the shared popover. The accent marks "unusual" (outside its own history) and nothing else; arrows show direction
// only, never good or bad.

const ORDER: TrackerHorizon[] = ["prev", "7d", "30d", "1y"];

function Detail({ t }: { t: Tracker }) {
  const lo = t.spark.length > 0 ? Math.min(...t.spark) : null;
  const hi = t.spark.length > 0 ? Math.max(...t.spark) : null;
  return (
    <div className="geo-pd">
      <p className="geo-pd-title">{t.name}</p>
      <p className="geo-pd-big">
        <b>{fmtValue(t.value)}</b> {t.unit} <span className="geo-muted">as of {shortDay(t.as_of)}</span>
      </p>
      {t.age_days > 2 && <p className="num-range">This source publishes with a lag: the latest reading is {t.age_days} days old at the time of this report.</p>}
      <Sparkline values={t.spark} large hot={t.unusual} label={`${shortName(t.name)}: shape of the series, latest ${fmtValue(t.value)} ${t.unit}`} />
      {lo !== null && hi !== null && (
        <p className="num-range">
          <span className="geo-micro">On the chart</span> low {fmtValue(lo)} · high {fmtValue(hi)}
          {t.percentile_1y !== null && <> · now above {Math.round(t.percentile_1y)}% of the past year</>}
        </p>
      )}
      <ul className="num-rows">
        {ORDER.filter((h) => t.changes[h]).map((h) => {
          const c = t.changes[h]!;
          return (
            <li key={h}>
              <span className="geo-muted">{h === "prev" ? `vs ${HORIZON_LABEL.prev} (${shortDay(c.from_period)})` : `vs ${HORIZON_LABEL[h]} ago`}</span>
              <span>
                {fmtValue(c.from)} → <b className="geo-strong">{fmtValue(t.value)}</b>
              </span>
              <span className="num-row-chg">{fmtChange(t, c)}</span>
            </li>
          );
        })}
      </ul>
      {(t.unusual || t.outside) && (
        <p className="num-why">
          {t.unusual && <span className="num-hot">● Unusual: {t.reasons.map((r) => REASON[r] ?? r).join("; ") || "outside its own history"}. </span>}
          {t.outside && <span>Outside everything this series has done in our record.</span>}
        </p>
      )}
      <p className="geo-pd-foot">
        {t.internal || !t.source_url ? (
          <span className="geo-muted">Source: {t.source} (internal reading: shown for context, not a citation)</span>
        ) : (
          <a href={t.source_url} target="_blank" rel="noopener noreferrer">
            Source: {t.source} ↗
          </a>
        )}
      </p>
    </div>
  );
}

export default function TrackerTile({ t }: { t: Tracker }) {
  const name = shortName(t.name);
  const prev = t.changes.prev;
  const week = t.changes["7d"];
  const flag = t.unusual ? "● unusual" : t.outside ? "outside its range" : "";
  return (
    <Popover
      label={`${t.name}: ${fmtValue(t.value)} ${t.unit}`}
      triggerClassName={`num-tile${t.unusual ? " is-hot" : ""}`}
      trigger={
        <>
          <span className="num-name">{name}</span>
          <span className="num-val">
            <b>{fmtValue(t.value)}</b> <small>{t.unit}</small>
          </span>
          <span className="num-chg">
            {prev ? (
              <span title={`${fmtValue(prev.from)} → ${fmtValue(t.value)} since ${prev.from_period}`}>
                {fmtChange(t, prev)} <i>{PREV_LABEL[t.freq]}</i>
              </span>
            ) : (
              <span className="geo-muted">first reading</span>
            )}
            {week && (
              <span title={`${fmtValue(week.from)} → ${fmtValue(t.value)} since ${week.from_period}`}>
                {fmtChange(t, week)} <i>7d</i>
              </span>
            )}
          </span>
          <Sparkline values={t.spark} hot={t.unusual} label={`${name}: shape over the plotted window; ${prev ? `${arrow(t.value - prev.from)} on the previous reading` : "first reading"}`} />
          <span className="num-flag">
            {flag}
            {flag ? " · " : ""}
            {`as of ${shortDay(t.as_of)}`}
          </span>
        </>
      }
    >
      <Detail t={t} />
    </Popover>
  );
}
