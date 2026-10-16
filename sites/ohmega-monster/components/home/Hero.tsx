import Link from "next/link";

import GlobeSpinner from "@/components/GlobeSpinner";
import IsoFlags from "@/components/IsoFlags";
import Glyph from "@/components/vl/Glyph";
import { DirMark, HeatBar, Numeral, Spark } from "@/components/vl/primitives";
import { claimOf, fmtDay, shortTheater, theaterAnchor, type Daily, type DailyTheater } from "@/lib/daily";
import type { Snapshot } from "@/lib/intel";
import { SITE_DESCRIPTION } from "@/lib/site";
import { categoryOf, CATEGORY_LABEL, shareOfMax } from "@/lib/visual";

import "./home.css";

// Home's first screen: the state of the world today, drawn rather than written. A short headline, three counts, the cycling globe, and
// one tile per theater that matters most (escalating ones first): category glyph, flags, a coloured direction mark, a heat bar on one
// shared scale and a week of coverage. No sentence per theater; the tile is the door to its section of the report.

const SHOWN = 4;
const FLAGS = 3;
const NAME_WORDS = 4;
const HEADLINE_MAX = 90;
const SPARK_DAYS = 7;

type Tile = { t: DailyTheater; anchor: string; series: number[] };

/** Escalating theaters first, then by heat: the order a newcomer should meet them in. */
function topTheaters(report: Daily, snap: Snapshot | null): Tile[] {
  const rank = { rising: 0, easing: 1, steady: 2, unclear: 3 } as const;
  return report.theaters
    .map((t, i) => ({ t, anchor: theaterAnchor(t, i) }))
    .filter(({ t }) => t.kind === "section")
    .sort((a, b) => rank[a.t.escalation.direction] - rank[b.t.escalation.direction] || b.t.temperature.heat - a.t.temperature.heat)
    .slice(0, SHOWN)
    .map(({ t, anchor }) => {
      const s = snap?.theaters.find((x) => x.id === t.theater_id)?.series ?? snap?.theaters.find((x) => x.name === t.name)?.series ?? [];
      return { t, anchor, series: s.slice(-SPARK_DAYS).map((d) => d.count) };
    });
}

const shortName = (name: string): string => shortTheater(name).split(/\s+/).slice(0, NAME_WORDS).join(" ");

export default function Hero({ report, snap }: { report: Daily | null; snap: Snapshot | null }) {
  const tiles = report ? topTheaters(report, snap) : [];
  const sections = report ? report.theaters.filter((t) => t.kind === "section") : [];
  const up = sections.filter((t) => t.escalation.direction === "rising").length;
  const down = sections.filter((t) => t.escalation.direction === "easing").length;
  const maxHeat = Math.max(0, ...sections.map((t) => t.temperature.heat));
  return (
    <section className="hm-hero" aria-label="The world today">
      <div className="hm-globe">
        <GlobeSpinner cycle decorative size={160} />
      </div>
      <div className="hm-claim-wrap">
        <p className="hm-kicker">{report ? fmtDay(report.date) : "Ohmega Monster"}</p>
        <h1 className="hm-claim">{report?.headline ? claimOf(report.headline, HEADLINE_MAX) : SITE_DESCRIPTION}</h1>
      </div>
      {sections.length > 0 && (
        <div className="hm-stats" role="group" aria-label="Today in numbers">
          <Numeral n={sections.length} label="theaters" />
          <span className="hm-stat hm-stat-up">
            <Numeral n={up} label="escalating" />
          </span>
          <span className="hm-stat hm-stat-down">
            <Numeral n={down} label="easing" />
          </span>
        </div>
      )}
      {tiles.length > 0 && (
        <ul className="hm-tiles" aria-label="Theaters to watch">
          {tiles.map(({ t, anchor, series }) => {
            const cat = categoryOf(t.name, t.headline, t.bottom_line);
            const flags = [...new Set(t.pulses.flatMap((p) => p.actors_iso2))].slice(0, FLAGS);
            return (
              <li key={anchor}>
                <Link href={`/geopolitics#${anchor}`} className={`vl-card has-cat vl-cat-${cat} hm-tile`} title={t.name}>
                  <span className="hm-tile-top">
                    <span className="vl-chip" title={CATEGORY_LABEL[cat]}>
                      <Glyph name={cat} size={18} />
                      <span className="vl-sr">{CATEGORY_LABEL[cat]}</span>
                    </span>
                    <DirMark direction={t.escalation.direction} />
                  </span>
                  <span className="hm-tile-flags">
                    <IsoFlags codes={flags} />
                  </span>
                  <span className="hm-tile-name">{shortName(t.name)}</span>
                  <span className="hm-tile-meter">
                    <HeatBar share={shareOfMax(t.temperature.heat, maxHeat)} label={`${shortTheater(t.name)} heat`} />
                    <Spark values={series} label={`${shortTheater(t.name)}: headlines per day, last ${series.length} days`} />
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      {report && (
        <p className="hm-more">
          <Link href="/geopolitics" className="xt">
            Today&apos;s report →
          </Link>
          <Link href="/intel/theaters" className="xt">
            All theaters →
          </Link>
        </p>
      )}
    </section>
  );
}
