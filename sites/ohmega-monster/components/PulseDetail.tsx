// The body of a Pulse popover: what the number means and how it got there. Client-safe (no lib/intel
// runtime import); styled by components/pulse-tile.css plus the shared .pulse-* rules in globals.css.

import { BAND_LABEL, deltaClass, fmtDelta } from "@/lib/band";
import type { WallPulse } from "@/lib/pulse-wall";

import IsoFlags from "./IsoFlags";
import Term from "./Term";
import PulseSpectrum from "./PulseSpectrum";
import "./pulse-tile.css";

const day = (at: string) => at.slice(0, 10);

/**
 * Every reading as a dot on the 0-100 spectrum over time: oldest faint and small, newest bold and large,
 * the latest ringed, a faint line joining them so back-and-forth shows. Band zones sit quietly behind.
 * Time-scaled when every date parses, evenly spaced otherwise. Recency reads on its own; no key.
 */
function History({ p }: { p: WallPulse }) {
  const pts = p.history.slice(-40);
  if (pts.length === 0) return null;
  const W = 320;
  const H = 96;
  const padX = 8;
  const padY = 6;
  const y = (v: number) => padY + (1 - Math.min(100, Math.max(0, v)) / 100) * (H - padY * 2);
  const times = pts.map((h) => Date.parse(h.at));
  const timed = pts.length > 1 && times.every(Number.isFinite) && times[times.length - 1] > times[0];
  const x = (i: number) =>
    pts.length === 1 ? W - padX : padX + (timed ? (times[i] - times[0]) / (times[times.length - 1] - times[0]) : i / (pts.length - 1)) * (W - padX * 2);
  const xy = pts.map((h, i) => [x(i), y(h.position)] as const);
  const d = xy.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" ");
  const last = xy[xy.length - 1];
  const zoneH = (H - padY * 2) / 4;
  return (
    <figure className="pulse-hist">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${p.title}: ${pts.length} readings, ${day(pts[0].at)} to ${day(pts[pts.length - 1].at)}`}>
        {(["critical", "severe", "elevated", "calm"] as const).map((b, i) => (
          <rect key={b} x={0} width={W} y={padY + i * zoneH} height={zoneH} className={`pulse-hist-zone intel-band-${b}`} />
        ))}
        {pts.length > 1 && <path d={d} className="pulse-hist-line" />}
        {xy.map(([px, py], i) => {
          const age = pts.length === 1 ? 1 : i / (pts.length - 1);
          return <circle key={i} cx={px} cy={py} r={1.6 + age * 2.4} className="pulse-hist-pt" style={{ opacity: 0.18 + age * 0.82 }} />;
        })}
        <circle cx={last[0]} cy={last[1]} r={6.5} className="pulse-hist-latest" />
      </svg>
      <figcaption className="intel-micro">
        <span>{day(pts[0].at)}</span>
        <span>{pts.length > 1 ? day(pts[pts.length - 1].at) : ""}</span>
      </figcaption>
    </figure>
  );
}

export default function PulseDetail({
  pulse: p,
  delta,
  period,
}: {
  pulse: WallPulse;
  /** Change over `period` (current minus the baseline). undefined: not shown; null: no baseline that old. */
  delta?: number | null;
  period?: string;
}) {
  const assessed = p.position !== null;
  const from = assessed && delta !== undefined && delta !== null ? (p.position as number) - delta : null;
  return (
    <div className={`pd intel-band-${p.band}`}>
      <div className="pd-head">
        <h2 className="pd-title">
          <IsoFlags codes={p.actors_iso2} link />
          {p.title}
        </h2>
        {p.situation && <span className="intel-micro">{p.situation}</span>}
      </div>
      {p.question && <p className="pulse-q">{p.question}</p>}
      <div className="pulse-spec-wrap">
        <PulseSpectrum position={p.position} variant="full" />
        {(p.low_end || p.high_end) && (
          <div className="pulse-ends">
            <p>
              <span className="intel-micro">0 · calm</span>
              {p.low_end || "—"}
            </p>
            <p className="pulse-end-hi">
              <span className="intel-micro">100 · extreme</span>
              {p.high_end || "—"}
            </p>
          </div>
        )}
      </div>
      <p className="pd-stats">
        <span className={assessed ? "intel-num" : "intel-num intel-muted"}>{assessed ? Math.round(p.position as number) : "—"}</span>
        <span className={`intel-chip intel-band-${p.band}`}>{BAND_LABEL[p.band]}</span>
        {delta !== undefined && (
          <span className={`intel-delta intel-delta-${deltaClass(delta)}`} title={from !== null ? `Was ${Math.round(from)}${period ? ` ${period} ago` : ""}` : "No reading that far back"}>
            {fmtDelta(delta)} {period && <span className="intel-micro">{period}</span>}
          </span>
        )}
      </p>
      <History p={p} />
      {(p.last_assessed || p.confidence) && (
        <p className="intel-micro pd-foot">
          {p.last_assessed && <>Updated {day(p.last_assessed)}</>}
          {p.confidence && <> · {p.confidence} confidence</>}
        </p>
      )}
      {p.rationale && <p className="pd-why">{p.rationale}</p>}
      <p className="intel-micro pd-foot">
        <Term id="pulse" label="a Pulse">
          What is a Pulse?
        </Term>
      </p>
    </div>
  );
}
