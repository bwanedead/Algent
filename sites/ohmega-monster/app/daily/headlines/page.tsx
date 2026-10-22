import type { Metadata } from "next";

import HeadlinesView from "@/components/HeadlinesView";
import PageTag from "@/components/PageTag";
import { getMenus } from "@/lib/radar";

export const metadata: Metadata = {
  title: "Headlines",
  description: "What crossed the wire, as other outlets reported it — not yet independently verified.",
};

export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

export default async function HeadlinesIndex() {
  const newest = (await getMenus())[0];
  if (!newest) {
    return (
      <article className="radar-page">
        <header className="article-header">
          <p className="ptag-row"><PageTag kind="daily" detail="Headlines · not verified" /></p>
          <h1>Headlines</h1>
          <p className="dek">No headline editions yet.</p>
        </header>
      </article>
    );
  }
  return <HeadlinesView menu={newest} />;
}
