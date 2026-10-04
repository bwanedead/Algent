import Popover from "@/components/Popover";
import { SourceLink } from "@/components/DailyVisuals";
import type { Figure } from "@/lib/dossier";
import { dayLabel, fmtNum, fmtPct, fmtShort, isoDay } from "@/lib/dossier-view";

import { Overflow, Section } from "./parts";

// "The numbers": each figure as a mini line-and-dot chart, the latest value big, the move since the
// first reading beside it (from -> to, the baseline drawn as a dashed line at the first value). Each
// chart is scaled to its own range (units differ); the baseline travels with the number.

const SHOWN = 6;
const W = 150;
const H = 38;
const PAD = 4;

function Chart({ f, fresh }: { f: Figure; fresh: boolean }) {
  const pts = f.series.slice(-40);
  const vals = pts.map((p) => p.value);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const span = hi - lo || 1;
  const times = pts.map((p) => Date.parse(`${isoDay(p.as_of)}T00:00:00Z`));
  const timed = pts.length > 1 && times.every(Number.isFinite) && times[times.length - 1] > times[0];
  const y = (v: number) => PAD + (1 - (hi === lo ? 0.5 : (v - lo) / span)) * (H - PAD * 2);
  const x = (i: number) => PAD + (timed ? (times[i] - times[0]) / (times[times.length - 1] - times[0]) : pts.length > 1 ? i / (pts.length - 1) : 1) * (W - PAD * 2);
  const xy = pts.map((p, i) => [x(i), y(p.value)] as const);
  const last = xy[xy.length - 1];
  return (
    <svg className="th-fig-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${f.label}: ${pts.length} reading${pts.length === 1 ? "" : "s"}, from ${fmtNum(pts[0].value)} to ${fmtNum(pts[pts.length - 1].value)}`}>
      {pts.length > 1 && <line x1={PAD} x2={W - PAD} y1={y(pts[0].value)} y2={y(pts[0].value)} className="th-fig-base" />}
      {xy.length > 1 && <path className="th-fig-line" d={xy.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" ")} />}
      {xy.slice(0, -1).map(([px, py], i) => (
        <circle key={i} cx={px} cy={py} r={1.7} className="th-fig-dot" />
      ))}
      <circle cx={last[0]} cy={last[1]} r={3} className={fresh ? "th-fig-now is-fresh" : "th-fig-now"} />
    </svg>
  );
}

function change(f: Figure): { pct: number | null; text: string } {
  const first = f.series[0];
  const last = f.series[f.series.length - 1];
  if (f.series.length < 2) return { pct: null, text: `single reading${first.as_of ? `, ${dayLabel(isoDay(first.as_of) || first.as_of)}` : ""}` };
  const pct = first.value !== 0 ? ((last.value - first.value) / Math.abs(first.value)) * 100 : null;
  const d = last.value - first.value;
  const since = `since ${dayLabel(isoDay(first.as_of) || first.as_of)} (${fmtShort(first.value)})`;
  if (pct !== null) return { pct, text: Math.abs(pct) < 0.05 ? `◆ unchanged ${since}` : `${fmtPct(pct)} ${since}` };
  return { pct: null, text: `${d > 0 ? "▲ +" : d < 0 ? "▼ −" : "◆ "}${fmtShort(Math.abs(d))} ${since}` };
}

function Tile({ f }: { f: Figure }) {
  const last = f.series[f.series.length - 1];
  const c = change(f);
  // Accent = what is new: the latest reading moved off the one before it. The long-run change is neutral.
  const prev = f.series.length > 1 ? f.series[f.series.length - 2] : null;
  const fresh = prev !== null && prev.value !== last.value;
  return (
    <Popover
      label={f.label}
      triggerClassName="th-fig"
      trigger={
        <>
          <span className="th-fig-label">{f.label}</span>
          <span className="th-fig-value">
            <b>{fmtShort(last.value)}</b>
            {f.unit && <span className="th-fig-unit">{f.unit}</span>}
          </span>
          <Chart f={f} fresh={fresh} />
          <span className="th-fig-chg">{c.text}</span>
        </>
      }
    >
      <div className="geo-pd">
        <p className="geo-pd-title">{f.label}</p>
        <p className="geo-pd-big">
          <b>{fmtNum(last.value)}</b> {f.unit}
        </p>
        <div className="th-tbl-wrap">
          <table className="th-tbl">
            <thead>
              <tr>
                <th>As of</th>
                <th className="th-r">Value</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {[...f.series].reverse().map((p, i) => (
                <tr key={i}>
                  <td>{dayLabel(isoDay(p.as_of) || p.as_of)}</td>
                  <td className="th-r">{fmtNum(p.value)}</td>
                  <td>{p.source ? <SourceLink url={p.source} /> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Popover>
  );
}

export default function DossierFigures({ figures }: { figures: Figure[] }) {
  if (figures.length === 0) return null;
  // The figure that moved most (in percent) leads the section's claim; position = rank.
  const moves = figures
    .filter((f) => f.series.length > 1 && f.series[0].value !== 0)
    .map((f) => ({ f, pct: ((f.series[f.series.length - 1].value - f.series[0].value) / Math.abs(f.series[0].value)) * 100 }))
    .sort((a, b) => Math.abs(b.pct) - Math.abs(a.pct));
  const lead = moves.length > 0 && Math.abs(moves[0].pct) >= 0.5 ? `${moves[0].f.label}: ${fmtPct(moves[0].pct)} since the first reading.` : `${figures.length} figure${figures.length === 1 ? "" : "s"} tracked.`;
  const shown = figures.slice(0, SHOWN);
  const rest = figures.slice(SHOWN);
  return (
    <Section id="numbers" title="The numbers" lead={lead}>
      <div className="th-figs">
        {shown.map((f, i) => (
          <Tile key={i} f={f} />
        ))}
      </div>
      {rest.length > 0 && (
        <Overflow label={`More figures (${rest.length})`} trigger={`${rest.length} more figure${rest.length === 1 ? "" : "s"}`} wide>
          <div className="th-figs">
            {rest.map((f, i) => (
              <Tile key={i} f={f} />
            ))}
          </div>
        </Overflow>
      )}
    </Section>
  );
}
