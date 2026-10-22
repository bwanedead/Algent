import type { Metadata } from "next";

import DeskTabs from "@/components/DeskTabs";
import PageTag from "@/components/PageTag";
import DeskPanel from "@/components/situations/DeskPanel";
import { situationsByDesk } from "@/lib/situations";

import "@/app/daily/daily.css";
import "@/components/hubs.css";
import "./situations.css";

export const metadata: Metadata = {
  title: "Situations",
  description: "Every story we follow over time, one living file each, listed by desk: where it stands, how long it has run and when we last reported on it.",
  alternates: { canonical: "/situations" },
};

// The situations index: one tab per desk (generated from the desk list), active situations first with the quiet ones folded below.
// Spotlight one-offs are not here; they live in the Daily until a second report makes them a situation.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function SituationsPage() {
  const groups = await situationsByDesk();
  const total = groups.reduce((n, g) => n + g.active.length, 0);
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="situation" detail="All desks" />
      </p>
      <h1 className="th-claim">
        {total} active situation{total === 1 ? "" : "s"}
      </h1>
      <p className="th-lead">
        A situation is one story we follow over time. Each has a living file: every Daily section about it, newest first, then the map, the actors and our outlook. Desks are listed separately because their scales differ.
      </p>
      <DeskTabs
        tabs={groups.map((g) => ({
          id: g.desk.id,
          label: g.desk.label,
          count: String(g.active.length),
          panel: <DeskPanel group={g} />,
        }))}
      />
    </div>
  );
}
