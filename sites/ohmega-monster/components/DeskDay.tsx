import Link from "next/link";

import DailyHeadlines from "@/components/DailyHeadlines";
import DailyReport from "@/components/DailyReport";
import DayKeys from "@/components/DayKeys";
import DayNav from "@/components/DayNav";
import DomainSwitch from "@/components/DomainSwitch";
import GlobeSpinner from "@/components/GlobeSpinner";
import { allDailyDates, dayHref, type Daily } from "@/lib/daily";
import { dailyBase, type Desk } from "@/lib/desks";

// One day's report of one desk, shared by /daily/<desk> (the newest) and /daily/<desk>/<date>: a day navigator above and below the
// report, left and right keys for the previous and next day, and cross-links to the rest of the site. Every desk runs the same Daily
// recipe over its own sources (backend `intel daily --domain <id>`), so this is one component, not one per desk. The only desk-specific
// parts are the geopolitics globe mark and the headlines strip (other outlets' headlines are a geopolitics product).
export default async function DeskDay({ desk, report }: { desk: Desk; report: Daily }) {
  const base = dailyBase(desk.id);
  const dates = await allDailyDates(desk.id);
  const i = dates.indexOf(report.date);
  const older = i >= 0 && i < dates.length - 1 ? dayHref(base, dates[i + 1], dates) : null;
  const newer = i > 0 ? dayHref(base, dates[i - 1], dates) : null;
  const geo = desk.id === "geopolitics";
  return (
    <div className="intel-page">
      <DayKeys prev={older} next={newer} />
      <DomainSwitch current={desk.id} />
      <DayNav dates={dates} current={report.date} domain={desk.id} base={base} placement="top" />
      <DailyReport
        report={report}
        title={desk.label}
        mark={
          geo ? (
            <Link href="/globe" className="globe-link" aria-label="Open the interactive globe" title="Open the interactive globe">
              <GlobeSpinner cycle decorative size={144} className="globe-mark" />
            </Link>
          ) : undefined
        }
      />
      {geo && i === 0 && <DailyHeadlines />}
      <DayNav dates={dates} current={report.date} domain={desk.id} base={base} placement="bottom" />
      <p className="geo-xlink">
        <Link href="/situations">Situations: each story&apos;s living file →</Link> · <Link href={`${base}/archive`}>All {desk.label} days →</Link>
        {desk.id === "ai" && (
          <>
            {" "}
            · <Link href="/intel/ai">AI benchmarks: the scores behind this report →</Link>
          </>
        )}
        {" "}
        · <Link href="/data">Data →</Link>
      </p>
    </div>
  );
}
