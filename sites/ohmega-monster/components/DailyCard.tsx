import Link from "next/link";

import { fmtDay, latestDaily } from "@/lib/daily";

// Home-page teaser for a daily report. Renders nothing until a report exists.
export default function DailyCard({ domain, title, href }: { domain: string; title: string; href: string }) {
  const report = latestDaily(domain);
  if (!report || !report.headline) return null;
  return (
    <aside className="intel-card" aria-label={`${title} daily report`}>
      <Link href={href} className="intel-card-link daily-card-link">
        <span className="intel-micro intel-card-title">{title} · Daily →</span>
        <span className="intel-card-theater">
          <span className="intel-micro">{fmtDay(report.date)}</span>
          <strong>{report.headline}</strong>
        </span>
      </Link>
    </aside>
  );
}
