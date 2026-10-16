import Link from "next/link";

import Doors from "@/components/Doors";
import ArticleCards from "@/components/home/ArticleCards";
import Hero from "@/components/home/Hero";
import LiveStrip from "@/components/home/LiveStrip";
import { getAllMeta } from "@/lib/articles";
import { latestDaily } from "@/lib/daily";
import { latestSnapshot } from "@/lib/intel";
import { liveSummary, liveWorld } from "@/lib/live";
import { homeDoors } from "@/lib/sections";

import "@/app/geopolitics/geopolitics.css";
import "@/components/home/home.css";

// Home: a visual hub, not an index. The world today as a globe and theater tiles, what is moving live as a stamp map and counts,
// doors into every section (glyph, one numeral, a short title), and the latest three articles as picture cards. Text is the
// exception on this page; the full article list lives at /articles. Visual language: app/visual.css.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

const LATEST_ARTICLES = 3;

export default async function Home() {
  const [report, summary, world, snap, doors, articles] = await Promise.all([latestDaily("geopolitics"), liveSummary(), liveWorld(), latestSnapshot(), homeDoors(), getAllMeta()]);
  return (
    <div className="index-page">
      <Hero report={report} snap={snap} />
      <LiveStrip summary={summary} world={world} />
      <section className="hm-block" aria-label="Go deeper">
        <p className="hm-sub">Go deeper</p>
        <Doors doors={doors} label="Sections of the site" lines={false} />
      </section>
      {articles.length > 0 && (
        <section className="hm-block" aria-label="Latest articles">
          <p className="hm-sub">Latest articles</p>
          <ArticleCards articles={articles.slice(0, LATEST_ARTICLES)} />
          <p className="hm-all">
            <Link href="/articles" className="xt">
              All {articles.length} articles →
            </Link>
          </p>
        </section>
      )}
    </div>
  );
}
