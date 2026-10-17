import type { Metadata } from "next";
import Link from "next/link";

import SanctionsTable from "@/components/sanctions/SanctionsTable";
import { recentSanctions } from "@/lib/sanctions";

import "@/app/geopolitics/geopolitics.css";
import "../theaters/theaters.css";

export const metadata: Metadata = {
  title: "Sanctions designations",
  description: "Who was added to or removed from the US, UK and EU sanctions lists, found by comparing each list with its previous version.",
  alternates: { canonical: "/intel/sanctions", types: { "application/json": "/api/v1/sanctions" } },
};

// Recent designations and delistings on the OFAC SDN list, the UK Sanctions List and the EU consolidated financial sanctions list. Ohmega
// downloads each list every six hours and diffs it against the last copy (backend `sanctions/`, migration 012), so a row is a change we saw,
// dated by the list when it states a recent date and otherwise the day we saw it. Designated ships also appear on the places map.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function SanctionsPage() {
  const rows = await recentSanctions(90);
  const today = new Date().toISOString().slice(0, 10);
  const added = rows.filter((r) => r.action === "designated").length;
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <span>Intelligence</span> <Link href="/calendar" className="xt">what&apos;s coming →</Link>
      </p>
      <h1 className="th-claim">Sanctions designations</h1>
      <p className="th-asof">
        {rows.length > 0
          ? `${added} added and ${rows.length - added} removed in the last 90 days across the US, UK and EU lists.`
          : "No designations have been read yet."}{" "}
        Each row is a change between two copies of an official list; it links to that list.
      </p>
      <SanctionsTable rows={rows} today={today} />
      <p className="th-asof">
        Sources: US Treasury OFAC SDN list, UK Sanctions List (FCDO and OFSI), EU consolidated financial sanctions list. A list that dates its own entries
        (UK, EU) is read for the last 30 days the first time we see it; the US list carries no dates, so its changes start from our first copy.
      </p>
    </div>
  );
}
