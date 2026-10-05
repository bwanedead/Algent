import type { Metadata } from "next";
import Link from "next/link";

import SituationCoverage from "@/components/SituationCoverage";
import SituationForecasts from "@/components/SituationForecasts";
import SituationMoves from "@/components/SituationMoves";
import SituationNew from "@/components/SituationNew";
import { SituationSince, SituationVisitProvider } from "@/components/SituationVisit";
import { actorIds } from "@/lib/actors";
import { dossierList } from "@/lib/dossier";
import { situationRoom } from "@/lib/situation";

import "./intel.css";

export const metadata: Metadata = {
  title: "Situation Room",
  description: "What changed, and how well we are calling it: the biggest Pulse moves, rising coverage, forecasts due and the track record.",
};

// The Situation Room: what changed, and how well are we calling it. It deliberately does not repeat
// the other pages' jobs: /geopolitics reads the day, /pulses scans the whole state of the world.
export default function IntelPage() {
  const room = situationRoom();
  const dossiers = dossierList().length;
  return (
    <div className="intel-page sit-page">
      <SituationVisitProvider>
        <div className="intel-strip sit-strip" role="group" aria-label="Status">
          <span className="intel-strip-title">Situation room</span>
          {room && (
            <span className="intel-strip-item">
              <span className="intel-micro">As of</span> {room.asOfLabel}
            </span>
          )}
          {room && (
            <span className="intel-strip-item">
              <SituationSince times={room.changeTimes} />
            </span>
          )}
          <span className="intel-strip-item sit-strip-links">
            {dossiers > 0 && <Link href="/intel/theaters">Every theater&apos;s dossier →</Link>}
            {actorIds().length > 0 && <Link href="/intel/actors">Who the actors are →</Link>}
            <Link href="/geopolitics">Read the day →</Link>
            <Link href="/pulses">Scan every Pulse →</Link>
          </span>
        </div>

        {!room && <p className="intel-empty">No intelligence has been published yet. Check back soon.</p>}

        {room && (
          <>
            <SituationMoves moves={room.moves} />
            <SituationCoverage coverage={room.coverage} />
            <SituationForecasts forecasts={room.forecasts} />
            <SituationNew items={room.news} />
          </>
        )}
      </SituationVisitProvider>
    </div>
  );
}
