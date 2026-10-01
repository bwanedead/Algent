import type { Metadata } from "next";
import Link from "next/link";

import DailyReport from "@/components/DailyReport";
import { allDailyDates, daily, fmtDay, latestDaily } from "@/lib/daily";

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

      {past.length > 0 && (
        <section className="intel-section" aria-labelledby="daily-archive">
          <div className="intel-section-head">
            <h2 id="daily-archive">Earlier days</h2>
            <span className="intel-micro">Latest first</span>
          </div>
          <ul className="intel-brief-list">
            {past.map((d) => {
              const r = daily(DOMAIN, d);
              return (
                <li key={d}>
                  <Link href={`/geopolitics/${d}`}>
                    <span className="intel-brief-meta">
                      <time className="intel-micro" dateTime={d}>{fmtDay(d)}</time>
                    </span>
                    <span className="intel-brief-body">
                      <strong>{r?.headline || `Daily report, ${d}`}</strong>
                      {r && r.theaters.length > 0 && <span className="intel-micro"> {r.theaters.length} theaters</span>}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <p className="intel-note daily-xlink">
        <Link href="/intel">Intelligence board — Pulses, Theaters and Briefs →</Link>
      </p>
    </div>
  );
}
