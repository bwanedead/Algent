import Link from "next/link";

import { fmtDay } from "@/lib/daily";
import { DIRECTION } from "@/lib/dossier-view";
import type { TheaterDay } from "@/lib/theater-history";

import { Section } from "./parts";

// The theater's file as the Daily wrote it: "Latest" (the newest day's section, open) and then every earlier day,
// newest first, each collapsible and linking to its Daily. Briefs are dated entries on the same line. Server
// component; no client state (native <details>).

type Brief = { slug: string; title: string; as_of: string };
type Entry = { kind: "day"; date: string; day: TheaterDay } | { kind: "brief"; date: string; brief: Brief };

const KIND_MARK: Record<string, string> = { escalated: "▲", eased: "▼", new: "●", resolved: "✓", unchanged: "=" };

function DayBody({ day }: { day: TheaterDay }) {
  return (
    <div className="th-day-body">
      {day.bottomLine && <p className="th-day-bl">{day.bottomLine}</p>}
      {day.changes.length > 0 && (
        <ul className="th-day-changes">
          {day.changes.map((c, i) => (
            <li key={i}>
              <span className="th-day-mark" aria-hidden="true">{KIND_MARK[c.kind] ?? "•"}</span> {c.what}
            </li>
          ))}
        </ul>
      )}
      {day.developments.length > 0 && (
        <ul className="th-day-devs">
          {day.developments.map((d, i) => (
            <li key={i}>
              <span className={`geo-v ${d.verified ? "is-solid" : "is-hollow"}`} aria-hidden="true" /> {d.headline}
            </li>
          ))}
        </ul>
      )}
      <p className="th-day-link">
        <Link href={day.href}>Open this day&apos;s report →</Link>
        {day.updates > 0 && <span className="geo-muted"> · updated {day.updates}× later that day</span>}
      </p>
    </div>
  );
}

export function TheaterLatest({ day }: { day: TheaterDay | undefined }) {
  if (!day) return null;
  const dir = DIRECTION[day.direction];
  return (
    <Section id="latest" title="Latest" aside={<span className="th-key">{fmtDay(day.date)} · {dir.glyph} {dir.word}</span>}>
      <h3 className="th-day-claim">{day.claim}</h3>
      <DayBody day={day} />
    </Section>
  );
}

export function TheaterHistory({ days, briefs }: { days: TheaterDay[]; briefs: Brief[] }) {
  const earlier = days.slice(1);
  const entries: Entry[] = [
    ...earlier.map((day): Entry => ({ kind: "day", date: day.date, day })),
    ...briefs.map((brief): Entry => ({ kind: "brief", date: brief.as_of.slice(0, 10), brief })),
  ].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : a.kind === "day" ? -1 : 1));
  if (entries.length === 0) return null;
  const n = earlier.length;
  return (
    <Section
      id="history"
      title="Timeline: every day on file"
      lead={`${n} earlier day${n === 1 ? "" : "s"} from the Daily${briefs.length > 0 ? ` and ${briefs.length} researched brief${briefs.length === 1 ? "" : "s"}` : ""}, newest first.`}
    >
      <ol className="th-days">
        {entries.map((e) =>
          e.kind === "day" ? (
            <li key={`d-${e.date}`}>
              <details className="th-day">
                <summary>
                  <span className="th-day-date">{fmtDay(e.date)}</span>
                  <span className="th-day-tag">Daily</span>
                  <span className="th-day-head">
                    <span aria-hidden="true">{DIRECTION[e.day.direction].glyph}</span> {e.day.claim}
                  </span>
                </summary>
                <DayBody day={e.day} />
              </details>
            </li>
          ) : (
            <li key={`b-${e.brief.slug}`} className="th-day th-day-brief">
              <span className="th-day-date">{fmtDay(e.date)}</span>
              <span className="th-day-tag">Brief</span>
              <Link href={`/intel/briefs/${e.brief.slug}`} className="th-day-head">{e.brief.title} →</Link>
            </li>
          ),
        )}
      </ol>
    </Section>
  );
}
