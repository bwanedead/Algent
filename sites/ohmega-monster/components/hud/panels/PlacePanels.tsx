"use client";

import { CountryContent } from "@/components/globe/GlobePanel";

import type { PanelProps } from "../types";

import TheaterCard from "./TheaterCard";

/** The country the reader picked on the globe: briefs, figures against the world median, counts, theaters (the former side panel). */
export function CountryPanel({ panel, ctx }: PanelProps) {
  return <CountryContent iso={panel.ref} data={ctx.globe} />;
}

/** The theater the reader picked on the globe: the same card as a theaters tab. */
export function TheaterPanel({ panel, ctx }: PanelProps) {
  const t = ctx.data.theaters.find((x) => x.id === panel.ref);
  if (!t) return <p className="hud-none">Not in today&apos;s report.</p>;
  return <TheaterCard t={t} ctx={ctx} heatMax={Math.max(1, ...ctx.data.theaters.map((x) => x.heat))} />;
}
