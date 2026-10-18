"use client";

import Link from "next/link";

import { shortDate } from "@/lib/calendar-shared";

import { pointsAt, type PanelProps } from "../types";

/** The latest designations across the US, UK and EU lists. */
export default function SanctionsPanel({ ctx }: PanelProps) {
  const rows = ctx.data.sanctions;
  if (rows.length === 0) return <p className="hud-none">No designations in the last three weeks.</p>;
  return (
    <>
      <ul className="hud-rows hud-table">
        {rows.map((r) => (
          <li key={r.id} {...pointsAt(ctx, r.iso)}>
            <span className="hud-row">
              <span className="hud-k hud-when">{shortDate(r.date)}</span>
              <span className="hud-tag" title={r.programme || undefined}>{r.source}</span>
              {r.url ? <a href={r.url} className="hud-row-text" target="_blank" rel="noopener noreferrer">{r.name}</a> : <span className="hud-row-text">{r.name}</span>}
              <span className="hud-k">{r.type}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="hud-foot"><Link href="/intel/sanctions">All sanctions</Link></p>
    </>
  );
}
