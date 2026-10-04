import Link from "next/link";

import type { Dossier, DossierIndexItem } from "@/lib/dossier";
import { DIRECTION, dayLabel, isoDay } from "@/lib/dossier-view";
import { BAND_LABEL, COVERAGE_DISPLAY } from "@/lib/intel";

import { EscalationMini } from "./EscalationTrack";

// The theater index as small multiples: every row is the same shape (name, escalation strip, top Pulse
// band, coverage bars, last seen) on the same day axis and the same bar scale, so the eye learns one row
// and reads the differences. Rows are grouped by escalation direction (3 chunks, most urgent first).

export type TheaterRow = { item: DossierIndexItem; dossier: Dossier | null };

function CoverBars({ series, days, max, name }: { series: { day: string; count: number }[]; days: string[]; max: number; name: string }) {
  const CW = 6;
  const H = 22;
  const W = Math.max(1, days.length) * CW;
  const at = new Map(series.map((s) => [isoDay(s.day), s.count]));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="th-cbars" role="img" aria-label={`${name}: headlines per day over the last ${days.length} days`}>
      <line x1={0} x2={W} y1={H - 0.5} y2={H - 0.5} className="geo-spark-base" />
      {days.map((d, i) => {
        const c = at.get(d) ?? 0;
        const h = c > 0 ? Math.max(1.5, (c / max) * (H - 3)) : 0;
        return h > 0 ? <rect key={d} x={i * CW} y={H - 1 - h} width={CW - 1.5} height={h} className="geo-spark-bar" /> : null;
      })}
    </svg>
  );
}

function Row({ r, days, max }: { r: TheaterRow; days: string[]; max: number }) {
  const { item, dossier: d } = r;
  const dir = DIRECTION[item.escalation_direction];
  const cov = COVERAGE_DISPLAY[item.coverage];
  const moving = item.escalation_direction === "rising" || item.escalation_direction === "easing";
  return (
    <li className="th-row">
      <Link href={`/intel/theaters/${item.theater_id}`} className="th-row-name">
        <b>{item.name}</b>
        {item.domain && <span className="th-domain">{item.domain}</span>}
      </Link>
      <span className="th-row-track">
        <span className={moving ? "th-dir is-moving" : "th-dir"}>
          <span aria-hidden="true">{dir.glyph}</span> {dir.word}
        </span>
        {d && d.escalation_history.length > 0 && <EscalationMini history={d.escalation_history} days={days} name={item.name} />}
      </span>
      <span className="th-row-band">
        {item.max_band !== "unassessed" ? (
          <span className={`intel-chip intel-band-${item.max_band}`} title="The most severe Pulse of this theater">
            {BAND_LABEL[item.max_band]}
          </span>
        ) : (
          <span className="th-when">not assessed</span>
        )}
      </span>
      <span className="th-row-cov" title="How much of the world's headlines are about this theater">
        {d && d.coverage_series.length > 0 && <CoverBars series={d.coverage_series} days={days} max={max} name={item.name} />}
        <span className="th-when">
          <span aria-hidden="true">{cov.glyph}</span> {cov.label}
        </span>
      </span>
      <span className="th-row-seen th-when">
        {item.last_seen ? dayLabel(isoDay(item.last_seen) || item.last_seen) : ""}
        {item.days_covered > 0 && (
          <>
            {" "}
            · {item.days_covered} report{item.days_covered === 1 ? "" : "s"}
          </>
        )}
      </span>
    </li>
  );
}

export function TheaterGroup({ title, rows, days, max }: { title: string; rows: TheaterRow[]; days: string[]; max: number }) {
  if (rows.length === 0) return null;
  return (
    <section className="th-group" aria-label={title}>
      <h2 className="th-group-h">{title}</h2>
      <ul className="th-rows">
        {rows.map((r) => (
          <Row key={r.item.theater_id} r={r} days={days} max={max} />
        ))}
      </ul>
    </section>
  );
}
