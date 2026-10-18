"use client";

import Link from "next/link";

import IsoFlags from "@/components/IsoFlags";
import { DirMark, HeatBar } from "@/components/vl/primitives";
import type { HudTheater } from "@/lib/globe/hud-data";

import { pointsAt, type HudCtx } from "../types";

import PulseRow from "./PulseRow";

/** A theater at a glance: heat and trend, direction, the writer's headline, its Pulses and where it lives in the report. */
export default function TheaterCard({ t, ctx, heatMax }: { t: HudTheater; ctx: HudCtx; heatMax: number }) {
  return (
    <div className="hud-theater" {...pointsAt(ctx, t.iso)}>
      <div className="hud-theater-meta">
        <DirMark direction={t.dir} label />
        <span className="hud-theater-heat"><HeatBar share={heatMax > 0 ? t.heat / heatMax : 0} label={`${t.name} heat`} /></span>
        <span className="hud-k">heat {Math.round(t.heat)} · {t.trend}</span>
      </div>
      {t.line && <p className="hud-lede">{t.line}</p>}
      {t.iso.length > 0 && <p className="hud-flags"><IsoFlags codes={t.iso} link /></p>}
      {t.pulses.length > 0 && <ul className="hud-rows">{t.pulses.map((p) => <PulseRow key={p.id} p={p} ctx={ctx} />)}</ul>}
      <p className="hud-foot"><Link href={t.href}>Report section</Link></p>
    </div>
  );
}
