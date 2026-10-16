import type { Metadata } from "next";

import GlobeViewer from "@/components/globe/GlobeViewer";
import { globeData } from "@/lib/globe-data";

export const metadata: Metadata = {
  title: "Globe",
  description: "An interactive globe: drag to turn it, scroll or pinch to zoom in on a region, and colour the countries by what the daily reports say about them.",
};

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function GlobePage() {
  const data = await globeData();
  return (
    <div className="intel-page">
      <div className="intel-strip" role="group" aria-label="Globe status">
        <span className="intel-strip-title">Globe</span>
        {data && <span className="gv-asof">read against the {data.asOf} report</span>}
      </div>
      <GlobeViewer data={data} />
    </div>
  );
}
