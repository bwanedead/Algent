import type { Metadata } from "next";

import RadarView from "@/components/RadarView";
import { getMenus } from "@/lib/radar";

export const metadata: Metadata = {
  title: "Headline radar",
  description: "What crossed the wire, as other outlets reported it — not yet independently verified.",
};

export default function RadarIndex() {
  const newest = getMenus()[0];
  if (!newest) {
    return (
      <article className="radar-page">
        <header className="article-header">
          <h1>Headline radar</h1>
          <p className="dek">No menus yet.</p>
        </header>
      </article>
    );
  }
  return <RadarView menu={newest} />;
}
