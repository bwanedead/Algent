import type { Metadata } from "next";
import Link from "next/link";

import Crumbs, { INTEL_CRUMB } from "@/components/Crumbs";
import { claimOf } from "@/lib/daily";
import { latestSnapshot } from "@/lib/intel";

import "@/app/geopolitics/geopolitics.css";
import "@/components/entities/entities.css";
import "../theaters/theaters.css";

export const metadata: Metadata = {
  title: "Briefs",
  description: "Researched deep reads of a single theater: the timeline, who is doing what to whom, and what would change our mind.",
  alternates: { canonical: "/intel/briefs" },
};

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

// Every brief, newest first. A brief is a one-theater deep read; the daily report links the ones it drew on.
export default async function BriefsIndexPage() {
  const snap = await latestSnapshot();
  const briefs = [...(snap?.briefs ?? [])].sort((a, b) => b.as_of.localeCompare(a.as_of));
  return (
    <div className="intel-page th-page">
      <Crumbs trail={[INTEL_CRUMB]} />
      <p className="th-kicker">
        <span>Briefs</span>
      </p>
      <h1 className="th-claim">{briefs.length > 0 ? `${briefs.length} researched brief${briefs.length === 1 ? "" : "s"}, newest first` : "No briefs yet"}</h1>
      {briefs.length === 0 ? (
        <p className="intel-empty">Briefs appear here once a theater has been researched in depth. Check back soon.</p>
      ) : (
        <ul className="en-rows">
          {briefs.map((b) => (
            <li key={b.slug}>
              <span className="en-when">{b.as_of.slice(0, 10)}</span>
              <Link href={`/intel/briefs/${b.slug}`}>{b.title}</Link>
              {b.theater_name && <span className="geo-muted"> · {b.theater_name}</span>}
              {b.bottom_line && <span className="geo-muted"> {claimOf(b.bottom_line, 140)}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
