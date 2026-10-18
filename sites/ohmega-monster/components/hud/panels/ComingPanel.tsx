"use client";

import Link from "next/link";

import { shortDate } from "@/lib/calendar-shared";

import { pointsAt, type PanelProps } from "../types";

/** The calendar for the next 14 days, soonest first. */
export default function ComingPanel({ ctx }: PanelProps) {
  const rows = ctx.data.coming;
  if (rows.length === 0) return <p className="hud-none">Nothing on the calendar in the next 14 days.</p>;
  return (
    <>
      <ul className="hud-rows hud-table">
        {rows.map((r, i) => (
          <li key={`${r.date}-${r.title}-${i}`} {...pointsAt(ctx, r.iso)}>
            <span className="hud-row">
              <span className="hud-k hud-when" title={r.until}>{shortDate(r.date)}</span>
              <span className="hud-tag">{r.label}</span>
              {r.url ? <a href={r.url} className="hud-row-text" target="_blank" rel="noopener noreferrer">{r.title}</a> : <span className="hud-row-text">{r.title}</span>}
            </span>
          </li>
        ))}
      </ul>
      <p className="hud-foot"><Link href="/calendar">Full calendar</Link></p>
    </>
  );
}
