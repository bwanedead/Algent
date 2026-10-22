import PageTag from "@/components/PageTag";
import type { Metadata } from "next";

import Crumbs, { DATA_CRUMB } from "@/components/Crumbs";
import RelationshipGraph from "@/components/graph/RelationshipGraph";
import { entityGraph } from "@/lib/entities";

import "@/app/daily/daily.css";
import "@/app/situations/situations.css";

export const metadata: Metadata = {
  title: "Relationship browser",
  description: "States and theaters as one network: who is involved where, and who shares a theater with whom.",
  alternates: { canonical: "/intel/graph" },
};

// Built from what the entity pages already know (lib/entities.ts), so it can never disagree with them.
export const revalidate = 1800; // lib/store.ts TTL.daily: a desk publishes twice a day

export default async function GraphPage() {
  const graph = await entityGraph();
  return (
    <div className="intel-page th-page">
      <Crumbs trail={[DATA_CRUMB]} />
      <p className="th-kicker">
        <PageTag kind="data" detail="Graph" />
      </p>
      <h1 className="th-claim">Who is involved where</h1>
      {graph.theaters.length === 0 ? (
        <p className="intel-empty">The network appears once theaters and the states they involve have been published.</p>
      ) : (
        <>
          <p className="th-asof">
            {graph.actors.length} states and {graph.theaters.length} theaters · tap one to follow its connections
          </p>
          <RelationshipGraph graph={graph} />
        </>
      )}
    </div>
  );
}
