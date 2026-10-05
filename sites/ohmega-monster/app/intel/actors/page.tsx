import type { Metadata } from "next";
import Link from "next/link";

import ActorTable, { type TableRow } from "@/components/actors/ActorTable";
import { COMPARE_METRICS, headline } from "@/components/actors/ActorParts";
import { allActors, fmt } from "@/lib/actors";

import "@/app/geopolitics/geopolitics.css";
import "../theaters/theaters.css";

export const metadata: Metadata = {
  title: "Every actor",
  description: "The powers behind the news: population, economy, energy and military of each state, side by side on shared scales.",
  alternates: { canonical: "/intel/actors" },
};

// The index: every published actor as one row of a small-multiples table, each column on one shared
// scale. The claim names the biggest of each kind, so the first screen answers "who is big at what".
export default function ActorsIndexPage() {
  const actors = allActors();
  if (actors.length === 0) {
    return (
      <div className="intel-page th-page">
        <h1 className="th-claim">No actor profiles yet</h1>
        <p className="intel-empty">Profiles appear here once the actors data has been fetched. Check back soon.</p>
      </div>
    );
  }
  const rows: TableRow[] = actors.map((a) => ({
    iso2: a.iso2,
    name: a.name,
    theaters: a.involved.theaters.length,
    cells: Object.fromEntries(
      COMPARE_METRICS.map(([id]) => {
        const f = headline(a, id);
        return [id, f ? { value: f.value, text: fmt(f.value, f.unit), year: f.year } : null];
      }),
    ),
  }));
  const top = (id: string) => [...rows].filter((r) => r.cells[id]).sort((x, y) => (y.cells[id]?.value ?? 0) - (x.cells[id]?.value ?? 0))[0];
  const biggest = top("gdp");
  const spender = top("milex");
  const asOf = actors.map((a) => a.data_as_of).sort().pop() ?? "";
  return (
    <div className="intel-page th-page">
      <nav className="th-crumb" aria-label="Breadcrumb">
        <Link href="/intel">Situation room</Link>
      </nav>
      <p className="th-kicker">
        <span>Actors</span>
      </p>
      <h1 className="th-claim">
        {biggest && spender
          ? `${biggest.name} has the largest economy and ${spender.name} the biggest military budget among ${actors.length} actors`
          : `${actors.length} actors, side by side`}
      </h1>
      <p className="th-asof">
        The G20, the UN Security Council&apos;s five, and every country the desk is writing about · each column is on one scale · latest year available per
        figure{asOf && ` · data fetched ${asOf}`}
      </p>
      <ActorTable rows={rows} columns={COMPARE_METRICS.map(([id, label]) => ({ id, label }))} />
      <p className="th-note">
        Sources: World Bank (CC BY 4.0, military figures from SIPRI), Our World in Data energy dataset (CC BY 4.0), Wikidata (CC0). Each actor&apos;s page credits its
        sources with the years used.
      </p>
    </div>
  );
}
