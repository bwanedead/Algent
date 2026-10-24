import { parseTheater, type DailyTheater } from "./daily";
import { DESKS, deskById, type Desk } from "./desks";
import { parseCoverageSeries, parseEscalationHistory, parseIndexItem, type Dossier, type DossierIndexItem } from "./dossier";
import type { Direction } from "./intel";
import { situationsView, type SituationRowView, type SituationView, type StreamEntry } from "./views";

// Situations as the reader meets them (docs/architecture/information-architecture.md §2): the backend's "theaters", grouped by desk, with Spotlight
// one-offs left out, the quiet ones separated from the active ones, and each situation's stream of Daily sections. The server builds all of it
// (backend `views/situation.py`: the grouping and ordering are its) and this module only shapes the published views for the pages. Server-only (it reads
// a document); everything returned is plain data.

export type SituationRow = { item: DossierIndexItem; dossier: Pick<Dossier, "escalation_history" | "coverage_series"> | null };
export type DeskSituations = { desk: Desk; active: SituationRow[]; quiet: SituationRow[]; merged: SituationRow[] };

function toRow(r: SituationRowView): SituationRow | null {
  const item = parseIndexItem(r.item);
  return item ? { item, dossier: { escalation_history: parseEscalationHistory(r.dossier?.escalation_history), coverage_series: parseCoverageSeries(r.dossier?.coverage_series) } } : null;
}

const rowsOf = (xs: SituationRowView[] | undefined): SituationRow[] => (xs ?? []).map(toRow).filter((r): r is SituationRow => r !== null);

/** Every situation, one entry per desk (a new desk shows up empty-handed rather than missing). */
export async function situationsByDesk(): Promise<DeskSituations[]> {
  const view = await situationsView();
  return DESKS.map((desk) => {
    const g = view?.desks.find((d) => d.desk === desk.id);
    return { desk, active: rowsOf(g?.active), quiet: rowsOf(g?.quiet), merged: rowsOf(g?.merged) };
  });
}

/** One day of a situation shown in full: the Daily section that covered it, with what the page needs of the report around it (its anchor, the part-of-day tags). */
export type StreamDay = { desk: Desk; date: string; anchor: string; edition: string; updateTags: string[]; events: boolean; t: DailyTheater };

/** An earlier day, as a row that links into that day's report (the server sends the newest days in full and an index of the rest). */
export type StreamRow = { desk: Desk; date: string; href: string; headline: string; direction: Direction; visuals: { id: string; kind: string; title: string }[]; developments: number };

export type SituationStream = { total: number; days: StreamDay[]; earlier: StreamRow[]; earlierTotal: number };

function toDay(e: StreamEntry): StreamDay | null {
  const t = parseTheater(e.section);
  return t ? { desk: deskById(e.desk) ?? DESKS[0], date: e.date, anchor: e.anchor, edition: e.edition, updateTags: e.update_tags, events: e.events, t } : null;
}

/** The stream of a situation view: every day any desk's Daily covered it, newest first - the newest in full, the rest as rows. */
export function streamOf(view: SituationView | null): SituationStream {
  if (!view) return { total: 0, days: [], earlier: [], earlierTotal: 0 };
  const days = view.stream.full.map(toDay).filter((d): d is StreamDay => d !== null);
  const earlier = view.stream.index.map((e): StreamRow => ({ desk: deskById(e.desk) ?? DESKS[0], date: e.date, href: e.href, headline: e.headline, direction: e.direction, visuals: e.visuals, developments: e.developments }));
  return { total: view.stream.days_total, days, earlier, earlierTotal: view.stream.index_total };
}
