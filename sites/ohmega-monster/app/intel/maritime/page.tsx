import PageTag from "@/components/PageTag";
import type { Metadata } from "next";
import Link from "next/link";

import MaritimeTable from "@/components/maritime/MaritimeTable";
import { maritimeCounts, maritimeEvents } from "@/lib/maritime";
import { fmtNum, shortDate, statView } from "@/lib/stats/render";

import "@/app/daily/daily.css";
import "@/app/situations/situations.css";

export const metadata: Metadata = {
  title: "Maritime behaviour",
  description: "Vessels that went dark where others stayed visible, met in open water, changed identity, matched a sanctions list or loitered over cable corridors: Ohmega's own analysis of AIS.",
  alternates: { canonical: "/intel/maritime", types: { "application/json": "/api/v1/maritime" } },
};

// Behaviour events Ohmega derives from the ship positions it hears (backend `maritime/`, migration 013): an AIS gap inside water that stayed heard, two ships
// alongside in open water, a renamed or re-flagged identity, a vessel matching a sanctions designation, a long dwell over a chokepoint or cable corridor. Each
// row opens into the reason it was flagged, the vessel's identity, a mini track and the evidence points. A pattern seen, never a finding of intent.
export const revalidate = 600; // lib/store.ts TTL.maritime: thirty days of events, republished when one changes

export default async function MaritimePage() {
  const [rows, counts] = await Promise.all([maritimeEvents(), maritimeCounts()]);
  const nowMs = Date.now();
  // The list is a capped fetch (1500 events), so totals come from the published counts document; without one the list size is shown as "latest N".
  const total = counts?.total ?? null;
  const ongoing = counts?.ongoing ?? rows.filter((e) => e.ended_at === null).length;
  const events = statView({ id: "maritime_events", value: rows.length, cap: { limit: 1000, total } });
  const since = events.def.baseline_since ?? "";
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="data" detail="Maritime" /> <Link href="/live" className="xt">live map →</Link>
      </p>
      <h1 className="th-claim">Maritime behaviour</h1>
      <p className="th-asof">
        {rows.length > 0
          ? `${events.text} events since detectors started on ${shortDate(since)} (ended events are kept 30 days); ${fmtNum(ongoing)}${total === null ? "+" : ""} are open. "Open" means the ship has not been heard again, usually because it left our receivers' coverage, not that it is known to be dark. Ohmega's own analysis of the ship positions it hears, labelled with how sure it is and why.`
          : "No behaviour events have been derived yet."}{" "}
        A pattern seen, not a finding of intent: a silence, an encounter, a rename and a long dwell all have innocent explanations.
      </p>
      <MaritimeTable rows={rows} nowMs={nowMs} kindTotals={counts?.byKind} />
      {total !== null && rows.length < total && (
        <p className="th-asof">The table lists the latest {fmtNum(rows.length)} of {fmtNum(total)}; the flag and area counts cover those.</p>
      )}
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
