import IsoFlags from "./IsoFlags";
import { dayLabel, type ToneSeries } from "@/lib/record-model";

import "./record.css";

const W = 230;
const H = 70;
const PAD = 6;
const yOf = (v: number) => PAD + ((2 - v) / 4) * (H - PAD * 2); // +2 (conciliatory) at the top, -2 (hostile) at the bottom

/** Stance over time for one speaker-side -> counterpart pair, one shared -2..+2 scale for every pair. */
function Dyad({ t }: { t: ToneSeries }) {
  const t0 = Date.parse(t.points[0].date);
  const t1 = Date.parse(t.points[t.points.length - 1].date);
  const x = (d: string) => (t1 > t0 ? PAD + ((Date.parse(d) - t0) / (t1 - t0)) * (W - PAD * 2) : W / 2);
  const path = t.points.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${yOf(p.stance).toFixed(1)}`).join(" ");
  return (
    <div className="tone-cell">
      <p className="tone-title">
        <IsoFlags codes={[t.iso2, t.about_iso2].filter(Boolean)} />
        {t.affiliation} → {t.about} <span className="rec-muted">· {t.n} statements</span>
      </p>
      <svg className="tone-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Tone of ${t.affiliation} toward ${t.about}, ${dayLabel(t.points[0].date)} to ${dayLabel(t.points[t.points.length - 1].date)}, on a scale from hostile to conciliatory`}>
        {[2, -2].map((g) => (
          <line key={g} x1={PAD} x2={W - PAD} y1={yOf(g)} y2={yOf(g)} className="tone-grid-line" />
        ))}
        <line x1={PAD} x2={W - PAD} y1={yOf(0)} y2={yOf(0)} className="tone-zero" />
        <path d={path} className="tone-line" />
        {t.points.map((p) => (
          <circle key={p.date} cx={x(p.date)} cy={yOf(p.stance)} r={2.5} className="tone-dot">
            <title>{`${dayLabel(p.date)}: ${p.stance > 0 ? "+" : ""}${p.stance} (${p.n} statement${p.n === 1 ? "" : "s"})`}</title>
          </circle>
        ))}
      </svg>
      <p className="tone-ends">
        <span>conciliatory ↑</span>
        <span>
          {dayLabel(t.points[0].date)} – {dayLabel(t.points[t.points.length - 1].date)}
        </span>
        <span>↓ hostile</span>
      </p>
    </div>
  );
}

export default function ToneChart({ series }: { series: ToneSeries[] }) {
  if (series.length === 0) return null;
  return (
    <section aria-label="Tone toward a counterpart over time">
      <h2 className="geo-h2">Tone over time</h2>
      <div className="tone-grid">
        {series.map((t) => (
          <Dyad key={`${t.affiliation}>${t.about}`} t={t} />
        ))}
      </div>
    </section>
  );
}
