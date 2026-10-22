import Link from "next/link";

import Age from "@/components/Fresh";
import NewDot from "@/components/NewDot";
import { claimOf, type Daily } from "@/lib/daily";
import { dailyBase, situationHref, type Desk } from "@/lib/desks";
import { CADENCE_HOURS, isStale } from "@/lib/fresh";
import type { ArticleMeta } from "@/lib/articles";
import type { DeskSituations } from "@/lib/situations";

import "@/components/hubs.css";

// "Today": the site's present tense across desks, in four kinds of row, each one a link with its own age: the newest Daily headline of
// every desk (so a new desk appears here by itself), the situations moving (escalating ones first, ranked WITHIN each desk, never
// across desks), and the newest article. Navigation, not content: the Daily hub, /situations and /articles hold the rest.

const HEADLINE_MAX = 150;
const MOVING_PER_DESK = 2;

type Moving = { id: string; name: string; deskLabel: string; stamp: string };

function moving(groups: DeskSituations[]): Moving[] {
  return groups.flatMap((g) =>
    g.active
      .filter((r) => r.item.escalation_direction === "rising")
      .slice(0, MOVING_PER_DESK)
      .map((r) => ({ id: r.item.theater_id, name: r.item.name, deskLabel: g.desk.label, stamp: r.item.last_seen })),
  );
}

export default function Today({ desks, reports, situations, article }: { desks: Desk[]; reports: (Daily | null)[]; situations: DeskSituations[]; article: ArticleMeta | null }) {
  const rows = moving(situations);
  return (
    <section className="hm-today" aria-label="Today across desks">
      <p className="hm-sub">
        <span>Today</span>
        <Link href="/daily" className="xt">
          All dailies
        </Link>
      </p>
      <ul className="hm-today-grid">
        {desks.map((desk, i) => {
          const r = reports[i];
          if (!r) return null;
          const stamp = r.built_at || r.date;
          return (
            <li key={desk.id}>
              <Link href={dailyBase(desk.id)} className="hm-today-item">
                <span className="hm-today-k">
                  <span>{desk.label} Daily</span>
                  <Age stamp={stamp} cadenceHours={desk.cadenceHours} />
                  <NewDot id={`daily:${desk.id}`} stamp={stamp} stale={isStale(stamp, desk.cadenceHours)} />
                </span>
                <span className="hm-today-line">{claimOf(r.headline || "Today's report", HEADLINE_MAX)}</span>
              </Link>
            </li>
          );
        })}
        {rows.map((m) => (
          <li key={m.id}>
            <Link href={situationHref(m.id)} className="hm-today-item">
              <span className="hm-today-k">
                <span>{m.deskLabel} situation · escalating</span>
                <Age stamp={m.stamp} cadenceHours={CADENCE_HOURS.situation} prefix="Last report " />
                <NewDot id={`situation:${m.id}`} stamp={m.stamp} stale={isStale(m.stamp, CADENCE_HOURS.situation)} />
              </span>
              <span className="hm-today-line">{m.name}</span>
            </Link>
          </li>
        ))}
        {article && (
          <li>
            <Link href={`/articles/${article.slug}`} className="hm-today-item">
              <span className="hm-today-k">
                <span>Newest article</span>
                <Age stamp={article.published_at || article.date} cadenceHours={CADENCE_HOURS.article} />
                <NewDot id="articles:newest" stamp={article.published_at || article.date} stale={isStale(article.published_at || article.date, CADENCE_HOURS.article)} />
              </span>
              <span className="hm-today-line">{article.title}</span>
            </Link>
          </li>
        )}
      </ul>
    </section>
  );
}
