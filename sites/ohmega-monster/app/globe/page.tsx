import type { Metadata } from "next";

import GlobeViewer from "@/components/globe/GlobeViewer";

export const metadata: Metadata = {
  title: "Globe",
  description: "An interactive globe: drag to turn it, scroll or pinch to zoom in on a region, or let it cycle through its views.",
};

export default function GlobePage() {
  return (
    <div className="intel-page">
      <div className="intel-strip" role="group" aria-label="Globe status">
        <span className="intel-strip-title">Globe</span>
      </div>
      <GlobeViewer />
    </div>
  );
}
