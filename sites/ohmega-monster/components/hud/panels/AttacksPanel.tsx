"use client";

import Link from "next/link";

import Provenance from "@/components/conflict/Provenance";
import { EVENT_SOURCES, typeLabel, type EventSource } from "@/lib/conflict-shared";
import { shortDate } from "@/lib/calendar-shared";

import { pointsAt, type PanelProps } from "../types";

/** The strongest attacks reported in the last three days. The count is Ohmega's own tally (a minimum), with its provenance in the "i". */
export default function AttacksPanel({ ctx }: PanelProps) {
  const a = ctx.data.attacks;
  if (!a) return <p className="hud-none">No attack reports collected yet.</p>;
  return (
    <>
      <p className="hud-sub">
        <span className="cx-hud-n">{a.total}</span> reported in {a.days} days <Provenance p={a.provenance} label="the attack count" />
      </p>
      <ul className="hud-rows hud-table">
        {a.rows.map((r) => (
          <li key={r.id} {...pointsAt(ctx, r.iso)}>
            <span className="hud-row">
              <span className="hud-k hud-when">{shortDate(r.date)}</span>
              <span className="hud-tag" title={r.machine ? "Machine-coded from news text: can duplicate or misplace an event" : EVENT_SOURCES[r.source as EventSource]?.name}>
                {r.machine ? "auto" : EVENT_SOURCES[r.source as EventSource]?.short ?? r.source}
              </span>
              {r.url ? <a href={r.url} className="hud-row-text" target="_blank" rel="noopener noreferrer">{typeLabel(r.type)}, {r.place}</a> : <span className="hud-row-text">{typeLabel(r.type)}, {r.place}</span>}
              {r.fatalities !== null && <span className="hud-k">{r.fatalities} killed</span>}
            </span>
          </li>
        ))}
      </ul>
      <p className="hud-foot"><Link href="/intel/attacks">Full attack log</Link></p>
    </>
  );
}
