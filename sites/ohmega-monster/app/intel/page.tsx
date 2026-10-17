import type { Metadata } from "next";
import Link from "next/link";

import Doors from "@/components/Doors";
import PageTag from "@/components/PageTag";
import { allDailyDates, fmtDay } from "@/lib/daily";
import { dossierList } from "@/lib/dossier";
import { DIRECTION } from "@/lib/dossier-view";
import { toolDoors } from "@/lib/sections";

import "@/app/geopolitics/geopolitics.css";
import "./theaters/theaters.css";

export const metadata: Metadata = {
  title: "Intelligence: theaters, data and tools",
  description: "Every theater's living file first, then the data and tools behind the Daily: Pulses, the record, calendar, sanctions, maritime, actors and the graph.",
  alternates: { canonical: "/intel" },
};

// The Intelligence directory, three blocks and nothing else: Theaters (the product, big), Data & tools (instruments,
// not publications) and the Archive (past Dailies). The two other products live at /geopolitics and /articles.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

const ARCHIVE_DAYS = 14;

export default async function IntelDirectoryPage() {
  const [doors, theaters, dates] = await Promise.all([toolDoors(), dossierList(), allDailyDates("geopolitics")]);
  const active = theaters.filter((t) => !t.merged_into).sort((a, b) => b.heat - a.heat);
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="tool" detail="Directory" />
      </p>
      <h1 className="th-claim">Theaters, data and tools</h1>

      <section className="th-sec" aria-labelledby="intel-theaters-h">
        <div className="th-sec-head">
          <h2 id="intel-theaters-h">Theaters ({active.length})</h2>
          <Link href="/intel/theaters" className="xt">Compare all theaters →</Link>
        </div>
        <p className="th-lead">One living file per situation: where it stands, the latest from the Daily, and every day before it.</p>
        <ul className="th-picks">
          {active.map((t) => {
            const dir = DIRECTION[t.escalation_direction];
            return (
              <li key={t.theater_id}>
                <Link href={`/intel/theaters/${t.theater_id}`}>
                  <span className="th-pick-dir" aria-hidden="true">{dir.glyph}</span>
                  <span className="th-pick-name">{t.name}</span>
                  <span className="th-pick-meta">{dir.word}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="th-sec" aria-labelledby="intel-tools-h">
        <div className="th-sec-head">
          <h2 id="intel-tools-h">Data &amp; tools</h2>
        </div>
        <Doors doors={doors} label="Data and tools" />
      </section>

      <section className="th-sec" aria-labelledby="intel-archive-h">
        <div className="th-sec-head">
          <h2 id="intel-archive-h">Archive</h2>
          <Link href="/articles" className="xt">Articles →</Link>
        </div>
        <p className="th-lead">Past Dailies, newest first.</p>
        <ul className="th-picks th-picks-days">
          {dates.slice(0, ARCHIVE_DAYS).map((d, i) => (
            <li key={d}>
              <Link href={i === 0 ? "/geopolitics" : `/geopolitics/${d}`}>
                <span className="th-pick-name">{fmtDay(d)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
