import Link from "next/link";
import { Fragment } from "react";

import Popover from "@/components/Popover";
import type { Daily } from "@/lib/daily";
import { claimOf, crossParts, fmtDay, isCut, shortTheater, theaterAnchor } from "@/lib/daily";
import { fmtUtc, latestSnapshot } from "@/lib/intel";

import DailyGlance from "./DailyGlance";
import DailyTheaterSection from "./DailyTheater";
import DailyWatching from "./DailyWatching";

// The daily report page body. Screen one is the day at a glance (headline, theater table, the
// day in four lines); each theater follows as a claim, a picture and a timeline. See
// docs/ethos/information-ergonomics-ethos.md.

const DAY_SHOWN = 4;

function TheDay({ items }: { items: string[] }) {
  const shown = items.slice(0, DAY_SHOWN).map((s) => ({ full: s, short: claimOf(s, 140) }));
  const more = items.length > DAY_SHOWN || shown.some((x) => isCut(x.full, x.short));
  return (
    <div className="geo-day">
      <span className="geo-micro">The day</span>
      <ul>
        {shown.map((x, i) => (
          <li key={i}>{x.short}</li>
        ))}
      </ul>
      {more && (
        <Popover label="The day, in full" triggerClassName="geo-link-btn" trigger={<>The day in full ({items.length}) ›</>}>
          <div className="geo-pd">
            <p className="geo-pd-title">The day</p>
            <ul className="geo-plain">
              {items.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </div>
        </Popover>
      )}
    </div>
  );
}

function Across({ report }: { report: Daily }) {
  if (report.cross_theater.length === 0) return null;
  const idx = (name: string) => report.theaters.findIndex((t) => t.name === name);
  return (
    <section className="geo-across" aria-label="Across theaters">
      <h2 className="geo-h2">Across theaters</h2>
      <ul>
        {report.cross_theater.map((c, k) => {
          const { mutual, text } = crossParts(c);
          const one = claimOf(text, 140);
          return (
            <li key={k} className="geo-x">
              <span className="geo-x-names">
                {c.theaters.map((n, j) => {
                  const i = idx(n);
                  return (
                    <Fragment key={j}>
                      {j > 0 && (
                        <span className="geo-x-arrow" title={mutual ? "Each bears on the other" : "Bears on"}>
                          {mutual ? "↔" : "→"}
                        </span>
                      )}
                      {i >= 0 ? (
                        <Link href={`#${theaterAnchor(report.theaters[i], i)}`} title={n}>
                          {shortTheater(n)}
                        </Link>
                      ) : (
                        <span>{shortTheater(n)}</span>
                      )}
                    </Fragment>
                  );
                })}
              </span>
              {isCut(text, one) ? (
                <Popover
                  label={`How they connect: ${c.theaters.map(shortTheater).join(", ")}`}
                  triggerClassName="geo-x-btn"
                  trigger={
                    <>
                      <span className="geo-x-line">{one}</span>
                      <span className="geo-more" aria-hidden="true">
                        ›
                      </span>
                    </>
                  }
                >
                  <div className="geo-pd">
                    <p className="geo-pd-title">{c.theaters.map(shortTheater).join(mutual ? " ↔ " : " → ")}</p>
                    <p className="geo-pd-text">{text}</p>
                  </div>
                </Popover>
              ) : (
                <span className="geo-x-line">{one}</span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default function DailyReport({ report, title }: { report: Daily; title: string }) {
  const snap = latestSnapshot();
  return (
    <div className="geo">
      <div className="intel-strip" role="group" aria-label="Report status">
        <span className="intel-strip-title">{title} · Daily</span>
        <span className="intel-strip-item">{fmtDay(report.date)}</span>
        <span className="intel-strip-item">
          <span className="geo-micro">Built</span> {report.built_at ? fmtUtc(report.built_at) : "—"}
        </span>
        <span className="intel-trust" title={report.researched ? "Developments were checked against sources" : "Built from headlines; not independently checked"}>
          {report.researched ? "Researched" : "From headlines"}
        </span>
        <span className="geo-key" title="Marks on developments and map">
          <i className="geo-v is-solid" aria-hidden="true" /> researched
          <i className="geo-v is-hollow" aria-hidden="true" /> reported
        </span>
      </div>

      {report.headline && <h1 className="geo-headline">{report.headline}</h1>}

      {report.theaters.length === 0 ? (
        <p className="intel-empty">No theaters were covered in this report.</p>
      ) : (
        <DailyGlance report={report} snap={snap} />
      )}

      {report.the_day.length > 0 && <TheDay items={report.the_day} />}

      {report.theaters.map((t, i) => (
        <DailyTheaterSection key={t.theater_id + i} t={t} id={theaterAnchor(t, i)} date={report.date} snap={snap} />
      ))}

      <Across report={report} />
      <DailyWatching watch={report.watch} quiet={report.quiet} />
    </div>
  );
}
