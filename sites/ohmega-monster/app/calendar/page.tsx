import PageTag from "@/components/PageTag";
import type { Metadata } from "next";

import CalendarView from "@/components/calendar/CalendarView";
import { calendarWindow, isUnconfirmed, todayIso } from "@/lib/calendar";

import "@/app/daily/daily.css";
import "@/app/situations/situations.css";

export const metadata: Metadata = {
  title: "What's coming",
  description:
    "Elections, central-bank decisions, data releases, commodity reports, summits, court hearings, AI and tech events, launches and the markets we track, for the next six months, each with its source and how far to trust the date.",
  alternates: { canonical: "/calendar", types: { "application/json": "/api/v1/calendar" } },
};

// The forward calendar: dated things ahead from official schedules (central banks, statistics offices, the UN, courts), announcements compiled
// by others (elections, summits, company earnings), dates generated from a published rule (marked estimated) and deadlines our own reports named
// (marked unconfirmed). Merged across sources and ranked by importance (backend `lookahead/`, one document: calendar/next.json). A date is a plan,
// not an outcome.
export const revalidate = 1800; // lib/store.ts TTL.daily: a desk publishes twice a day

export default async function CalendarPage() {
  const today = todayIso();
  const rows = await calendarWindow();
  const ahead = rows.filter((r) => (r.end_date ?? r.on_date) >= today);
  const notable = ahead.filter((r) => r.importance > 1).length;
  const unconfirmed = ahead.filter(isUnconfirmed).length;
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="data" detail="Calendar" />
      </p>
      <h1 className="th-claim">What&apos;s coming</h1>
      <p className="th-asof">
        {ahead.length > 0
          ? `${notable} notable items in the next six months, ${ahead.length - notable} routine ones behind a switch${unconfirmed > 0 ? `, ${unconfirmed} of them unconfirmed` : ""}.`
          : "The calendar has not been filled yet."}{" "}
        Every item names who published the date. Official schedules link to the page that publishes them; estimated dates follow a published rule and can move; unconfirmed ones come from our own
        earlier reports or watches.
      </p>
      <CalendarView rows={rows} today={today} />
    </div>
  );
}
