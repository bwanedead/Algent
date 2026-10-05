// The body of a Pulse popover: what the number means and how it got there. Client-safe (no lib/intel
// runtime import); styled by components/pulse-tile.css plus the shared .pulse-* rules in globals.css.

import { BAND_LABEL, deltaClass, fmtDelta } from "@/lib/band";
import type { WallPulse } from "@/lib/pulse-wall";

import IsoFlags from "./IsoFlags";
import PulseSpectrum from "./PulseSpectrum";
import "./pulse-tile.css";

const day = (at: string) => at.slice(0, 10);

/** History line with first/last dates. Time-scaled when every date parses, evenly spaced otherwise. */
function History({ p }: { p: WallPulse }) {
  const pts = p.history.slice(-40);
  if (pts.length === 0) return null;
  const W = 320;
  const H = 56;
  const pad = 5;
  const y = (v: number) => pad + (1 - Math.min(100, Math.max(0, v)) / 100) * (H - pad * 2);
  const times = pts.map((h) => Date.parse(h.at));
  const timed = pts.length > 1 && times.every(Number.isFinite) && times[times.length - 1] > times[0];
  const x = (i: number) =>
    pts.length === 1 ? W - pad : pad + (timed ? (times[i] - times[0]) / (times[times.length - 1] - times[0]) : i / (pts.length - 1)) * (W - pad * 2);
  const xy = pts.map((h, i) => [x(i), y(h.position)] as const);
  const d = xy.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" ");
  const last = xy[xy.length - 1];
  return (
    <figure className="pulse-hist">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${p.title}: ${pts.length} readings, ${day(pts[0].at)} to ${day(pts[pts.length - 1].at)}`}>
        {[25, 50, 75].map((g) => (
          <line key={g} x1={pad} x2={W - pad} y1={y(g)} y2={y(g)} className="pulse-hist-grid" />
        ))}
        {pts.length > 1 && <path d={d} className="pulse-hist-line" />}
        <circle cx={last[0]} cy={last[1]} r={3} className="pulse-hist-dot" />
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
          <IsoFlags codes={p.actors_iso2} />
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
    </div>
  );
}
