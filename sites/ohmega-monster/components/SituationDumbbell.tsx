import { bandAt } from "@/lib/band";

// A Pulse move as a dumbbell on a shared 0–100 axis: hollow dot = where it was, filled dot = where
// it is (coloured by the band it is now in), arrow = which way. Position on a common scale is the
// most accurately judged encoding, so every row uses the same x scale and rows compare by eye.
// Pure SVG with percentage x-coordinates: it fills its container and needs no measuring.

const clamp = (v: number) => Math.min(100, Math.max(0, v));
const at = (v: number) => `${clamp(v)}%`;

export function Dumbbell({ from, to, label, compact = false }: { from: number; to: number; label: string; compact?: boolean }) {
  const H = compact ? 16 : 24;
  const mid = H / 2;
  const span = Math.abs(to - from);
  const right = to >= from;
  return (
    <svg className={`sit-db intel-band-${bandAt(to)}`} width="100%" height={H} role="img" aria-label={label}>
      <title>{label}</title>
      {[25, 50, 75].map((g) => (
        <line key={g} x1={at(g)} x2={at(g)} y1={0} y2={H} className="sit-db-tick" />
      ))}
      <line x1="0%" x2="100%" y1={mid} y2={mid} className="sit-db-base" />
      {span > 0 && <line x1={at(from)} x2={at(to)} y1={mid} y2={mid} className="sit-db-link" />}
      {span >= 6 && (
        // Nested viewport anchored at the filled dot (percent x), so the arrowhead can be drawn in plain pixels.
        <svg x={at(to)} y={mid} width="1" height="1" className="sit-db-arrowbox">
          <path d={right ? "M-6,0 L-12,-3.5 L-12,3.5 Z" : "M6,0 L12,-3.5 L12,3.5 Z"} className="sit-db-arrow" />
        </svg>
      )}
      {span > 0 && <circle cx={at(from)} cy={mid} r={compact ? 2.5 : 3.5} className="sit-db-from" />}
      <circle cx={at(to)} cy={mid} r={compact ? 3.5 : 5} className="sit-db-to" />
    </svg>
  );
}

/** The scale, once: the four bands across 0–100 (band colour = severity, nothing else). */
export function DumbbellAxis() {
  return (
    <div className="sit-axis" aria-hidden="true">
      <span className="intel-band-calm">Calm</span>
      <span className="intel-band-elevated">Elevated</span>
      <span className="intel-band-severe">Severe</span>
      <span className="intel-band-critical">Critical</span>
    </div>
  );
}
