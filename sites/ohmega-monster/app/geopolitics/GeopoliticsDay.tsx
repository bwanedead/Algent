import Link from "next/link";

import DailyReport from "@/components/DailyReport";
import DailyHeadlines from "@/components/DailyHeadlines";
import DayKeys from "@/components/DayKeys";
import DayNav from "@/components/DayNav";
import DomainSwitch from "@/components/DomainSwitch";
import GlobeSpinner from "@/components/GlobeSpinner";
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
      <DomainSwitch current="geopolitics" />
      <DayNav dates={dates} current={report.date} domain={DOMAIN} base={BASE} placement="top" />
      <DailyReport report={report} title="Geopolitics" mark={<Link href="/globe" className="globe-link" aria-label="Open the interactive globe" title="Open the interactive globe"><GlobeSpinner cycle decorative size={144} className="globe-mark" /></Link>} />
      {i === 0 && <DailyHeadlines />}
      <DayNav dates={dates} current={report.date} domain={DOMAIN} base={BASE} placement="bottom" />
      <p className="geo-xlink">
        <Link href="/intel/theaters">Theaters: each one&apos;s living file →</Link> · <Link href="/intel">Data &amp; tools →</Link>
      </p>
    </div>
  );
}
