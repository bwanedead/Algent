import Link from "next/link";

import { TheaterGroup } from "@/components/dossier/TheaterRows";
import { situationHref } from "@/lib/desks";
import { isoDay } from "@/lib/dossier-view";
import type { DeskSituations, SituationRow } from "@/lib/situations";

// One desk's situations: the active ones grouped by where they are heading (escalating first), the quiet ones folded below, merged
// ones as plain links. The day axis and the bar scale are this desk's own, because a desk's coverage shares are not comparable with
// another desk's. Server component.

const DAYS = 21;

export default function DeskPanel({ group }: { group: DeskSituations }) {
  const { desk, active, quiet, merged } = group;
  const all = [...active, ...quiet];
  if (all.length === 0 && merged.length === 0) {
    return <p className="intel-empty">No {desk.label} situations yet. They appear once a story has been reported on in a second daily.</p>;
  }
  const days = Array.from(
    new Set(
      all
        .flatMap((r) => (r.dossier ? [...r.dossier.escalation_history.map((e) => e.date), ...r.dossier.coverage_series.map((c) => c.day)] : []))
        .map(isoDay)
        .filter(Boolean),
    ),
  )
    .sort()
    .slice(-DAYS);
  const max = Math.max(1, ...all.flatMap((r) => (r.dossier ? r.dossier.coverage_series.filter((c) => days.includes(isoDay(c.day))).map((c) => c.count) : [])));
  const names = new Map([...all, ...merged].map((r) => [r.item.theater_id, r.item.name]));
  const where = (dirs: SituationRow["item"]["escalation_direction"][]) => active.filter((r) => dirs.includes(r.item.escalation_direction));
  const rising = where(["rising"]);
  const steady = where(["steady", "unclear"]);
  const easing = where(["easing"]);
  return (
    <>
      <p className="hub-note">
        {active.length} active situation{active.length === 1 ? "" : "s"}
        {rising.length > 0 && ` · ${rising.length} escalating`}
        {quiet.length > 0 && ` · ${quiet.length} quiet`}. Each row shows the last {days.length} days on one shared axis; the bars are headlines per day on one scale for this desk&apos;s rows only.
      </p>
      <p className="th-key th-index-key">
        <span aria-hidden="true">▲</span> rising <span aria-hidden="true">◆</span> steady <span aria-hidden="true">▼</span> easing · coloured chip = most severe Pulse
      </p>
      <TheaterGroup title={`Escalating (${rising.length})`} rows={rising} days={days} max={max} names={names} />
      <TheaterGroup title={`Holding steady (${steady.length})`} rows={steady} days={days} max={max} names={names} />
      <TheaterGroup title={`Easing (${easing.length})`} rows={easing} days={days} max={max} names={names} />
      {active.length === 0 && <p className="intel-empty">Nothing active in {desk.label} right now.</p>}
      {quiet.length > 0 && (
        <details className="hub-quiet">
          <summary>Quiet ({quiet.length}) · nothing new for a week or more</summary>
          <TheaterGroup title="Quiet" rows={quiet} days={days} max={max} names={names} />
        </details>
      )}
      {merged.length > 0 && (
        <section className="th-group" aria-label="Merged situations">
          <h2 className="th-group-h">Merged ({merged.length})</h2>
          <ul className="th-merged-list">
            {merged.map((r) => (
              <li key={r.item.theater_id}>
                <Link href={situationHref(r.item.theater_id)}>{r.item.name}</Link> · merged into{" "}
                {names.has(r.item.merged_into) ? <Link href={situationHref(r.item.merged_into)}>{names.get(r.item.merged_into)}</Link> : r.item.merged_into}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
