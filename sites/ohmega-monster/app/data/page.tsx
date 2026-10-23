import type { Metadata } from "next";

import Doors from "@/components/Doors";
import PageTag from "@/components/PageTag";
import UpdatePending from "@/components/UpdatePending";
import { dataGroups } from "@/lib/sections";

import "@/app/daily/daily.css";
import "@/app/situations/situations.css";
import "@/components/hubs.css";

export const metadata: Metadata = {
  title: "Data",
  description: "Everything behind the Daily and the Situations: measured layers, our scored judgments, and feeds for machines.",
  alternates: { canonical: "/data" },
};

// The Data hub: three groups and nothing else. Measured layers have no editorial voice; Judgments are what we think will happen, kept
// and scored; For machines is the API, MCP server and feeds. Each row carries the as-of age of its product. The tool pages keep their
// routes (/intel/..., /pulses, /calendar): only the JSON feeds live under /data/<file>.json (a rewrite in next.config.mjs that matches
// at least one segment, so this page at /data exactly is never swallowed).
export const revalidate = 1800; // lib/store.ts TTL.daily: a desk publishes twice a day

export default async function DataHub() {
  const groups = await dataGroups();
  return (
    <div className="intel-page th-page">
      <p className="th-kicker">
        <PageTag kind="data" detail="All layers" />
      </p>
      <h1 className="th-claim">Data</h1>
      <p className="th-lead">What we measure, what we judge, and how to read it from code. Each row says how old it is; a dimmed age means it is late for how often it is meant to refresh.</p>
      {groups.map((g) => (
        <section key={g.id} className="hub-group" aria-labelledby={`data-${g.id}`}>
          <h2 id={`data-${g.id}`}>{g.title}</h2>
          <p className="th-lead">{g.lead}</p>
          <Doors doors={g.doors} label={g.title} />
        </section>
      ))}
      <UpdatePending />
    </div>
  );
}
