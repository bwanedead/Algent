import { allDailyDates, daily, theaterAnchor, type Daily, type DailyTheater } from "./daily";
import { DESKS, deskOfDomain, type Desk } from "./desks";
import { dossier, dossierList, isSpotlightOneOff, type Dossier, type DossierIndexItem } from "./dossier";
import { ageMs } from "./fresh";

// Situations as the reader meets them (docs/architecture/information-architecture.md §2): the backend's "theaters", grouped by desk,
// with Spotlight one-offs left out (they live in the Daily until a second report follows), the quiet ones separated from the active
// ones, and each situation's stream of Daily sections. Server-only (it reads documents); everything returned is plain data.

/** Nothing new for this many days = quiet. Mirrors the backend's FOCUS_DROP_DAYS (agents/intel/focus.py). */
const QUIET_AFTER_DAYS = 7;
const DAY_MS = 24 * 3_600_000;

export type SituationRow = { item: DossierIndexItem; dossier: Dossier | null };
export type DeskSituations = { desk: Desk; active: SituationRow[]; quiet: SituationRow[]; merged: SituationRow[] };

/** The desk's own lifecycle word wins; an older index with none falls back to how long since its last report. */
function isQuiet(i: DossierIndexItem): boolean {
  if (i.state) return i.state === "quiet";
  const age = ageMs(i.last_novel || i.last_seen);
  return age !== null && age > QUIET_AFTER_DAYS * DAY_MS;
}

const RANK = { rising: 0, easing: 1, steady: 2, unclear: 3 } as const;

/** Within ONE desk: escalating first, then the most recently reported, then the longest-running. Heat is never compared across desks
 *  (each desk's heat is a share of its own headlines), so no sort here ever mixes them. */
const byUrgency = (a: SituationRow, b: SituationRow): number =>
  RANK[a.item.escalation_direction] - RANK[b.item.escalation_direction] ||
  (a.item.last_seen < b.item.last_seen ? 1 : a.item.last_seen > b.item.last_seen ? -1 : 0) ||
  b.item.days_covered - a.item.days_covered ||
  a.item.name.localeCompare(b.item.name);

/** Every situation, one entry per desk (a new desk shows up empty-handed rather than missing). */
export async function situationsByDesk(): Promise<DeskSituations[]> {
  const list = (await dossierList()).filter((i) => !isSpotlightOneOff(i));
  const rows: SituationRow[] = (await Promise.all(list.map(async (item) => ({ item, dossier: await dossier(item.theater_id) })))).filter((r) => r.dossier !== null); // an unreadable dossier would be a dead link
  return DESKS.map((desk) => {
    const mine = rows.filter((r) => deskOfDomain(r.item.domain).id === desk.id);
    return {
      desk,
      active: mine.filter((r) => !r.item.merged_into && !isQuiet(r.item)).sort(byUrgency),
      quiet: mine.filter((r) => !r.item.merged_into && isQuiet(r.item)).sort(byUrgency),
      merged: mine.filter((r) => r.item.merged_into),
    };
  });
}

/** One day of a situation: the Daily section that covered it, with the report around it (for the map frame, the day's links and the anchors). */
export type StreamDay = { desk: Desk; date: string; report: Daily; t: DailyTheater; index: number; anchor: string };

/** Every day this situation had a section in any desk's Daily, newest first. Days it was not written up are simply absent. */
export async function situationStream(theaterId: string): Promise<StreamDay[]> {
  const perDesk = await Promise.all(
    DESKS.map(async (desk) => {
      const dates = await allDailyDates(desk.id);
      const reports = await Promise.all(dates.map((d) => daily(desk.id, d)));
      return reports.flatMap((report, k): StreamDay[] => {
        if (!report) return [];
        const index = report.theaters.findIndex((t) => t.theater_id === theaterId && t.kind !== "update");
        if (index < 0) return [];
        const t = report.theaters[index];
        return [{ desk, date: dates[k], report, t, index, anchor: theaterAnchor(t, index) }];
      });
    }),
  );
  return perDesk.flat().sort((a, b) => b.date.localeCompare(a.date));
}
