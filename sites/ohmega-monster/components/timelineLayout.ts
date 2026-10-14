// Pure layout of a native timeline (NativeTimeline.tsx): the ordered rows (events, "now", and the gaps between them
// that make elapsed time visible). No DOM, no React: the geometry rules live here so they can be read and tested alone.
//
// Spacing rule: a gap row sits between two items that fall on different days. Its height grows with the days between
// them (GAP_PX_PER_DAY) up to a week, then compresses (logarithmically, capped), and a gap of two days or more is named
// ("· 6 days ·"). A gap longer than a week is drawn dashed: the spine says "time was skipped here". Same-day events
// are adjacent with no gap. The spine itself is continuous through every row (see timeline.css), so nothing floats.

import type { TimelineEvent, TimelineSpec } from "@/lib/visualSpecs";

export const GAP_PX_PER_DAY = 8;
export const GAP_LINEAR_DAYS = 7;
export const GAP_MAX_PX = 84;
export const GAP_LABEL_MIN_PX = 24; // a named gap is at least tall enough for its text

export type Row =
  | { kind: "event"; key: string; event: TimelineEvent; showDate: boolean; first: boolean; last: boolean }
  | { kind: "now"; key: string; date: string; first: boolean; last: boolean }
  | { kind: "gap"; key: string; days: number; px: number; compressed: boolean; label: string };

const DAY_MS = 86_400_000;
const utc = (iso: string) => Date.parse(`${iso}T00:00:00Z`);
export const daysBetween = (a: string, b: string): number => Math.round((utc(b) - utc(a)) / DAY_MS);

/** The height in px of the gap for `days` days: proportional for a week, then compressed and capped. */
export function gapPx(days: number): number {
  if (days <= 0) return 0;
  if (days <= GAP_LINEAR_DAYS) return days * GAP_PX_PER_DAY;
  const extra = Math.log(days / GAP_LINEAR_DAYS) * 18;
  return Math.min(GAP_MAX_PX, Math.round(GAP_LINEAR_DAYS * GAP_PX_PER_DAY + extra));
}

/** "6 days", "3 weeks", "4 months": the time a gap stands for. */
export function gapLabel(days: number): string {
  if (days < 2) return "";
  if (days <= 31) return `${days} days`;
  if (days <= 90) return `${Math.round(days / 7)} weeks`;
  return `${Math.round(days / 30)} months`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
/** { day: "9 Oct", weekday: "Thu", year } of an ISO date (UTC, so no timezone can shift it). */
export function dateParts(iso: string): { day: string; weekday: string; year: string } {
  const [y, m, d] = iso.split("-").map(Number);
  return { day: `${d} ${MONTHS[m - 1] ?? ""}`, weekday: WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()], year: String(y) };
}

/** Events in order with the `now` marker where it falls and a gap row wherever days passed between two items. */
export function layoutRows(spec: Pick<TimelineSpec, "events" | "now">): Row[] {
  type Item = { date: string; ev: TimelineEvent | null };
  const items: Item[] = spec.events.map((ev) => ({ date: ev.date, ev }));
  if (spec.now) {
    let at = items.length; // after every event on or before `now`
    while (at > 0 && items[at - 1].date > spec.now) at--;
    items.splice(at, 0, { date: spec.now, ev: null });
  }
  const rows: Row[] = [];
  items.forEach((it, i) => {
    const prev = items[i - 1];
    if (prev) {
      const days = daysBetween(prev.date, it.date);
      if (days >= 1) {
        const label = gapLabel(days);
        const px = gapPx(days);
        rows.push({ kind: "gap", key: `gap-${i}`, days, px: label ? Math.max(px, GAP_LABEL_MIN_PX) : px, compressed: days > GAP_LINEAR_DAYS, label });
      }
    }
    const showDate = !prev || prev.date !== it.date || prev.ev === null; // a repeated date is shown once
    rows.push(it.ev ? { kind: "event", key: it.ev.id, event: it.ev, showDate, first: false, last: false } : { kind: "now", key: "now", date: it.date, first: false, last: false });
  });
  // The spine starts at the first dot and ends at the last: only the first and last rows are clipped. A gap is never first or last.
  const marks = rows.filter((r) => r.kind !== "gap") as Exclude<Row, { kind: "gap" }>[];
  if (marks.length) {
    marks[0].first = true;
    marks[marks.length - 1].last = true;
  }
  return rows;
}
