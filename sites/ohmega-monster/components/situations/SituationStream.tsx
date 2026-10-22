import Link from "next/link";
import { Fragment } from "react";

import DailyTheaterSection from "@/components/DailyTheater";
import { Section } from "@/components/dossier/parts";
import Age from "@/components/Fresh";
import { editionTag, fmtDay } from "@/lib/daily";
import { dailyHref } from "@/lib/desks";
import { CADENCE_HOURS } from "@/lib/fresh";
import { theaterInfra, type TheaterInfra } from "@/lib/geoledger";
import type { Snapshot } from "@/lib/intel";
import type { StreamDay } from "@/lib/situations";

// A situation's stream: every Daily section written about it, newest first, in ONE list (no separate "latest", "history" and
// "timeline" blocks). The newest day is fully open, with its live strips; older days are compact (no live strips) but each still shows
// its visuals, map, numbers, grid impact and status log inline, because they are the same section component the Daily uses
// (components/DailyTheater.tsx). Briefs, which are dated entries of their own, sit below the stream. Server component.

type Brief = { slug: string; title: string; as_of: string };

async function infrastructure(days: StreamDay[]): Promise<TheaterInfra[]> {
  return Promise.all(days.map(({ t, date }) => theaterInfra(t.map?.bbox, date)));
}

export default async function SituationStream({ days, briefs, snap, dossiers }: { days: StreamDay[]; briefs: Brief[]; snap: Snapshot | null; dossiers: ReadonlySet<string> }) {
  if (days.length === 0 && briefs.length === 0) return null;
  const infra = await infrastructure(days);
  const n = days.length;
  const newest = days[0];
  return (
    <Section
      id="stream"
      title="Every day on file"
      lead={n > 0 ? `${n} day${n === 1 ? "" : "s"} from the Daily, newest first. Each day keeps its own pictures and numbers.` : "No Daily has covered this situation yet; its researched briefs are below."}
      aside={newest ? <Age stamp={newest.date} cadenceHours={CADENCE_HOURS.situation} prefix="Last report " /> : undefined}
    >
      {days.map((day, i) => {
        const { desk, date, report, t, anchor } = day;
        const stream = { dayLabel: `${fmtDay(date)}${desk.id === "geopolitics" ? "" : ` · ${desk.label}`}`, dayHref: `${dailyHref(desk.id, date)}#${anchor}`, newest: i === 0 };
        const id = `day-${date}-${desk.id}`;
        return (
          <Fragment key={id}>
            <DailyTheaterSection
              t={t}
              id={id}
              date={date}
              snap={snap}
              dossiers={dossiers}
              first={i === 0}
              tag={editionTag(report, t.edition)}
              infra={infra[i]}
              events={report.theaters.filter((x) => x.theater_id === t.theater_id).length === 1}
              stream={stream}
            />
            {t.updates.map((u, k) => (
              <DailyTheaterSection key={`${id}-u${k}`} t={u} id={`${id}-update-${k + 1}`} date={date} snap={snap} dossiers={dossiers} tag={editionTag(report, u.edition)} update infra={infra[i]} stream={stream} />
            ))}
          </Fragment>
        );
      })}
      {briefs.length > 0 && (
        <div className="sit-briefs">
          <p className="th-sub">Researched briefs</p>
          <ul className="th-days">
            {briefs.map((b) => (
              <li key={b.slug} className="th-day th-day-brief">
                <span className="th-day-date">{fmtDay(b.as_of.slice(0, 10))}</span>
                <span className="th-day-tag">Brief</span>
                <Link href={`/intel/briefs/${b.slug}`} className="th-day-head">
                  {b.title} →
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  );
}
