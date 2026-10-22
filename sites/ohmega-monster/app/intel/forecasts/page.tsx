import type { Metadata } from "next";
import Link from "next/link";

import Crumbs, { DATA_CRUMB } from "@/components/Crumbs";
import JudgmentsSwitch from "@/components/JudgmentsSwitch";
import PageTag from "@/components/PageTag";
import SituationForecasts from "@/components/SituationForecasts";
import { SituationVisitProvider } from "@/components/SituationVisit";
import { situationRoom } from "@/lib/situation";

import "../intel.css";
import "@/app/situations/situations.css";

export const metadata: Metadata = {
  title: "Forecasts",
  description: "Every open forecast on one timeline, and how well past calls have held up.",
  alternates: { canonical: "/intel/forecasts" },
};

// A judgment page, one of two views of our forecasting (the other is /intel/track-record, see JudgmentsSwitch): the forecasts the
// desk has made across situations (what resolves soon, how sure we were).
export const revalidate = 1800; // lib/store.ts TTL.daily: a desk publishes twice a day

export default async function ForecastsPage() {
  const room = await situationRoom();
  return (
    <div className="intel-page sit-page">
      <Crumbs trail={[DATA_CRUMB]} />
      <p className="ptag-row">
        <PageTag kind="judgment" detail="Forecasts" />
      </p>
      <JudgmentsSwitch current="open" />
      <SituationVisitProvider>
        {!room ? (
          <p className="intel-empty">No forecasts have been published yet. Check back soon.</p>
        ) : (
          <SituationForecasts forecasts={room.forecasts} />
        )}
      </SituationVisitProvider>
      <p className="geo-xlink">
        <Link href="/situations">Situations: forecasts per story →</Link> · <Link href="/pulses">Pulses →</Link>
      </p>
    </div>
  );
}
