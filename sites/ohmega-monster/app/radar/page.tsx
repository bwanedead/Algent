import type { Metadata } from "next";

import RadarView from "@/components/RadarView";
import { getMenus } from "@/lib/radar";

export const metadata: Metadata = {
  title: "Headline radar",
  description: "What crossed the wire, as other outlets reported it — not yet independently verified.",
};

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function RadarIndex() {
  const newest = (await getMenus())[0];
  if (!newest) {
    return (
      <article className="radar-page">
        <header className="article-header">
          <h1>Headline radar</h1>
          <p className="dek">No radar editions yet.</p>
        </header>
      </article>
    );
  }
  return <RadarView menu={newest} />;
}
