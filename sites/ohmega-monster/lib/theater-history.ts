import { allDailyDates, daily, headlineOf, theaterAnchor, type DailyChangeKind } from "./daily";
import type { Direction } from "./intel";

// A theater's living file, seen through the Daily: every day's section for one theater, newest first. The Daily
// is the source (backend daily/geopolitics/<date>.json); this module only reads it per theater. Server-only
// (it reads documents); the list it returns is plain data a component renders.

export type TheaterDay = {
  date: string;
  /** The deep link to this theater's section in that day's Daily. */
  href: string;
  claim: string;
  bottomLine: string;
  direction: Direction;
  changes: { what: string; kind: DailyChangeKind }[];
  developments: { headline: string; verified: boolean }[];
  /** Later parts of the day that added to this section. */
  updates: number;
};

const TOP_DEVELOPMENTS = 4;

/** Every day this theater had a section in the Daily, newest first. Days it was not written up are simply absent. */
export async function theaterDays(theaterId: string): Promise<TheaterDay[]> {
  const dates = await allDailyDates("geopolitics");
  const reports = await Promise.all(dates.map((d) => daily("geopolitics", d)));
  const out: TheaterDay[] = [];
  reports.forEach((r, ri) => {
    if (!r) return;
    const i = r.theaters.findIndex((t) => t.theater_id === theaterId && t.kind !== "update");
    if (i < 0) return;
    const t = r.theaters[i];
    out.push({
      date: dates[ri],
      href: `/geopolitics/${dates[ri]}#${theaterAnchor(t, i)}`,
      claim: headlineOf(t.headline, t.bottom_line, 160) || t.name,
      bottomLine: t.bottom_line,
      direction: t.escalation.direction,
      changes: t.since_yesterday.filter((c) => c.kind !== "unchanged"),
      developments: t.developments.slice(0, TOP_DEVELOPMENTS).map((d) => ({ headline: d.headline, verified: d.verification === "researched" })),
      updates: t.updates.length,
    });
  });
  return out;
}
