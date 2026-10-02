"use client";

// BIGGEST MOVES: the top Pulse moves for the chosen period as dumbbells on one shared 0–100 axis.
// The heading is the finding ("X up 16 in 7 days"), the row's tile opens the shared Pulse popover.
// The server computes all three periods; this component only switches between them.

import Link from "next/link";
import { useState } from "react";

import { BAND_LABEL } from "@/lib/band";
import { DEFAULT_PERIOD, PERIODS, type Period } from "@/lib/pulse-wall";
import type { MovesByPeriod, SituationMove } from "@/lib/situation";

import PulseTile from "./PulseTile";
import { Dumbbell, DumbbellAxis } from "./SituationDumbbell";
import { NewDot } from "./SituationVisit";

const PERIOD_WORDS: Record<Period, string> = { "24h": "24 hours", "7d": "7 days", "30d": "30 days" };
const round = (v: number) => Math.round(v * 10) / 10;
const sign = (d: number) => (d > 0 ? "+" : "−") + Math.abs(round(d));

function claim(top: SituationMove[], period: Period): string {
  if (top.length === 0) return `No Pulse has moved in ${PERIOD_WORDS[period]}`;
  const m = top[0];
  return `${m.pulse.name} ${m.delta > 0 ? "up" : "down"} ${Math.abs(round(m.delta))} to ${Math.round(m.to)} in ${PERIOD_WORDS[period]}`;
}

function note(m: SituationMove): string | undefined {
  return m.fromBand !== m.toBand ? `${BAND_LABEL[m.fromBand]} → ${BAND_LABEL[m.toBand]}` : undefined;
}

export default function SituationMoves({ moves }: { moves: MovesByPeriod }) {
  const [period, setPeriod] = useState<Period>(DEFAULT_PERIOD);
  const { top, crossed } = moves[period];
  const young = top.some((m) => m.firstReading);
  return (
    <section className="sit-sec" aria-labelledby="sit-moves-h">
      <div className="sit-head">
        <h2 id="sit-moves-h">{claim(top, period)}</h2>
        <div className="sit-ctl">
          <div className="sit-seg" role="group" aria-label="Period">
            {PERIODS.map((p) => (
              <button key={p} type="button" aria-pressed={p === period} onClick={() => setPeriod(p)}>
                {p}
              </button>
            ))}
          </div>
          <Link href={`/pulses?sort=moves&period=${period}`}>All Pulses →</Link>
        </div>
      </div>

      {top.length > 0 && (
        <>
          <div className="sit-row sit-axis-row">
            <span className="sit-row-tile" />
            <div className="sit-row-chart">
              <DumbbellAxis />
            </div>
          </div>
          <ul className="sit-moves">
            {top.map((m) => (
              <li key={m.pulse.id} className="sit-row">
                <NewDot at={m.at} />
                <div className="sit-row-tile">
                  <PulseTile pulse={m.pulse} delta={m.delta} period={period} size="s" note={note(m)} />
                </div>
                <div className="sit-row-chart">
                  <Dumbbell
                    from={m.from}
                    to={m.to}
                    label={`${m.pulse.name}: ${Math.round(m.from)} to ${Math.round(m.to)} (${sign(m.delta)}) in ${PERIOD_WORDS[period]}`}
                  />
                </div>
              </li>
            ))}
          </ul>
          <p className="intel-micro sit-foot">
            Hollow dot: before · filled dot: now{crossed > 0 ? ` · ${crossed} Pulse${crossed === 1 ? "" : "s"} changed band` : ""}
            {young ? ` · Pulses younger than ${PERIOD_WORDS[period]} are measured from their first reading` : ""}
          </p>
        </>
      )}
    </section>
  );
}
