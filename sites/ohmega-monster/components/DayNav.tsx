import Link from "next/link";

import Popover from "@/components/Popover";
import { dayHref, dayStep, fmtDay } from "@/lib/daily";

import DailyArchive from "./DailyArchive";

// The day navigator: ← previous report · this day (Latest marked) · next report →, plus an "All days"
// popover. `dates` is every report date, newest first; steps skip days without a report. The newest
// report lives at `base` itself; the rest at `base/<date>`. Server component; the keyboard shortcut
// is mounted once by the page (DayKeys), not here.
export default function DayNav({
  dates,
  current,
  domain,
  base,
  placement,
}: {
  dates: string[];
  current: string;
  domain: string;
  base: string;
  placement: "top" | "bottom";
}) {
  const i = dates.indexOf(current);
  if (i < 0) return null;
  const newer = i > 0 ? dates[i - 1] : null;
  const older = i < dates.length - 1 ? dates[i + 1] : null;
  const isLatest = i === 0;

  return (
    <nav className={`geo-daynav is-${placement}`} aria-label={placement === "top" ? "Report days" : "More report days"}>
      {older ? (
        <Link href={dayHref(base, older, dates)} rel="prev" className="geo-daynav-step geo-daynav-prev" title={`Previous report: ${fmtDay(older)}`}>
          <span aria-hidden="true">← </span>
          {dayStep(older)}
        </Link>
      ) : (
        <span className="geo-daynav-prev" aria-hidden="true" />
      )}

      <span className="geo-daynav-mid">
        <time className="geo-daynav-cur" dateTime={current}>
          {fmtDay(current)}
        </time>
        {isLatest ? (
          <span className="geo-micro">Latest</span>
        ) : (
          // Says where it goes: a bare "Latest" beside an older date read as a label claiming that date was newest.
          <Link href={base} className="geo-daynav-latest" title="Jump to the newest report">
            Jump to latest ⇥
          </Link>
        )}
        {dates.length > 1 && (
          <Popover key={current} label="All days" wide triggerClassName="geo-daynav-all" trigger={<>All days ▾</>}>
            <DailyArchive dates={dates} current={current} domain={domain} base={base} />
          </Popover>
        )}
      </span>

      {newer ? (
        <Link href={dayHref(base, newer, dates)} rel="next" className="geo-daynav-step geo-daynav-next" title={`Next report: ${fmtDay(newer)}`}>
          {dayStep(newer)}
          <span aria-hidden="true"> →</span>
        </Link>
      ) : (
        <span className="geo-daynav-next" aria-hidden="true" />
      )}
    </nav>
  );
}
