import type { EscalationPoint } from "@/lib/dossier";
import { DIRECTION, dayLabel, escalationShift, isoDay } from "@/lib/dossier-view";
import type { Direction, Pace } from "@/lib/intel";

// The escalation trajectory: one mark per report, drawn on a three-level scale (rising high, steady
// middle, easing low) so the eye reads the arc as a shape before it reads a word. Glyph + level +
// colour all say the same thing; mark size says pace. Two variants share one grammar: the full strip on
// a dossier and the mini strip of the index, where every theater is drawn on the SAME day axis.

const PACE_SIZE: Record<Pace, number> = { fast: 1, gradual: 0.78, flat: 0.62 };

function Mark({ dir, pace, x, y, s }: { dir: Direction; pace: Pace; x: number; y: number; s: number }) {
  const r = s * PACE_SIZE[pace];
  const cls = `th-m th-m-${dir}`;
  if (dir === "rising") return <polygon className={cls} points={`${x},${y - r} ${x + r * 0.95},${y + r * 0.8} ${x - r * 0.95},${y + r * 0.8}`} />;
  if (dir === "easing") return <polygon className={cls} points={`${x},${y + r} ${x + r * 0.95},${y - r * 0.8} ${x - r * 0.95},${y - r * 0.8}`} />;
  if (dir === "steady") return <polygon className={cls} points={`${x},${y - r * 0.85} ${x + r * 0.85},${y} ${x},${y + r * 0.85} ${x - r * 0.85},${y}`} />;
  return <circle className={cls} cx={x} cy={y} r={r * 0.75} />;
}

const level = (dir: Direction, lo: number, mid: number, hi: number) => (dir === "rising" ? lo : dir === "easing" ? hi : mid);

/** The full strip for a dossier: last reports, newest at the right, with what the run is and since when. */
export function EscalationTrack({ history, name }: { history: EscalationPoint[]; name: string }) {
  if (history.length === 0) return null;
  const MAX = 28;
  const cells = history.slice(-MAX);
  const CW = 34;
  const H = 66;
  const W = cells.length * CW;
  const xy = cells.map((c, i) => ({ c, x: i * CW + CW / 2, y: level(c.direction, 15, 33, 51) }));
  const shift = escalationShift(history);
  const first = cells[0].date;
  const last = cells[cells.length - 1].date;
  return (
    <figure className="th-track">
      <div style={{ maxWidth: W }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={`${name}: escalation at each of ${history.length} reports, ${dayLabel(history[0].date)} to ${dayLabel(history[history.length - 1].date)}${
            shift ? `; now ${DIRECTION[shift.direction].word}${shift.first ? "" : ` since ${dayLabel(shift.since)}`}` : ""
          }`}
          className="th-track-svg"
        >
          {[15, 33, 51].map((y) => (
            <line key={y} x1={0} x2={W} y1={y} y2={y} className="th-track-grid" />
          ))}
          {xy.length > 1 && <polyline className="th-track-line" points={xy.map((p) => `${p.x},${p.y}`).join(" ")} />}
          {xy.map((p, i) => (
            <g key={i}>
              <title>{`${dayLabel(p.c.date)}: ${DIRECTION[p.c.direction].word}, ${p.c.pace} pace`}</title>
              <Mark dir={p.c.direction} pace={p.c.pace} x={p.x} y={p.y} s={10.5} />
              {i === xy.length - 1 && <circle className="th-track-now" cx={p.x} cy={p.y} r={15} />}
            </g>
          ))}
        </svg>
        <div className="th-track-axis">
          <span>{dayLabel(first)}</span>
          <span>{history.length > cells.length ? `last ${cells.length} of ${history.length} reports` : `${history.length} report${history.length === 1 ? "" : "s"}`}</span>
          <span>{dayLabel(last)}</span>
        </div>
      </div>
      <figcaption className="th-key">
        <span aria-hidden="true">▲</span> rising <span aria-hidden="true">◆</span> steady <span aria-hidden="true">▼</span> easing · bigger mark = faster
      </figcaption>
    </figure>
  );
}

/** The index's mini strip. `days` is the shared, ascending day axis; a theater marks only the days it was reported. */
export function EscalationMini({ history, days, name }: { history: EscalationPoint[]; days: string[]; name: string }) {
  const CW = 10;
  const H = 24;
  const W = Math.max(1, days.length) * CW;
  const at = new Map(days.map((d, i) => [d, i]));
  const pts = history
    .map((c) => ({ c, i: at.get(isoDay(c.date)) }))
    .filter((p): p is { c: EscalationPoint; i: number } => p.i !== undefined)
    .map((p) => ({ c: p.c, x: p.i * CW + CW / 2, y: level(p.c.direction, 6, 12, 18) }));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="th-mini" role="img" aria-label={`${name}: escalation per report over the last ${days.length} days`}>
      <line x1={0} x2={W} y1={12} y2={12} className="th-track-grid" />
      {pts.length > 1 && <polyline className="th-track-line" points={pts.map((p) => `${p.x},${p.y}`).join(" ")} />}
      {pts.map((p, i) => (
        <g key={i}>
          <title>{`${dayLabel(p.c.date)}: ${DIRECTION[p.c.direction].word}`}</title>
          <Mark dir={p.c.direction} pace={p.c.pace} x={p.x} y={p.y} s={4.2} />
        </g>
      ))}
    </svg>
  );
}
