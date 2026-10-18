import Link from "next/link";

import DailyReport from "@/components/DailyReport";
import DayKeys from "@/components/DayKeys";
import DayNav from "@/components/DayNav";
import DomainSwitch from "@/components/DomainSwitch";
import { allDailyDates, dayHref, type Daily } from "@/lib/daily";

export const DOMAIN = "ai";
export const BASE = "/ai";

// One day's AI report, shared by /ai (the newest) and /ai/<date>: the same Daily recipe as /geopolitics over the AI desk's own sources and theaters
// (backend `intel daily --domain ai`). Its numbers are the benchmark tracker, so it links to /intel/ai.
export default async function AiDay({ report }: { report: Daily }) {
  const dates = await allDailyDates(DOMAIN);
  const i = dates.indexOf(report.date);
  const older = i >= 0 && i < dates.length - 1 ? dayHref(BASE, dates[i + 1], dates) : null;
  const newer = i > 0 ? dayHref(BASE, dates[i - 1], dates) : null;
  return (
    <div className="intel-page">
      <DayKeys prev={older} next={newer} />
      <DomainSwitch current="ai" />
      <DayNav dates={dates} current={report.date} domain={DOMAIN} base={BASE} placement="top" />
      <DailyReport report={report} title="AI" />
      <DayNav dates={dates} current={report.date} domain={DOMAIN} base={BASE} placement="bottom" />
      <p className="geo-xlink">
        <Link href="/intel/ai">AI benchmarks: the scores behind this report →</Link> · <Link href="/intel/theaters">Theaters →</Link> · <Link href="/intel">Data &amp; tools →</Link>
      </p>
    </div>
  );
}
