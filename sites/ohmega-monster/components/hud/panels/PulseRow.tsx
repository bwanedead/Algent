"use client";

import Link from "next/link";

import { Delta, Spark } from "@/components/vl/primitives";
import { BAND_LABEL, fmtDelta } from "@/lib/band";
import type { HudPulse } from "@/lib/globe/hud-data";

import { pointsAt, type HudCtx } from "../types";

/** One tracked question: its title, the line it has drawn (band-coloured), the 0-100 reading and the 7-day move. */
export default function PulseRow({ p, ctx }: { p: HudPulse; ctx: HudCtx }) {
  return (
    <li className={`hud-pulse intel-band-${p.band}`} {...pointsAt(ctx, p.iso)}>
      <Link href={p.href} className="hud-row hud-pulse-link" title={`${p.title}: ${BAND_LABEL[p.band]}`}>
        <span className="hud-row-text">{p.title}</span>
        <span className="hud-pulse-spark"><Spark values={p.history} label={`${p.title}, last ${p.history.length} readings`} /></span>
        <span className="hud-pulse-n">{p.position === null ? "—" : Math.round(p.position)}</span>
        <Delta text={fmtDelta(p.change7d)} sign={p.change7d ?? 0} />
      </Link>
    </li>
  );
}
