import Link from "next/link";

import { fmtDay, latestDaily } from "@/lib/daily";

import "../app/geopolitics/geopolitics.css";
import DailyGlance from "./DailyGlance";

// Home-page teaser for a daily report: the headline, then the same small-multiples rows as the
// report's first screen (compact). Renders nothing until a report exists.
export default async function DailyCard({ domain, title, href }: { domain: string; title: string; href: string }) {
  const report = await latestDaily(domain);
  if (!report || !report.headline) return null;
  return (
    <aside className="intel-card geo-card" aria-label={`${title} daily report`}>
      <Link href={href} className="geo-card-head">
        <span className="geo-micro">
          {title} · Daily · {fmtDay(report.date)} →
        </span>
        <strong>{report.headline}</strong>
      </Link>
      <DailyGlance report={report} snap={null} base={href} compact />
    </aside>
  );
}
