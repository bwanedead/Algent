import type { Metadata } from "next";

import GlobeHud from "@/components/hud/GlobeHud";
import { globeData } from "@/lib/globe-data";
import { hudData } from "@/lib/globe-hud";

export const metadata: Metadata = {
  title: "Globe",
  description: "A personal intelligence board around an interactive globe: pick a country or theater to open its panel, pin what you want to track, and arrange the report, Pulses, live counters, calendar, sanctions and paper trader your way.",
};

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function GlobePage() {
  const [data, hud] = await Promise.all([globeData(), hudData()]);
  return (
    <div className="intel-page">
      <div className="intel-strip" role="group" aria-label="Globe status">
        <span className="intel-strip-title">Globe</span>
        {data && <span className="gv-asof">read against the {data.asOf} report</span>}
      </div>
      <GlobeHud globe={data} hud={hud} />
    </div>
  );
}
