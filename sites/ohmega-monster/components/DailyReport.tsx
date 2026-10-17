import PageTag from "./PageTag";
import Link from "next/link";
import { Fragment, type ReactNode } from "react";

import LinkedText from "@/components/entities/LinkedText";
import Popover from "@/components/Popover";
import Term from "@/components/Term";
import type { Daily } from "@/lib/daily";
import { claimOf, crossParts, editionTag, firstSentences, fmtDay, isCut, publishedLine, shortTheater, theaterAnchor } from "@/lib/daily";
import { dossier, dossierIds } from "@/lib/dossier";
import { theaterInfra, type TheaterInfra } from "@/lib/geoledger";
import { latestSnapshot } from "@/lib/intel";

import DailyGlance from "./DailyGlance";
import DailyThirty from "./DailyThirty";
import Expander from "./Expander";
import DailySweepBlock from "./DailySweep";
import DailyTheaterSection from "./DailyTheater";
import DailyWatching from "./DailyWatching";

// The daily report page body. Screen one is the day in 30 seconds (headline, one line per theater);
// the theater table and the longer day sit behind expanders. Each theater follows as a claim, a picture
// and its top developments, the rest behind expanders (Expander.tsx). See
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
        <Popover label="The day, in full" triggerClassName="geo-link-btn xt" trigger={<>The day in full ({items.length}) ›</>}>
          <div className="geo-pd">
            <p className="geo-pd-title">The day</p>
            <ul className="geo-plain">
              {items.map((s, i) => (
                <li key={i}><LinkedText text={s} /></li>
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
                    <p className="geo-pd-text"><LinkedText text={text} /></p>
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

/** The big-picture line for a section whose record carries none (an older report): the first sentences of the theater's
 *  stored dossier primer, background we already hold, so it costs nothing. Only for theaters that have a dossier. */
async function backgrounds(report: Daily, dossiers: ReadonlySet<string>): Promise<Record<string, string>> {
  const need = report.theaters.filter((t) => !t.saga && dossiers.has(t.theater_id));
  const found = await Promise.all(need.map(async (t) => [t.theater_id, firstSentences((await dossier(t.theater_id))?.primer?.text ?? "", 2)] as const));
  return Object.fromEntries(found.filter(([, text]) => text));
}

/** Each theater's infrastructure for its map and status log (the geoledger, lib/geoledger.ts), keyed by theater id; a theater
 *  with no map frame, or no database behind the site, simply has none. Updates of a theater share its frame. */
async function infrastructure(report: Daily): Promise<Record<string, TheaterInfra>> {
  const found = await Promise.all(report.theaters.map(async (t) => [t.theater_id, await theaterInfra(t.map?.bbox, report.date)] as const));
  return Object.fromEntries(found.filter(([, i]) => i.assets.length > 0 || i.log.length > 0));
}

/** `mark`: an optional small decoration at the start of the status strip (the geopolitics page puts its cycling globe there). */
export default async function DailyReport({ report, title, mark }: { report: Daily; title: string; mark?: ReactNode }) {
  const snap = await latestSnapshot();
  const dossiers = new Set(await dossierIds());
  const published = publishedLine(report);
  const background = await backgrounds(report, dossiers);
  const infra = await infrastructure(report);
  return (
    <div className="geo">
      <div className="intel-strip" role="group" aria-label="Report status">
        {mark}
        <span className="intel-strip-title"><PageTag kind="daily" detail={title} /></span>
        <span className="intel-strip-item">{fmtDay(report.date)}</span>
        {published && <span className="intel-strip-item">{published}</span>}
        <span className="intel-trust">
          <Term id={report.researched ? "researched" : "fromHeadlines"} label={report.researched ? "researched" : "from headlines"}>
            {report.researched ? "Researched" : "From headlines"}
          </Term>
        </span>
        <span className="geo-key">
          <i className="geo-v is-solid" aria-hidden="true" /> <Term id="researched">researched</Term>
          <i className="geo-v is-hollow" aria-hidden="true" /> <Term id="reported">reported</Term>
        </span>
      </div>

      {report.headline && <h1 className="geo-headline">{report.headline}</h1>}

      {report.theaters.length === 0 ? (
        <p className="intel-empty">No theaters were covered in this report.</p>
      ) : (
        <>
          <DailyThirty report={report} />
          <div className="geo-exps geo-exps-top">
            <Expander label="All theaters side by side" hint="state, direction, Pulses, coverage">
              <DailyGlance report={report} snap={snap} />
            </Expander>
            {report.the_day.length > 0 && (
              <Expander label="The day, in more detail" count={report.the_day.length}>
                <TheDay items={report.the_day} />
              </Expander>
            )}
          </div>
        </>
      )}

      {report.theaters.map((t, i) => (
        <Fragment key={t.theater_id + i}>
          {t.spotlight && <p className="geo-spotlight-label geo-micro">
              <Term id="spotlight">Spotlight</Term> · an under-covered story, researched in full
            </p>}
          <DailyTheaterSection t={t} id={theaterAnchor(t, i)} date={report.date} snap={snap} dossiers={dossiers} first={i === 0} tag={editionTag(report, t.edition)} background={background[t.theater_id] ?? ""} infra={infra[t.theater_id]} events={report.theaters.filter((x) => x.theater_id === t.theater_id).length === 1} />
          {t.updates.map((u, k) => (
            <DailyTheaterSection key={`${u.theater_id}-u${k}`} t={u} id={`${theaterAnchor(t, i)}-update-${k + 1}`} date={report.date} snap={snap} dossiers={dossiers} tag={editionTag(report, u.edition)} update infra={infra[t.theater_id]} />
          ))}
        </Fragment>
      ))}

      {report.sweep && <DailySweepBlock sweep={report.sweep} />}

      <Across report={report} />
      <DailyWatching watch={report.watch} quiet={report.quiet} dossiers={dossiers} />
    </div>
  );
}
