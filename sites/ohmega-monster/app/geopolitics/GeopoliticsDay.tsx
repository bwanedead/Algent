import Link from "next/link";

import DailyReport from "@/components/DailyReport";
import DayKeys from "@/components/DayKeys";
import DayNav from "@/components/DayNav";
import { allDailyDates, dayHref, type Daily } from "@/lib/daily";

export const DOMAIN = "geopolitics";
export const BASE = "/geopolitics";

// One day's report page, shared by /geopolitics (the newest) and /geopolitics/<date>: a day navigator
// above and below the report, ← / → keys for previous / next day, and the cross-link to the board.
export default async function GeopoliticsDay({ report }: { report: Daily }) {
  const dates = await allDailyDates(DOMAIN);
  const i = dates.indexOf(report.date);
  const older = i >= 0 && i < dates.length - 1 ? dayHref(BASE, dates[i + 1], dates) : null;
  const newer = i > 0 ? dayHref(BASE, dates[i - 1], dates) : null;
  return (
    <div className="intel-page">
      <DayKeys prev={older} next={newer} />
      <DayNav dates={dates} current={report.date} domain={DOMAIN} base={BASE} placement="top" />
      <DailyReport report={report} title="Geopolitics" />
      <DayNav dates={dates} current={report.date} domain={DOMAIN} base={BASE} placement="bottom" />
      <p className="geo-xlink">
        <Link href="/intel">Intelligence board: Pulses, Theaters and Briefs →</Link>
      </p>
    </div>
  );
}
