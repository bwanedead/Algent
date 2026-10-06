import type { Metadata } from "next";
import Link from "next/link";

import { TheaterGroup, type TheaterRow } from "@/components/dossier/TheaterRows";
import { dossier, dossierList } from "@/lib/dossier";
import { isoDay } from "@/lib/dossier-view";
import type { Band, Direction } from "@/lib/intel";

import "@/app/geopolitics/geopolitics.css";
import "./theaters.css";

export const metadata: Metadata = {
  title: "Every theater",
  description: "One living dossier per theater: where it stands, how it got here, who is doing what to whom, and where it is heading.",
  alternates: { canonical: "/intel/theaters" },
};

const DAYS = 21;
const BAND_RANK: Record<Band, number> = { calm: 1, elevated: 2, severe: 3, critical: 4, unassessed: 0 };
const bySeverity = (a: TheaterRow, b: TheaterRow) =>
  BAND_RANK[b.item.max_band] - BAND_RANK[a.item.max_band] || b.item.heat - a.item.heat || a.item.name.localeCompare(b.item.name);

// The index: every theater as one row of a small-multiples table. The page's claim counts what is
// moving; rows are grouped by direction so the first chunk is the one that matters.
export default function TheatersIndexPage() {
  const all: TheaterRow[] = dossierList()
    .map((item) => ({ item, dossier: dossier(item.theater_id) }))
    .filter((r) => r.dossier !== null); // an unreadable dossier would be a dead link
  // A theater absorbed into another leaves the groups: it is listed once, below, as "merged into ...".
  const rows = all.filter((r) => !r.item.merged_into);
  const merged = all.filter((r) => r.item.merged_into);
  const names = new Map(all.map((r) => [r.item.theater_id, r.item.name]));
  if (rows.length === 0) {
    return (
      <div className="intel-page th-page">
        <h1 className="th-claim">No theater dossiers yet</h1>
        <p className="intel-empty">Dossiers appear here once a theater has been reported on. Check back soon.</p>
      </div>
    );
  }

  // One shared day axis (the newest DAYS days any theater was reported) and one shared bar scale.
  const days = Array.from(
    new Set(
      rows
        .flatMap((r) => (r.dossier ? [...r.dossier.escalation_history.map((e) => e.date), ...r.dossier.coverage_series.map((c) => c.day)] : []))
        .map(isoDay)
        .filter(Boolean),
    ),
  )
    .sort()
    .slice(-DAYS);
  const max = Math.max(1, ...rows.flatMap((r) => (r.dossier ? r.dossier.coverage_series.filter((c) => days.includes(isoDay(c.day))).map((c) => c.count) : [])));

  const group = (dirs: Direction[]) => rows.filter((r) => dirs.includes(r.item.escalation_direction)).sort(bySeverity);
  const rising = group(["rising"]);
  const steady = group(["steady", "unclear"]);
  const easing = group(["easing"]);
  const claim =
    rising.length > 0
      ? `${rising.length} of ${rows.length} theaters ${rising.length === 1 ? "is" : "are"} escalating`
      : `${rows.length} theater${rows.length === 1 ? "" : "s"} tracked, none escalating`;

  return (
    <div className="intel-page th-page">
      <nav className="th-crumb" aria-label="Breadcrumb">
        <Link href="/intel">Situation room</Link>
      </nav>
      <p className="th-kicker">
        <span>Theater dossiers</span>
      </p>
      <h1 className="th-claim">{claim}</h1>
      <p className="th-asof">
        {rows.length} dossier{rows.length === 1 ? "" : "s"}
        {easing.length > 0 && ` · ${easing.length} easing`} · each row shows the last {days.length} days on one shared axis
      </p>
      <p className="th-key th-index-key">
        <span aria-hidden="true">▲</span> rising <span aria-hidden="true">◆</span> steady <span aria-hidden="true">▼</span> easing · coloured chip = most severe Pulse · bars = headlines per day, one scale for every row
      </p>
      <TheaterGroup title={`Escalating (${rising.length})`} rows={rising} days={days} max={max} names={names} />
      <TheaterGroup title={`Holding steady (${steady.length})`} rows={steady} days={days} max={max} names={names} />
      <TheaterGroup title={`Easing (${easing.length})`} rows={easing} days={days} max={max} names={names} />
      {merged.length > 0 && (
        <section className="th-group" aria-label="Merged theaters">
          <h2 className="th-group-h">Merged ({merged.length})</h2>
          <ul className="th-merged-list">
            {merged.map((r) => (
              <li key={r.item.theater_id}>
                <Link href={`/intel/theaters/${r.item.theater_id}`}>{r.item.name}</Link> · merged into{" "}
                {names.has(r.item.merged_into) ? <Link href={`/intel/theaters/${r.item.merged_into}`}>{names.get(r.item.merged_into)}</Link> : r.item.merged_into}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
