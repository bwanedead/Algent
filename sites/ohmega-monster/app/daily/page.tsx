import type { Metadata } from "next";
import Link from "next/link";

import Age from "@/components/Fresh";
import NewDot from "@/components/NewDot";
import PageTag from "@/components/PageTag";
import { DirMark } from "@/components/vl/primitives";
import { claimOf, dailyFromView, fmtDay, headlineOf, shortTheater, theaterAnchor, type Daily } from "@/lib/daily";
import { cadenceLine, dailyBase, dailyHref, DESKS, type Desk } from "@/lib/desks";
import { CADENCE_HOURS, isStale, newest } from "@/lib/fresh";
import { getMenus } from "@/lib/radar";
import { dailyHubView, type DailyHubView } from "@/lib/views";

import "@/app/situations/situations.css";
import "@/components/hubs.css";
import "./daily.css";

export const metadata: Metadata = {
  title: "The Daily",
  description: "One report per desk per day: geopolitics and AI. Pick a desk for today's headline, its sections and its archive.",
  alternates: { canonical: "/daily" },
};

export const revalidate = 1800; // lib/store.ts TTL.daily: a desk publishes twice a day

const RECENT_DAYS = 6;

type Part = { n: number; time: string; state: "done" | "due" | "missed"; at: string };

/** Where each part of the day stands for this report: published (with its time), still due today, or not run. Older reports with no
 *  edition record count as a published part 1 at the report's own build time. */
function partsOf(desk: Desk, report: Daily, now: Date): Part[] {
  const today = now.toISOString().slice(0, 10);
  const hhmm = (iso: string) => (iso && !Number.isNaN(Date.parse(iso)) ? `${new Date(iso).toISOString().slice(11, 16)} UTC` : "");
  return desk.parts.map((time, i): Part => {
    const n = i + 1;
    const ed = report.editions.find((e) => e.n === n);
    if (ed) return { n, time, state: "done", at: hhmm(ed.built_at) };
    if (n === 1 && report.editions.length === 0) return { n, time, state: "done", at: hhmm(report.built_at) };
    return { n, time, state: report.date === today ? "due" : "missed", at: "" };
  });
}

function PartLine({ p, single }: { p: Part; single: boolean }) {
  const name = single ? "Report" : `Part ${p.n}`;
  if (p.state === "done") return <li className="is-done">{name} published{p.at ? ` ${p.at}` : ""}</li>;
  if (p.state === "due") return <li>{name} due about {p.time} UTC</li>;
  return <li className="is-late">{name} not run</li>;
}

type HubEntry = DailyHubView["desks"][number];

function DeskCard({ desk, now, entry }: { desk: Desk; now: Date; entry: HubEntry | undefined }) {
  const report = dailyFromView(entry?.report ?? null, desk.id);
  const base = dailyBase(desk.id);
  if (!report) {
    return (
      <article className="hub-card" aria-label={desk.label}>
        <div className="hub-card-head"><h2>{desk.label}</h2></div>
        <p className="hub-cadence">{desk.blurb}</p>
        <p className="intel-empty">No report published yet.</p>
      </article>
    );
  }
  const stamp = report.built_at || report.date;
  const sections = report.theaters.filter((t) => t.kind === "section");
  const parts = partsOf(desk, report, now);
  return (
    <article className="hub-card" aria-label={`${desk.label} Daily`}>
      <div className="hub-card-head">
        <h2>
          <Link href={base}>{desk.label}</Link>
          <NewDot id={`daily:${desk.id}`} stamp={stamp} stale={isStale(stamp, desk.cadenceHours)} />
        </h2>
        <Age stamp={stamp} cadenceHours={desk.cadenceHours} prefix="Latest " />
      </div>
      <p className="hub-cadence">{desk.blurb} Made {cadenceLine(desk)}. {fmtDay(report.date)}.</p>
      {report.headline && (
        <Link href={base} className="hub-headline">
          {claimOf(report.headline, 170)}
        </Link>
      )}
      <ul className="hub-parts" aria-label="Parts of the day">
        {parts.map((p) => (
          <PartLine key={p.n} p={p} single={parts.length === 1} />
        ))}
      </ul>
      {sections.length > 0 && (
        <ul className="hub-list" aria-label={`Sections in the ${desk.label} Daily`}>
          {sections.map((t) => {
            const i = report.theaters.indexOf(t);
            return (
              <li key={t.theater_id + i}>
                <Link href={`${base}#${theaterAnchor(t, i)}`} className="hub-row">
                  <DirMark direction={t.escalation.direction} label />
                  <span className="hub-row-what">
                    <span className="hub-row-name">
                      {shortTheater(t.name)}
                      {t.spotlight && <span className="hub-row-tag">Spotlight</span>}
                      {t.updates.length > 0 && <span className="hub-row-tag">Updated</span>}
                    </span>
                    <span className="hub-row-claim">{headlineOf(t.headline, t.bottom_line, 110)}</span>
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      <p className="hub-foot">
        <Link href={base}>Read the {desk.label} Daily →</Link>
        <Link href={`${base}/archive`}>All {entry?.dates_total ?? 0} days →</Link>
      </p>
      {entry && entry.recent.length > 0 && (
        <ul className="hub-days" aria-label="Recent days">
          {entry.recent.slice(0, RECENT_DAYS).map((d) => (
            <li key={d}>
              <Link href={dailyHref(desk.id, d)}>{d.slice(5)}</Link>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

// The Daily hub: mostly navigation. One card per desk (generated from the desk list, so a new desk appears on its own) with today's
// headline, its sections, where the day's parts stand, how old it is, and the way into the archive by date. The cards come from one server-built view
// (backend views/daily_hub.py: each desk's newest report as a digest and its list of days), not from the reports themselves.
export default async function DailyHub() {
  const now = new Date();
  const [view, menus] = await Promise.all([dailyHubView(), getMenus()]);
  const headlines = menus[0];
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="daily" detail="All desks" />
      </p>
      <h1 className="th-claim">The Daily</h1>
      <p className="th-lead">One report per desk per day. Each section covers one situation that had news that day; follow a section into its situation for the whole story.</p>
      <div className="hub-cards">
        {DESKS.map((d) => (
          <DeskCard key={d.id} desk={d} now={now} entry={view?.desks.find((e) => e.desk === d.id)} />
        ))}
      </div>
      {headlines && (
        <p className="hub-other">
          <Link href="/daily/headlines">Other outlets&apos; headlines</Link> <span className="geo-muted">· unverified, not ours</span>{" "}
          <Age stamp={newest([headlines.builtAt])} cadenceHours={CADENCE_HOURS.headlines} />
        </p>
      )}
    </div>
  );
}
