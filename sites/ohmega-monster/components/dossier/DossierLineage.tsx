import Link from "next/link";

import type { Dossier, LineageRef } from "@/lib/dossier";
import { dayLabel, isoDay } from "@/lib/dossier-view";

import { Anchor, Overflow } from "./parts";

// Where a theater came from and what folded into it (backend: dossier_lineage.py). Quiet by design: a
// few plain sentences under the page's header, nothing at all for a theater with no lineage.

const when = (at: string) => (at ? dayLabel(isoDay(at) || at) : "");

function Name({ r }: { r: LineageRef }) {
  return r.url ? <Link href={r.url}>{r.name}</Link> : <>{r.name}</>;
}

export default function DossierLineage({ d }: { d: Dossier }) {
  const { parent, branches, merged_into: into, absorbed } = d.lineage;
  if (!parent && !into && branches.length === 0 && absorbed.length === 0) return null;
  return (
    <section className="th-lineage" aria-label="Lineage">
      {into && (
        <p className="th-lineage-line is-merged">
          This theater was merged into <Name r={into} />
          {into.at && <> on {when(into.at)}</>}. Its record is kept here; new developments are followed there.
          {into.why && <span className="th-since"> {into.why}</span>}
        </p>
      )}
      {parent && (
        <p className="th-lineage-line">
          Branched from <Name r={parent} />
          {parent.at && <> on {when(parent.at)}</>}.
          {parent.why && <span className="th-since"> {parent.why}</span>}
        </p>
      )}
      {d.inherited.length > 0 && parent && (
        <Overflow label={`${parent.name}: history before the branch (${d.inherited.length})`} trigger={`History before the branch (${d.inherited.length})`} wide>
          <ul className="th-lineage-history">
            {d.inherited.map((t, i) => (
              <li key={i}>
                <span className="th-when">{when(t.date)}</span> {t.headline}
                {t.from && (
                  <>
                    {" "}
                    <Anchor url={t.from}>report</Anchor>
                  </>
                )}
              </li>
            ))}
          </ul>
        </Overflow>
      )}
      {branches.length > 0 && (
        <p className="th-lineage-line">
          Branches:{" "}
          {branches.map((b, i) => (
            <span key={b.theater_id}>
              {i > 0 && ", "}
              <Name r={b} />
              {b.at && <span className="th-since"> ({when(b.at)})</span>}
            </span>
          ))}
        </p>
      )}
      {absorbed.length > 0 && (
        <p className="th-lineage-line">
          Absorbed:{" "}
          {absorbed.map((a, i) => (
            <span key={a.theater_id}>
              {i > 0 && "; "}
              <Name r={a} />
              {a.at && <span className="th-since"> on {when(a.at)}</span>}
              {a.url && a.days_covered > 0 && (
                <span className="th-since">
                  {" "}
                  · its history: {a.days_covered} report{a.days_covered === 1 ? "" : "s"}
                </span>
              )}
            </span>
          ))}
        </p>
      )}
    </section>
  );
}
