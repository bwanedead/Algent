import { BAND_LABEL, bandAt, deltaClass, fmtDelta, type Band, type Pulse } from "@/lib/intel";

import PulseSpectrum from "./PulseSpectrum";

// THE Pulse component. Used on /intel, /pulses, in daily reports and in briefs. A Pulse never links
// away: it expands in place (native <details>, no client JS).

/** What the collapsed card needs. Daily reports carry only this much; the full Pulse is looked up. */
export type PulseBase = { id: string; name: string; position: number | null; band: Band; d24: number | null; d7: number | null };

export const baseOf = (p: Pulse): PulseBase => ({ id: p.id, name: p.name, position: p.position, band: p.band, d24: null, d7: p.velocity_7d });

export function BandChip({ band }: { band: Band }) {
  return <span className={`intel-chip intel-band-${band}`}>{BAND_LABEL[band]}</span>;
}

const MAX_POINTS = 60;
const day = (at: string) => at.slice(0, 10);

/** History line with its dates. Time-scaled when every date parses, evenly spaced otherwise. */
function PulseHistory({ history, band, name }: { history: Pulse["history"]; band: Band; name: string }) {
  const pts = history.slice(-MAX_POINTS);
  if (pts.length === 0) return null;
  const W = 320;
  const H = 64;
  const padX = 6;
  const padY = 5;
  const y = (v: number) => padY + (1 - Math.min(100, Math.max(0, v)) / 100) * (H - padY * 2);
  const times = pts.map((p) => Date.parse(p.at));
  const timed = pts.length > 1 && times.every((t) => Number.isFinite(t)) && times[times.length - 1] > times[0];
  const x = (i: number) => {
    if (pts.length === 1) return W - padX;
    const f = timed ? (times[i] - times[0]) / (times[times.length - 1] - times[0]) : i / (pts.length - 1);
    return padX + f * (W - padX * 2);
  };
  const xy = pts.map((p, i) => [x(i), y(p.position)] as const);
  const d = xy.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" ");
  const last = xy[xy.length - 1];
  return (
    <figure className={`pulse-hist intel-band-${band}`}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${name}: ${pts.length} reading${pts.length === 1 ? "" : "s"}, ${day(pts[0].at)} to ${day(pts[pts.length - 1].at)}`}>
        {[25, 50, 75].map((g) => (
          <line key={g} x1={padX} x2={W - padX} y1={y(g)} y2={y(g)} className="pulse-hist-grid" />
        ))}
        {pts.length > 1 && <path d={d} className="pulse-hist-line" />}
        {xy.slice(0, -1).map(([px, py], i) => (
          <circle key={i} cx={px} cy={py} r={2} className="pulse-hist-dot">
            <title>{`${day(pts[i].at)}: ${Math.round(pts[i].position)}`}</title>
          </circle>
        ))}
        <circle cx={last[0]} cy={last[1]} r={3.5} className="pulse-hist-dot pulse-hist-last">
          <title>{`${day(pts[pts.length - 1].at)}: ${Math.round(pts[pts.length - 1].position)}`}</title>
        </circle>
      </svg>
      <figcaption className="intel-micro">
        <span>{day(pts[0].at)}</span>
        <span>
          {pts.length} reading{pts.length === 1 ? "" : "s"}
        </span>
        <span>{pts.length > 1 ? day(pts[pts.length - 1].at) : ""}</span>
      </figcaption>
    </figure>
  );
}

export default function PulseCard({
  base,
  full,
  anchor = false,
  reportDate,
}: {
  base: PulseBase;
  /** The full Pulse from the latest snapshot (question, ends, history, reasoning); null when unknown. */
  full: Pulse | null;
  /** Render an id="pulse-<id>" anchor (only where a page shows each Pulse once). */
  anchor?: boolean;
  /** Set on daily reports: base is the report-time reading, and "Now" is shown when it has moved. */
  reportDate?: string;
}) {
  const assessed = base.position !== null;
  const now = full && full.position !== null ? full.position : null;
  const moved = reportDate !== undefined && assessed && now !== null && Math.round(now) !== Math.round(base.position as number);
  const hasDeltas = base.d24 !== null || base.d7 !== null;
  const hasDetail = full !== null;
  const conf = full?.confidence ?? "";

  return (
    <details id={anchor ? `pulse-${base.id}` : undefined} className={`pulse-card intel-band-${base.band}`}>
      <summary>
        <span className="pulse-card-name">{base.name}</span>
        <span className="pulse-card-main">
          <span className={assessed ? "intel-num" : "intel-num intel-muted"}>{assessed ? Math.round(base.position as number) : "—"}</span>
          <BandChip band={base.band} />
        </span>
        <PulseSpectrum position={base.position} variant="compact" />
        {hasDeltas && (
          <span className="pulse-card-deltas">
            {base.d24 !== null && (
              <span className={`intel-delta intel-delta-${deltaClass(base.d24)}`} title="Change over 24 hours">
                {fmtDelta(base.d24)}
                <span className="intel-micro"> 24h</span>
              </span>
            )}
            {base.d7 !== null && (
              <span className={`intel-delta intel-delta-${deltaClass(base.d7)}`} title="Change over 7 days">
                {fmtDelta(base.d7)}
                <span className="intel-micro"> 7d</span>
              </span>
            )}
          </span>
        )}
      </summary>
      <div className="pulse-card-body">
        {full?.question && <p className="pulse-q">{full.question}</p>}

        <div className="pulse-spec-wrap">
          <PulseSpectrum position={base.position} variant="full" />
          {full && (full.low_end || full.high_end) && (
            <div className="pulse-ends">
              <p>
                <span className="intel-micro">0 · calm</span>
                {full.low_end || "—"}
              </p>
              <p className="pulse-end-hi">
                <span className="intel-micro">100 · extreme</span>
                {full.high_end || "—"}
              </p>
            </div>
          )}
        </div>

        {reportDate !== undefined && assessed && (
          <p className="pulse-now">
            <span className="intel-micro">Reading in this report</span> <b className="intel-tab">{Math.round(base.position as number)}</b>
            {moved && (
              <>
                {" · "}
                <span className="intel-micro">Now</span> <b className="intel-tab">{Math.round(now as number)}</b> <BandChip band={bandAt(now)} />
              </>
            )}
          </p>
        )}

        {full && full.history.length > 0 && <PulseHistory history={full.history} band={base.band} name={base.name} />}

        {full?.rationale ? <p className="pulse-rationale">{full.rationale}</p> : !hasDetail ? <p className="intel-muted">No further detail is available for this Pulse yet.</p> : <p className="intel-muted">No reading yet.</p>}

        {full && (full.last_assessed || conf || full.evidence_through || full.velocity_30d !== null) && (
          <p className="intel-micro pulse-foot">
            {full.last_assessed && <>Assessed {full.last_assessed.slice(0, 10)}</>}
            {conf && <> · {conf} confidence</>}
            {full.evidence_through && <> · evidence through {full.evidence_through.slice(0, 10)}</>}
            {full.velocity_30d !== null && <> · 30d {fmtDelta(full.velocity_30d)}</>}
          </p>
        )}
      </div>
    </details>
  );
}
