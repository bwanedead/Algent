import Link from "next/link";

import ArticleFeed from "@/components/ArticleFeed";
import Doors from "@/components/Doors";
import Hero from "@/components/home/Hero";
import LiveStrip from "@/components/home/LiveStrip";
import { getAllMeta } from "@/lib/articles";
import { latestDaily } from "@/lib/daily";
import { liveSummary } from "@/lib/live";
import { homeDoors } from "@/lib/sections";

import "@/app/geopolitics/geopolitics.css";
import "@/components/home/home.css";

// Home: a calm hub, not an index. The state of the world today, what is moving live, doors into every
// section (each with one line and a live hint), and only the latest few articles. The full article
// list lives at /articles.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

const LATEST_ARTICLES = 3;

export default async function Home() {
  const [report, summary, doors, articles] = await Promise.all([latestDaily("geopolitics"), liveSummary(), homeDoors(), getAllMeta()]);
  return (
    <div className="index-page">
      <Hero report={report} />
      <LiveStrip summary={summary} />
      <section className="hm-block" aria-label="Go deeper">
        <p className="hm-sub">Go deeper</p>
        <Doors doors={doors} label="Sections of the site" />
      </section>
      {articles.length > 0 && (
        <section className="hm-block" aria-label="Latest articles">
          <p className="hm-sub">Latest articles</p>
          <ArticleFeed articles={articles.slice(0, LATEST_ARTICLES)} />
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
