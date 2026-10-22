import PageTag from "@/components/PageTag";
import type { Metadata } from "next";

import CalendarView from "@/components/calendar/CalendarView";
import { calendarItems, isUnconfirmed, todayIso } from "@/lib/calendar";

import "@/app/daily/daily.css";
import "@/app/situations/situations.css";

export const metadata: Metadata = {
  title: "What's coming",
  description: "Elections, central-bank decisions, UN Security Council meetings, OPEC+ meetings and deadlines in the next 30 days, each with its source.",
  alternates: { canonical: "/calendar", types: { "application/json": "/api/v1/calendar" } },
};

// The forward calendar: dated things ahead from official schedules (central banks, the UN Security Council), announcements compiled by
// volunteers (elections, OPEC+) and deadlines our own daily reports named. Data: backend `lookahead/` (migration 012, table
// calendar_items). A date is a plan, not an outcome: items taken from our own reports are marked unconfirmed.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function CalendarPage() {
  const today = todayIso();
  const rows = await calendarItems(45);
  const unconfirmed = rows.filter(isUnconfirmed).length;
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="data" detail="Calendar" />
      </p>
      <h1 className="th-claim">What&apos;s coming in the next 30 days</h1>
      <p className="th-asof">
        {rows.length > 0 ? `${rows.length - unconfirmed} dated items from their sources${unconfirmed > 0 ? `, and ${unconfirmed} unconfirmed` : ""}.` : "The calendar has not been filled yet."} Official schedules link to the page that
        publishes them; items marked unconfirmed come from our own earlier reports, or have a date in the title that disagrees with the item&apos;s date.
      </p>
      <CalendarView rows={rows} today={today} />
    </div>
  );
}
