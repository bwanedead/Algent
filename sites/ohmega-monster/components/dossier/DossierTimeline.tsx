import Popover from "@/components/Popover";
import { SourceLink } from "@/components/DailyVisuals";
import { claimOf } from "@/lib/daily";
import { linkTarget, type TimelineItem } from "@/lib/dossier";
import { dayLabel, fromLabel, groupByWeek, isoDay } from "@/lib/dossier-view";

import { Anchor, Overflow, Section, VerifyKey } from "./parts";

// "How we got here": the merged record of everything the reports and briefs have established, newest
// first, one line per event (date, headline, a solid/hollow mark for researched/reported). Weeks are
// separated by a quiet label. Detail and sources wait in a popover; everything past the first screen
// sits behind "Earlier".

const SHOWN = 15;

type Row = { t: TimelineItem; day: string; key: number };

function sortRows(items: TimelineItem[]): Row[] {
  return items
    .map((t, key) => ({ t, day: isoDay(t.date), key }))
    .sort((a, b) => (a.day === b.day ? a.key - b.key : a.day === "" ? 1 : b.day === "" ? -1 : a.day < b.day ? 1 : -1));
}

function Detail({ t }: { t: TimelineItem }) {
  const verified = t.verification === "researched";
  return (
    <div className="geo-pd">
      <p className="geo-pd-title">{t.headline}</p>
      <p className="geo-pd-meta">
        <span className={`geo-v ${verified ? "is-solid" : "is-hollow"}`} aria-hidden="true" />
        <span>{verified ? "Researched" : "Reported, not independently checked"}</span>
        {(t.date || t.where) && <span className="geo-micro"> · {[t.date && dayLabel(isoDay(t.date) || t.date), t.where].filter(Boolean).join(" · ")}</span>}
      </p>
      {t.detail && <p className="geo-pd-text">{t.detail}</p>}
      {t.sources.length > 0 && (
        <p className="geo-pd-foot">
          {t.sources.map((u, i) => (
            <SourceLink key={i} url={u} />
          ))}
        </p>
      )}
      {t.from && (
        <p className="geo-pd-foot">
          <span className="geo-micro">From</span> {linkTarget(t.from) ? <Anchor url={t.from}>{fromLabel(t.from)}</Anchor> : <span className="geo-muted">{fromLabel(t.from)}</span>}
        </p>
      )}
    </div>
  );
}

function Groups({ rows }: { rows: Row[] }) {
  return (
    <>
      {groupByWeek(rows, (r) => r.day).map((g, gi) => {
        let prev = "";
        return (
          <div key={gi} className="th-week">
            <p className="th-week-label">{g.week ? `Week of ${dayLabel(g.week)}` : "Undated"}</p>
            <ol className="geo-tl">
              {g.items.map((r) => {
                const label = r.day && r.day !== prev ? dayLabel(r.day) : "";
                prev = r.day;
                const verified = r.t.verification === "researched";
                return (
                  <li key={r.key} className="geo-ev">
                    <span className="geo-ev-day">{label}</span>
                    <span className={`geo-ev-mark ${verified ? "is-solid" : "is-hollow"}`} title={verified ? "Researched" : "Reported, not independently checked"} />
                    <Popover
                      label={r.t.headline}
                      triggerClassName="geo-ev-btn"
                      trigger={
                        <>
                          <span className="geo-ev-head">{r.t.headline}</span>
                          <span className="geo-more" aria-hidden="true">
                            ›
                          </span>
                        </>
                      }
                    >
                      <Detail t={r.t} />
                    </Popover>
                  </li>
                );
              })}
            </ol>
          </div>
        );
      })}
    </>
  );
}

export default function DossierTimeline({ items, since }: { items: TimelineItem[]; since: string }) {
  if (items.length === 0) return null;
  const rows = sortRows(items);
  const shown = rows.slice(0, SHOWN);
  const rest = rows.slice(SHOWN);
  const researched = items.filter((t) => t.verification === "researched").length;
  const latest = claimOf(rows[0].t.headline, 110);
  return (
    <Section
      id="timeline"
      title="How we got here"
      lead={`${items.length} event${items.length === 1 ? "" : "s"}${since ? ` since ${dayLabel(since)}` : ""}, ${researched} researched. Latest: ${latest}`}
      aside={<VerifyKey />}
    >
      <Groups rows={shown} />
      {rest.length > 0 && (
        <Overflow label={`Earlier events (${rest.length})`} trigger={`Earlier (${rest.length})`} wide>
          <Groups rows={rest} />
        </Overflow>
      )}
    </Section>
  );
}
