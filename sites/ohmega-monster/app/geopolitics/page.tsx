import type { Metadata } from "next";
import Link from "next/link";

import { latestDaily } from "@/lib/daily";

import GeopoliticsDay, { BASE, DOMAIN } from "./GeopoliticsDay";
import "./geopolitics.css";

export const metadata: Metadata = {
  title: "Geopolitics — daily report",
  description: "A daily rundown of the world's hot spots: what happened, who said what, and what to watch next.",
  alternates: { canonical: BASE },
};

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function GeopoliticsPage() {
  const report = await latestDaily(DOMAIN);
  if (report) return <GeopoliticsDay report={report} />;

  return (
    <div className="intel-page">
      <div className="intel-strip" role="group" aria-label="Report status">
        <span className="intel-strip-title">Geopolitics · Daily</span>
      </div>
      <p className="intel-empty">No daily report has been published yet. Check back soon.</p>
      <p className="geo-xlink">
        <Link href="/intel">Intelligence board: Pulses, Theaters and Briefs →</Link>
      </p>
    </div>
  );
}
