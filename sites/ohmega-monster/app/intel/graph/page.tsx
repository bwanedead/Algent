import PageTag from "@/components/PageTag";
import type { Metadata } from "next";

import Crumbs, { INTEL_CRUMB } from "@/components/Crumbs";
import RelationshipGraph from "@/components/graph/RelationshipGraph";
import { entityGraph } from "@/lib/entities";

import "@/app/geopolitics/geopolitics.css";
import "../theaters/theaters.css";

export const metadata: Metadata = {
  title: "Relationship browser",
  description: "States and theaters as one network: who is involved where, and who shares a theater with whom.",
  alternates: { canonical: "/intel/graph" },
};

// Built from what the entity pages already know (lib/entities.ts), so it can never disagree with them.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function GraphPage() {
  const graph = await entityGraph();
  return (
    <div className="intel-page th-page">
      <Crumbs trail={[INTEL_CRUMB]} />
      <p className="th-kicker">
        <PageTag kind="tool" detail="Graph" />
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
