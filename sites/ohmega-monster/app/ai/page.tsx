import PageTag from "@/components/PageTag";
import type { Metadata } from "next";
import Link from "next/link";

import DomainSwitch from "@/components/DomainSwitch";
import { latestDaily } from "@/lib/daily";

import "../geopolitics/geopolitics.css";
import AiDay, { BASE, DOMAIN } from "./AiDay";

export const metadata: Metadata = {
  title: "The AI Daily",
  description: "A daily rundown of artificial intelligence: the labs' race, chips and compute, policy, security, open weights and capital, with the benchmark scores behind it.",
  alternates: { canonical: BASE, types: { "application/json": `/api/v1/daily/${DOMAIN}/latest` } },
};

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function AiPage() {
  const report = await latestDaily(DOMAIN);
  if (report) return <AiDay report={report} />;

  return (
    <div className="intel-page">
      <DomainSwitch current="ai" />
      <div className="intel-strip" role="group" aria-label="Report status">
        <span className="intel-strip-title"><PageTag kind="daily" detail="AI" /></span>
      </div>
      <p className="intel-empty">No AI report has been published yet.</p>
      <p className="geo-xlink">
        <Link href="/intel/ai">AI benchmarks: scores across public leaderboards →</Link> · <Link href="/intel">Data &amp; tools →</Link>
      </p>
    </div>
  );
}
