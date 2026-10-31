import type { ReactNode } from "react";
import type { Bucket, DiffPoint } from "@/lib/track-record";

// Two plain pictures. Calibration: when we say X%, how often does it happen (on the diagonal = honest; below it = overconfident); our points are filled, the
// market's hollow, area = how many markets. Brier over time: the running average of (our error minus the market's error) in order of resolution; below
// the zero line we are ahead, above it the market was the better forecaster. Server-rendered SVG, no client code.

const S = 260;
const PAD = 30;
const span = S - PAD * 2;
const x = (p: number) => PAD + p * span;
const y = (p: number) => S - PAD - p * span;

export function CalibrationChart({ ours, market }: { ours: Bucket[]; market: Bucket[] }) {
  const r = (n: number) => 3 + Math.min(7, Math.sqrt(n) * 2);
  return (
    <figure className="tr-fig">
      <svg viewBox={`0 0 ${S} ${S}`} role="img" aria-labelledby="tr-cal-t tr-cal-d" className="tr-svg">
        <title id="tr-cal-t">Calibration</title>
        <desc id="tr-cal-d">Share of markets that resolved yes against the probability stated, for Ohmega forecasts and for the market price. The diagonal is perfect calibration.</desc>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={y(0)} y2={y(1)} className="tr-grid" />
            <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} className="tr-grid" />
            <text x={x(t)} y={S - PAD + 12} textAnchor="middle" className="tr-tick">{Math.round(t * 100)}</text>
            <text x={PAD - 6} y={y(t) + 3} textAnchor="end" className="tr-tick">{Math.round(t * 100)}</text>
          </g>
        ))}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} className="tr-diag" />
        {market.map((b) => (
          <circle key={`m${b.low}`} cx={x(b.mean_p)} cy={y(b.hit_rate)} r={r(b.n)} className="tr-pt-market">
            <title>{`Market: priced ${Math.round(b.mean_p * 100)}%, happened ${Math.round(b.hit_rate * 100)}% (${b.n} markets)`}</title>
          </circle>
        ))}
        {ours.map((b) => (
          <circle key={`o${b.low}`} cx={x(b.mean_p)} cy={y(b.hit_rate)} r={r(b.n)} className="tr-pt-ours">
            <title>{`Ohmega: said ${Math.round(b.mean_p * 100)}%, happened ${Math.round(b.hit_rate * 100)}% (${b.n} markets)`}</title>
          </circle>
        ))}
        <text x={S / 2} y={S - 2} textAnchor="middle" className="tr-axis">probability stated (%)</text>
        <text x={9} y={S / 2} textAnchor="middle" transform={`rotate(-90 9 ${S / 2})`} className="tr-axis">share that happened (%)</text>
      </svg>
      <figcaption className="tr-cap">
        <span className="tr-key tr-key-ours" /> Ohmega <span className="tr-key tr-key-market" /> market. Dot area is the number of markets; the diagonal is perfect calibration.
      </figcaption>
    </figure>
  );
}

// The recipe lab's picture: when a recipe says X%, how often it happened, as said (hollow, thin line) and after recalibration (filled, thicker line), one line per
// series, named directly at its last point (no key), with the diagonal for "honest". Dot area is the number of forecasts in the bin.
export function ReliabilityChart({ raw, calibrated, title, caption }: { raw: Bucket[]; calibrated: Bucket[]; title: string; caption: string }) {
  if (raw.length === 0 && calibrated.length === 0) return <p className="tr-empty">No forecasts to draw yet.</p>;
  const r = (n: number) => 2.5 + Math.min(6, Math.sqrt(n) * 1.5);
  const path = (bs: Bucket[]) => bs.map((b, i) => `${i === 0 ? "M" : "L"}${x(b.mean_p).toFixed(1)} ${y(b.hit_rate).toFixed(1)}`).join(" ");
  const name = (bs: Bucket[], text: string, cls: string, dy: number): ReactNode => {
    const b = bs[bs.length - 1];
    if (!b) return null;
    const right = x(b.mean_p) > S - 90;
    return (
      <text x={x(b.mean_p) + (right ? -9 : 9)} y={y(b.hit_rate) + dy} textAnchor={right ? "end" : "start"} className={cls}>
        {text}
      </text>
    );
  };
  return (
    <figure className="tr-fig">
      <svg viewBox={`0 0 ${S} ${S}`} role="img" aria-label={title} className="tr-svg">
        <title>{title}</title>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={y(0)} y2={y(1)} className="tr-grid" />
            <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} className="tr-grid" />
            <text x={x(t)} y={S - PAD + 12} textAnchor="middle" className="tr-tick">{Math.round(t * 100)}</text>
            <text x={PAD - 6} y={y(t) + 3} textAnchor="end" className="tr-tick">{Math.round(t * 100)}</text>
          </g>
        ))}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} className="tr-diag" />
        <path d={path(raw)} className="tr-rel-raw" />
        <path d={path(calibrated)} className="tr-rel-cal" />
        {raw.map((b) => (
          <circle key={`r${b.low}`} cx={x(b.mean_p)} cy={y(b.hit_rate)} r={r(b.n)} className="tr-pt-market">
            <title>{`As said: ${Math.round(b.mean_p * 100)}%, happened ${Math.round(b.hit_rate * 100)}% (${b.n} forecasts)`}</title>
          </circle>
        ))}
        {calibrated.map((b) => (
          <circle key={`c${b.low}`} cx={x(b.mean_p)} cy={y(b.hit_rate)} r={r(b.n)} className="tr-pt-ours">
            <title>{`After correction: ${Math.round(b.mean_p * 100)}%, happened ${Math.round(b.hit_rate * 100)}% (${b.n} forecasts)`}</title>
          </circle>
        ))}
        {name(raw, "as said", "tr-rel-lbl-raw", -7)}
        {name(calibrated, "corrected", "tr-rel-lbl-cal", 14)}
        <text x={S / 2} y={S - 2} textAnchor="middle" className="tr-axis">probability stated (%)</text>
        <text x={9} y={S / 2} textAnchor="middle" transform={`rotate(-90 9 ${S / 2})`} className="tr-axis">share that happened (%)</text>
      </svg>
      <figcaption className="tr-cap">{caption}</figcaption>
    </figure>
  );
}

export function BrierSeries({ series }: { series: DiffPoint[] }) {
  const W = 420;
  const H = 180;
  const L = 40;
  const B = 24;
  const T = 10;
  if (series.length < 2) {
    return <p className="tr-empty">The comparison line needs at least two resolved markets that were priced when we forecast them.</p>;
  }
  const m = Math.max(0.05, ...series.map((d) => Math.abs(d.diff))) * 1.15;
  const px = (i: number) => L + (i / (series.length - 1)) * (W - L - 8);
  const py = (v: number) => T + (1 - (v + m) / (2 * m)) * (H - T - B);
  const d = series.map((p, i) => `${i === 0 ? "M" : "L"}${px(i).toFixed(1)} ${py(p.diff).toFixed(1)}`).join(" ");
  const last = series[series.length - 1];
  return (
    <figure className="tr-fig">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="tr-br-t tr-br-d" className="tr-svg tr-wide">
        <title id="tr-br-t">Brier score difference over time</title>
        <desc id="tr-br-d">Running average of our Brier error minus the market's, in order of resolution. Below zero means we are ahead.</desc>
        <line x1={L} x2={W - 8} y1={py(0)} y2={py(0)} className="tr-diag" />
        <text x={L - 4} y={py(0) + 3} textAnchor="end" className="tr-tick">0</text>
        <text x={L - 4} y={py(m * 0.85) + 3} textAnchor="end" className="tr-tick">+{(m * 0.85).toFixed(2)}</text>
        <text x={L - 4} y={py(-m * 0.85) + 3} textAnchor="end" className="tr-tick">-{(m * 0.85).toFixed(2)}</text>
        <path d={d} className={last.diff <= 0 ? "tr-line tr-ahead" : "tr-line tr-behind"} fill="none" />
        <text x={L} y={H - 6} className="tr-tick">{series[0].at}</text>
        <text x={W - 8} y={H - 6} textAnchor="end" className="tr-tick">{last.at}</text>
        <text x={W - 8} y={T + 6} textAnchor="end" className="tr-axis">above 0: market closer</text>
        <text x={W - 8} y={H - B - 4} textAnchor="end" className="tr-axis">below 0: we are closer</text>
      </svg>
      <figcaption className="tr-cap">Running mean of (our Brier minus the market's) over {series.length} resolved markets. Now {last.diff > 0 ? "+" : ""}{last.diff.toFixed(3)}.</figcaption>
    </figure>
  );
}

// A chart with the question it answers, a one-sentence reading guide, and a refusal to draw anything below the verdict threshold ("Too early: 2 of 30").
export function ChartCard({ title, guide, have, need, children }: { title: string; guide: string; have: number; need: number; children: ReactNode }) {
  return (
    <div className="tr-card">
      <h3 className="tr-h3">{title}</h3>
      <p className="tr-note">{guide}</p>
      {have >= need ? children : <p className="tr-empty">Too early: {have} of {need} markets needed before this chart means anything.</p>}
    </div>
  );
}
