import type { Metadata } from "next";
import Link from "next/link";

import DailyArchive from "@/components/DailyArchive";
import DailyReport from "@/components/DailyReport";
import { allDailyDates, latestDaily } from "@/lib/daily";

import "./geopolitics.css";

const DOMAIN = "geopolitics";

export const metadata: Metadata = {
  title: "Geopolitics — daily report",
  description: "A daily rundown of the world's hot spots: what happened, who said what, and what to watch next.",
};

export default function GeopoliticsPage() {
  const report = latestDaily(DOMAIN);
  const past = allDailyDates(DOMAIN).filter((d) => d !== report?.date);

  return (
    <div className="intel-page">
      {report ? (
        <DailyReport report={report} title="Geopolitics" />
      ) : (
        <>
          <div className="intel-strip" role="group" aria-label="Report status">
            <span className="intel-strip-title">Geopolitics · Daily</span>
          </div>
          <p className="intel-empty">No daily report has been published yet. Check back soon.</p>
        </>
      )}

      <DailyArchive dates={past} domain={DOMAIN} href="/geopolitics" />

      <p className="geo-xlink">
        <Link href="/intel">Intelligence board: Pulses, Theaters and Briefs →</Link>
      </p>
    </div>
  );
}
