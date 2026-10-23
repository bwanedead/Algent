import Link from "next/link";
import { Fragment } from "react";

import DailyTheaterSection from "@/components/DailyTheater";
import { Section } from "@/components/dossier/parts";
import Age from "@/components/Fresh";
import { claimOf, fmtDay } from "@/lib/daily";
import { dailyHref } from "@/lib/desks";
import { CADENCE_HOURS } from "@/lib/fresh";
import { theaterInfra, type TheaterInfra } from "@/lib/geoledger";
import type { Snapshot } from "@/lib/intel";
import type { SituationStream as Stream } from "@/lib/situations";

// A situation's stream: every Daily section written about it, newest first, in ONE list (no separate "latest", "history" and "timeline" blocks).
// The server sends the newest days in full - each shows its visuals, map, numbers, grid impact and status log inline, because they are the same section
// component the Daily uses (components/DailyTheater.tsx) - and every earlier day as a row that opens that day's report at this situation's section
// (docs/architecture/views.md: a view is small; the full section of an old day is one click away in the Daily, which is its home). Briefs, which are
// dated entries of their own, sit below the stream. Server component.

type Brief = { slug: string; title: string; as_of: string };

async function infrastructure(days: Stream["days"]): Promise<TheaterInfra[]> {
  return Promise.all(days.map(({ t, date }) => theaterInfra(t.map?.bbox, date)));
}

export default async function SituationStream({ stream, briefs, snap, dossiers }: { stream: Stream; briefs: Brief[]; snap: Snapshot | null; dossiers: ReadonlySet<string> }) {
  const { days, earlier } = stream;
  if (days.length === 0 && earlier.length === 0 && briefs.length === 0) return null;
  const infra = await infrastructure(days);
  const n = stream.total;
  const newest = days[0] ?? null;
  return (
    <Section
      id="stream"
      title="Every day on file"
      lead={n > 0 ? `${n} day${n === 1 ? "" : "s"} from the Daily, newest first. The latest ${days.length === 1 ? "is" : `${days.length} are`} open here with their pictures and numbers; earlier days open in their Daily.` : "No Daily has covered this situation yet; its researched briefs are below."}
      aside={newest ? <Age stamp={newest.date} cadenceHours={CADENCE_HOURS.situation} prefix="Last report " /> : undefined}
    >
      {days.map((day, i) => {
        const { desk, date, t, anchor } = day;
        const link = { dayLabel: `${fmtDay(date)}${desk.id === "geopolitics" ? "" : ` · ${desk.label}`}`, dayHref: `${dailyHref(desk.id, date)}#${anchor}`, newest: i === 0 };
        const id = `day-${date}-${desk.id}`;
        return (
          <Fragment key={id}>
            <DailyTheaterSection t={t} id={id} date={date} snap={snap} dossiers={dossiers} first={i === 0} tag={day.edition} infra={infra[i]} events={day.events} stream={link} />
            {t.updates.map((u, k) => (
              <DailyTheaterSection key={`${id}-u${k}`} t={u} id={`${id}-update-${k + 1}`} date={date} snap={snap} dossiers={dossiers} tag={day.updateTags[k] ?? ""} update infra={infra[i]} stream={link} />
            ))}
          </Fragment>
        );
      })}
      {earlier.length > 0 && (
        <div className="sit-briefs">
          <p className="th-sub">
            Earlier days{stream.earlierTotal > earlier.length ? ` (the newest ${earlier.length} of ${stream.earlierTotal})` : ` (${earlier.length})`}
          </p>
          <ul className="th-days">
            {earlier.map((e) => (
              <li key={`${e.date}-${e.desk.id}`} className="th-day">
                <span className="th-day-date">{fmtDay(e.date)}</span>
                {e.desk.id !== "geopolitics" && <span className="th-day-tag">{e.desk.label}</span>}
                <Link href={e.href} className="th-day-head">
                  {claimOf(e.headline, 150)} →
                </Link>
                {e.visuals.length > 0 && <span className="th-day-tag">{e.visuals.length === 1 ? e.visuals[0].title || "1 picture" : `${e.visuals.length} pictures`}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
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
