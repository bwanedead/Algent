import Link from "next/link";

import Popover from "@/components/Popover";
import type { Daily, DailyPulse, DailyTheater } from "@/lib/daily";
import { claimOf, shortTheater, theaterAnchor } from "@/lib/daily";
import { fmtDelta } from "@/lib/band";
import type { Direction, Snapshot } from "@/lib/intel";

import { CoverSpark, PulseTiles } from "./DailyVisuals";

// The day at a glance: a small-multiples table, one row per theater, every row the same shape and
// the same 0-100 axis so the eye compares down the columns (doctrine: overview first, small
// multiples, position on a common scale, accent = change). Used by the report (screen one) and,
// in `compact` form, by the home-page card.

const DIR: Record<Direction, { glyph: string; word: string; moving: boolean }> = {
  rising: { glyph: "▲", word: "rising", moving: true },
  steady: { glyph: "◆", word: "steady", moving: false },
  easing: { glyph: "▼", word: "easing", moving: true },
  unclear: { glyph: "?", word: "unclear", moving: false },
};

const clamp = (v: number) => Math.min(100, Math.max(0, v));

/** The biggest 24h Pulse move in a theater (signed), null when none is known. */
function topMove(pulses: DailyPulse[]): number | null {
  let best: number | null = null;
  for (const p of pulses) if (p.change_24h !== null && (best === null || Math.abs(p.change_24h) > Math.abs(best))) best = p.change_24h;
  return best;
}

function Axis({ t, snap, interactive }: { t: DailyTheater; snap: Snapshot | null; interactive: boolean }) {
  const placed = t.pulses.filter((p) => p.position !== null);
  const peak = placed.reduce<number | null>((m, p) => (p.position !== null && (m === null || p.position > m) ? p.position : m), null);
  const inner = (
    <>
      <span className="geo-axis" aria-hidden="true">
        <span className="geo-zones">
          <i className="intel-band-calm" />
          <i className="intel-band-elevated" />
          <i className="intel-band-severe" />
          <i className="intel-band-critical" />
        </span>
        {placed.map((p, i) => (
          <i key={`${p.id}-${i}`} className={`geo-dot intel-band-${p.band}`} style={{ left: `${clamp(p.position ?? 0)}%` }} title={`${p.title}: ${Math.round(p.position ?? 0)} of 100`} />
        ))}
      </span>
      <b className="geo-peak" title="Highest Pulse in this theater">
        {peak === null ? "—" : Math.round(peak)}
      </b>
    </>
  );
  if (!interactive || t.pulses.length === 0) return <span className="geo-axis-cell">{inner}</span>;
  return (
    <Popover
      label={`${t.name}: ${t.pulses.length} Pulse${t.pulses.length === 1 ? "" : "s"}, highest ${peak === null ? "not yet assessed" : Math.round(peak)} of 100`}
      triggerClassName="geo-axis-cell geo-axis-btn"
      wide
      trigger={inner}
    >
      <div className="geo-pd">
        <p className="geo-pd-title">{t.name}</p>
        <PulseTiles pulses={t.pulses} snap={snap} />
      </div>
    </Popover>
  );
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
          <span className="geo-gh-axis">
            <span>0</span>
            <span>Pulses</span>
            <span>100</span>
          </span>
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
              <Axis t={t} snap={snap} interactive={!compact} />
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
