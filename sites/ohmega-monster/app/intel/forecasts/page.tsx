import type { Metadata } from "next";
import Link from "next/link";

import Crumbs, { INTEL_CRUMB } from "@/components/Crumbs";
import PageTag from "@/components/PageTag";
import SituationForecasts from "@/components/SituationForecasts";
import { SituationVisitProvider } from "@/components/SituationVisit";
import { situationRoom } from "@/lib/situation";

import "../intel.css";
import "../theaters/theaters.css";

export const metadata: Metadata = {
  title: "Forecasts and track record",
  description: "Every open forecast on one timeline, and how well past calls have held up.",
  alternates: { canonical: "/intel/forecasts" },
};

// A tool, not a publication: the forecasts the desk has made across theaters (what resolves soon, how sure we were)
// and the track record. It is what was unique in the retired Situation room; the rest of that page already lives in
// Pulses (moves), Theaters (coverage, direction) and the Daily (what changed).
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function ForecastsPage() {
  const room = await situationRoom();
  return (
    <div className="intel-page sit-page">
      <Crumbs trail={[INTEL_CRUMB]} />
      <p className="ptag-row">
        <PageTag kind="tool" detail="Forecasts" />
      </p>
      <SituationVisitProvider>
        {!room ? (
          <p className="intel-empty">No forecasts have been published yet. Check back soon.</p>
        ) : (
          <SituationForecasts forecasts={room.forecasts} />
        )}
      </SituationVisitProvider>
      <p className="geo-xlink">
        <Link href="/intel/theaters">Theaters: forecasts per situation →</Link> · <Link href="/pulses">Pulses →</Link>
      </p>
    </div>
  );
}
