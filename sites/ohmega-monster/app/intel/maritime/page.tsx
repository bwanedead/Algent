import type { Metadata } from "next";
import Link from "next/link";

import MaritimeTable from "@/components/maritime/MaritimeTable";
import { maritimeEvents } from "@/lib/maritime";

import "@/app/geopolitics/geopolitics.css";
import "../theaters/theaters.css";

export const metadata: Metadata = {
  title: "Maritime behaviour",
  description: "Vessels that went dark where others stayed visible, met in open water, changed identity, matched a sanctions list or loitered over cable corridors: Ohmega's own analysis of AIS.",
  alternates: { canonical: "/intel/maritime", types: { "application/json": "/api/v1/maritime" } },
};

// Behaviour events Ohmega derives from the ship positions it hears (backend `maritime/`, migration 013): an AIS gap inside water that stayed heard, two ships
// alongside in open water, a renamed or re-flagged identity, a vessel matching a sanctions designation, a long dwell over a chokepoint or cable corridor. Each
// row opens into the reason it was flagged, the vessel's identity, a mini track and the evidence points. A pattern seen, never a finding of intent.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function MaritimePage() {
  const rows = await maritimeEvents();
  const nowMs = Date.now();
  const ongoing = rows.filter((e) => e.ended_at === null).length;
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <span>Intelligence</span> <Link href="/live" className="xt">live map →</Link>
      </p>
      <h1 className="th-claim">Maritime behaviour</h1>
      <p className="th-asof">
        {rows.length > 0
          ? `${rows.length} events in the last 30 days, ${ongoing} still going. Ohmega's own analysis of the ship positions it hears, labelled with how sure it is and why.`
          : "No behaviour events have been derived yet."}{" "}
        A pattern seen, not a finding of intent: a silence, an encounter, a rename and a long dwell all have innocent explanations.
      </p>
      <MaritimeTable rows={rows} nowMs={nowMs} />
      <p className="th-asof">
        How to read it. An AIS gap is reported only where other ships kept being heard, so a ship that sailed out of receiver coverage is not counted as going dark. Ship-to-ship
        candidates exclude ports, harbour approaches and crowds of waiting ships. A sanctioned-vessel match rests on the IMO number (high confidence) or on exact name plus flag
        state (medium); a listing is an act of a government, not a finding of guilt. Cable and pipeline zones are approximate corridors, not surveyed routes. Positions come from AIS
        (aisstream.io, Fintraffic digitraffic.fi, Norwegian Coastal Administration) and reflect only what volunteer and coastal receivers hear. Ended events stay for 30 days.
        Sanctions: <Link href="/intel/sanctions" className="xt">designations</Link>. Machine access: <Link href="/api/v1/maritime" className="xt">/api/v1/maritime</Link> and the MCP tool <code>get_maritime_behaviour</code>.
      </p>
    </div>
  );
}
