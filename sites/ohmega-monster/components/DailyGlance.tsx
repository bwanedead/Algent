import Link from "next/link";

import type { Daily, DailyPulse } from "@/lib/daily";
import { claimOf, shortTheater, theaterAnchor } from "@/lib/daily";
import { fmtDelta } from "@/lib/band";
import type { Direction, Snapshot } from "@/lib/intel";

import { CoverSpark, PulseTiles } from "./DailyVisuals";

// The day at a glance: a small-multiples table, one row per theater, every row the same shape and
// the same tiles (name, number, band, 24h move) so the eye compares down the columns (doctrine: overview first, small
// multiples, position on a common scale, accent = change). Used by the report (screen one) and,
// in `compact` form, by the home-page card.

const DIR: Record<Direction, { glyph: string; word: string; moving: boolean }> = {
  rising: { glyph: "▲", word: "rising", moving: true },
  steady: { glyph: "◆", word: "steady", moving: false },
  easing: { glyph: "▼", word: "easing", moving: true },
  unclear: { glyph: "?", word: "unclear", moving: false },
};

/** The biggest 24h Pulse move in a theater (signed), null when none is known. */
function topMove(pulses: DailyPulse[]): number | null {
  let best: number | null = null;
  for (const p of pulses) if (p.change_24h !== null && (best === null || Math.abs(p.change_24h) > Math.abs(best))) best = p.change_24h;
  return best;
}

export default function DailyGlance({
  report,
  snap,
  base = "",
  compact = false,
}: {
  report: Daily;
  snap: Snapshot | null;
  /** Path the theater links hang their #anchor on ("" on the report page itself). */
  base?: string;
  compact?: boolean;
}) {
  if (report.theaters.length === 0) return null;
  return (
    <div className={`geo-glance${compact ? " is-compact" : ""}`}>
      {!compact && (
        <div className="geo-glance-head" aria-hidden="true">
          <span>Theater</span>
          <span>State</span>
          <span>Direction</span>
          <span>Pulses · move in 24h</span>
          <span>Δ 24h</span>
          <span>Coverage</span>
        </div>
      )}
      <ol className="geo-rows">
        {report.theaters.map((t, i) => {
          const dir = DIR[t.escalation.direction];
          const move = topMove(t.pulses);
          const moved = move !== null && Math.round(move * 10) !== 0;
          const series = snap?.theaters.find((x) => x.id === t.theater_id)?.series ?? snap?.theaters.find((x) => x.name === t.name)?.series ?? [];
          const state = claimOf(t.bottom_line || t.since_yesterday[0]?.what || "", 110);
          return (
            <li key={t.theater_id + i} className="geo-row">
              <Link href={`${base}#${theaterAnchor(t, i)}`} className="geo-name" title={t.name}>
                {shortTheater(t.name)}
              </Link>
              {!compact && <span className="geo-state">{state}</span>}
              <span className={`geo-dir${dir.moving ? " is-moving" : ""}`} title={`Is the situation itself getting worse or easing: ${dir.word}, ${t.escalation.pace} pace`}>
                <span aria-hidden="true">{dir.glyph}</span> {dir.word}
              </span>
              <PulseTiles pulses={t.pulses} snap={snap} limit={compact ? 2 : 3} asOf={report.date} className="geo-tiles" />
              <span className={`geo-delta${moved ? " is-moving" : ""}`} title="Biggest Pulse move in 24 hours">
                {fmtDelta(move)}
              </span>
              {!compact && (
                <span className="geo-cov-cell">
                  <CoverSpark series={series} coverage={t.temperature.coverage} name={t.name} />
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
