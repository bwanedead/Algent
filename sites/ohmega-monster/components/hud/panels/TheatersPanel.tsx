"use client";

import { useState } from "react";

import { DirTick } from "@/components/vl/primitives";

import type { PanelProps } from "../types";

import TheaterCard from "./TheaterCard";

/** Tabs across today's active theaters (hottest first); each tab is a TheaterCard. "Track" puts the theater on the board as a pinned panel. */
export default function TheatersPanel({ ctx }: PanelProps) {
  const ts = ctx.data.theaters;
  const [sel, setSel] = useState(ts[0]?.id ?? "");
  if (ts.length === 0) return <p className="hud-none">No theaters in today&apos;s report.</p>;
  const t = ts.find((x) => x.id === sel) ?? ts[0];
  const heatMax = Math.max(1, ...ts.map((x) => x.heat));
  return (
    <>
      <div className="hud-tabs" role="tablist" aria-label="Theaters">
        {ts.map((x) => (
          <button key={x.id} type="button" role="tab" id={`hud-tab-${x.id}`} aria-selected={x.id === t.id} aria-controls="hud-tabpanel" className={x.id === t.id ? "is-on" : ""} onClick={() => setSel(x.id)}>
            <DirTick direction={x.dir} /> {x.name}
          </button>
        ))}
      </div>
      <div id="hud-tabpanel" role="tabpanel" aria-labelledby={`hud-tab-${t.id}`}>
        <TheaterCard t={t} ctx={ctx} heatMax={heatMax} />
        <p className="hud-foot"><button type="button" className="hud-link" onClick={() => ctx.track("theater", t.id)}>Track on board</button></p>
      </div>
    </>
  );
}
