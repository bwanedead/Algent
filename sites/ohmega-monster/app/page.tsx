import Link from "next/link";

import Doors from "@/components/Doors";
import { ChartOfDay, GlanceBand } from "@/components/home/Glance";
import { Masthead, TheaterRank } from "@/components/home/Hero";
import ArticleRows from "@/components/home/ArticleRows";
import { getAllMeta } from "@/lib/articles";
import { latestDaily } from "@/lib/daily";
import { chartOfDay, glanceCells, topMovers } from "@/lib/glance";
import { latestSnapshot } from "@/lib/intel";
import { liveEnergy, liveStats, liveSummary } from "@/lib/live";
import { homeDoors } from "@/lib/sections";

import "@/app/geopolitics/geopolitics.css";
import "@/components/home/home.css";

// Home: a dense, calm dashboard, not an index. The world today (headline and the cycling globe), the day's key movers as an
// at-a-glance band of numerals against their own normal, the theaters ranked beside the chart of the day, a compact index of
// doors into every section, and the latest three articles as thin rows. Every number links to where it lives; running text is
// the headline and short names. Visual language: app/visual.css. Band data: lib/glance.ts.
export const revalidate = 300; // lib/store.ts REVALIDATE_SECONDS

const LATEST_ARTICLES = 3;

export default async function Home() {
  const [report, summary, stats, energy, snap, doors, articles] = await Promise.all([
    latestDaily("geopolitics"),
    liveSummary(),
    liveStats(),
    liveEnergy(),
    latestSnapshot(),
    homeDoors(),
    getAllMeta(),
  ]);
  const cells = glanceCells({ stats, summary, energy, snap, report });
  const chart = chartOfDay(report);
  return (
    <div className="index-page">
      <Masthead report={report} />
      <GlanceBand cells={cells} />
      <div className="hm-pair">
        <TheaterRank report={report} snap={snap} />
        <ChartOfDay chart={chart} movers={chart ? [] : topMovers(report)} />
      </div>
      <section className="hm-block" aria-label="Go deeper">
        <p className="hm-sub">Go deeper</p>
        <Doors doors={doors} label="Sections of the site" lines={false} />
      </section>
      {articles.length > 0 && (
        <section className="hm-block" aria-label="Latest articles">
          <p className="hm-sub">
            <span>Latest articles</span>
            <Link href="/articles" className="xt">
              All {articles.length}
            </Link>
          </p>
          <ArticleRows articles={articles.slice(0, LATEST_ARTICLES)} />
        </section>
      )}
    </div>
  );
}
