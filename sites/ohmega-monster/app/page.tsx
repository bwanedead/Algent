import Link from "next/link";

import ComingStrip from "@/components/calendar/ComingStrip";
import Doors from "@/components/Doors";
import { ChartOfDay, GlanceBand } from "@/components/home/Glance";
import { Masthead, TheaterRank } from "@/components/home/Hero";
import ArticleRows from "@/components/home/ArticleRows";
import Today from "@/components/home/Today";
import { getAllMeta } from "@/lib/articles";
import { addDays, ahead, toComing, todayIso } from "@/lib/calendar";
import { dailyFromView } from "@/lib/daily";
import { DESKS, deskById } from "@/lib/desks";
import { chartOfDay, glanceCells, topMovers } from "@/lib/glance";
import { parseSnapshot } from "@/lib/intel";
import { liveEnergy, liveStats, liveSummary } from "@/lib/live";
import { homeDoors } from "@/lib/sections";
import { homeView } from "@/lib/views";

import "@/app/daily/daily.css";
import "@/components/home/home.css";

// Home: a dense, calm dashboard, not an index. The world today (headline and the cycling globe), today across desks (each desk's
// Daily headline, the situations moving, the newest article, each with its age), the day's key movers as an
// at-a-glance band of numerals against their own normal, the day's sections ranked beside the chart of the day, a compact index of
// doors into every section, and the latest three articles as thin rows. Every number links to where it lives; running text is
// the headline and short names. Visual language: app/visual.css. Band data: lib/glance.ts.
// Everything that is not live is ONE server-built view (backend views/home.py: each desk's newest report as a digest, the situations moving, the next two
// weeks of the calendar, the counts behind the doors); the live strip is read beside it.
export const revalidate = 300; // lib/store.ts TTL.fast: the home view is rebuilt every half hour and the page mixes it with the live strip (live 120 s)

const LATEST_ARTICLES = 3;

export default async function Home() {
  const [view, summary, stats, energy, doors, articles] = await Promise.all([homeView(), liveSummary(), liveStats(), liveEnergy(), homeDoors(), getAllMeta()]);
  const today = todayIso();
  const reports = DESKS.map((d) => dailyFromView(view?.reports[d.id] ?? null, d.id));
  const report = reports[DESKS.findIndex((d) => d.id === "geopolitics")] ?? null;
  const snap = view?.snapshot ? parseSnapshot(view.snapshot, "") : null;
  const moving = (view?.moving ?? []).map((m) => ({ id: m.id, name: m.name, deskLabel: deskById(m.desk)?.label ?? m.desk, stamp: m.stamp }));
  const coming = ahead(view?.coming ?? [], today)
    .filter((r) => r.on_date <= addDays(today, 14))
    .map(toComing);
  const cells = glanceCells({ stats, summary, energy, snap, report });
  const chart = chartOfDay(report);
  return (
    <div className="index-page">
      <Masthead report={report} />
      <Today desks={DESKS} reports={reports} moving={moving} article={articles[0] ?? null} />
      <GlanceBand cells={cells} />
      <ComingStrip rows={coming} today={today} heading="Coming up, next 14 days" limit={4} />
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
