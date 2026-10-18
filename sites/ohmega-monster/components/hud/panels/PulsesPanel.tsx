"use client";

import Link from "next/link";

import type { PanelProps } from "../types";

import PulseRow from "./PulseRow";

/** The tracked questions that moved most this week, each with the line it has drawn. */
export default function PulsesPanel({ ctx }: PanelProps) {
  const ps = ctx.data.pulses;
  if (ps.length === 0) return <p className="hud-none">No Pulses with a history yet.</p>;
  return (
    <>
      <p className="hud-cap">Biggest 7-day moves · reading 0-100</p>
      <ul className="hud-rows">{ps.map((p) => <PulseRow key={p.id} p={p} ctx={ctx} />)}</ul>
      <p className="hud-foot"><Link href="/pulses">All Pulses</Link></p>
    </>
  );
}
