import type { Metadata } from "next";

import Doors from "@/components/Doors";
import { intelDoors } from "@/lib/sections";

import "@/app/geopolitics/geopolitics.css";
import "./theaters/theaters.css";

export const metadata: Metadata = {
  title: "Intelligence",
  description: "The depth behind the daily report: theaters, actors, briefs, the record and the Pulses, in one place.",
  alternates: { canonical: "/intel" },
};

// The Intelligence section's front door: a plain directory of everything behind the daily report, so no
// page type is reachable only by chance. The Situation room (what changed) lives at /intel/situation.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function IntelDirectoryPage() {
  const doors = await intelDoors();
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <span>Intelligence</span>
      </p>
      <h1 className="th-claim">The depth behind the daily report</h1>
      <p className="th-asof">Start with a theater or a state, or see what changed since you were last here.</p>
      <Doors doors={doors} label="Intelligence sections" />
    </div>
  );
}
