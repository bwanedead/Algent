import Link from "next/link";

import GlobeSpinner from "@/components/GlobeSpinner";
import IsoFlags from "@/components/IsoFlags";
import Glyph from "@/components/vl/Glyph";
import { DirMark, DirTick, HeatBar, Spark } from "@/components/vl/primitives";
import { claimOf, fmtDay, shortTheater, theaterAnchor, type Daily, type DailyTheater } from "@/lib/daily";
import type { Snapshot } from "@/lib/intel";
import { SITE_DESCRIPTION } from "@/lib/site";
import { categoryOf, CATEGORY_LABEL, shareOfMax } from "@/lib/visual";

import "./home.css";

// Home's masthead and theater ranking. The masthead is the date, one headline and the cycling globe in a small precise frame. The
// ranking is a sharp list of the theaters that matter most (escalating first), one row each: direction tick, flags, a 2 to 5 word
// name, category glyph, heat on one shared scale, a week of coverage as a hairline. No sentence per theater; each row is the door to
// its section of the report.

const SHOWN = 6;
const FLAGS = 3;
const NAME_WORDS = 5;
const HEADLINE_MAX = 90;
const SPARK_DAYS = 7;

type Row = { t: DailyTheater; anchor: string; series: number[] };

/** Escalating theaters first, then by heat: the order a newcomer should meet them in. */
function topTheaters(report: Daily, snap: Snapshot | null): Row[] {
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

export function Masthead({ report }: { report: Daily | null }) {
  const sections = report ? report.theaters.filter((t) => t.kind === "section") : [];
  const up = sections.filter((t) => t.escalation.direction === "rising").length;
  return (
    <section className="hm-mast" aria-label="The world today">
      <div className="hm-claim-wrap">
        <p className="hm-kicker">{report ? fmtDay(report.date) : "Ohmega Monster"}</p>
        <h1 className="hm-claim">{report?.headline ? claimOf(report.headline, HEADLINE_MAX) : SITE_DESCRIPTION}</h1>
        {report && (
          <p className="hm-more">
            <Link href="/geopolitics" className="xt">
              Today&apos;s report
            </Link>
            <Link href="/intel/theaters" className="xt">
              {sections.length > 0 ? `${sections.length} theaters${up > 0 ? `, ${up} escalating` : ""}` : "All theaters"}
            </Link>
          </p>
        )}
      </div>
      <div className="hm-globe">
        <Link href="/globe" className="globe-link" aria-label="Open the interactive globe" title="Open the interactive globe">
          <GlobeSpinner cycle decorative size={120} />
        </Link>
      </div>
    </section>
  );
}

export function TheaterRank({ report, snap }: { report: Daily | null; snap: Snapshot | null }) {
  const rows = report ? topTheaters(report, snap) : [];
  if (!report || rows.length === 0) return null;
  const maxHeat = Math.max(0, ...report.theaters.filter((t) => t.kind === "section").map((t) => t.temperature.heat));
  return (
    <section className="hm-rank" aria-label="Theaters to watch">
      <p className="hm-sub">
        <span>Theaters</span>
        <span className="hm-sub-note">escalating first, then by heat</span>
      </p>
      <ol className="hm-rows">
        {rows.map(({ t, anchor, series }) => {
          const cat = categoryOf(t.name, t.headline, t.bottom_line);
          const flags = [...new Set(t.pulses.flatMap((p) => p.actors_iso2))].slice(0, FLAGS);
          return (
            <li key={anchor}>
              <Link href={`/geopolitics#${anchor}`} className={`hm-row vl-cat-${cat}`} title={t.name}>
                <DirTick direction={t.escalation.direction} />
                <span className="hm-row-flags">
                  <IsoFlags codes={flags} />
                </span>
                <span className="hm-row-name">{shortName(t.name)}</span>
                <span className="vl-chip hm-row-cat" title={CATEGORY_LABEL[cat]}>
                  <Glyph name={cat} size={16} />
                  <span className="vl-sr">{CATEGORY_LABEL[cat]}</span>
                </span>
                <span className="hm-row-heat">
                  <HeatBar share={shareOfMax(t.temperature.heat, maxHeat)} label={`${shortTheater(t.name)} heat`} />
                </span>
                <span className="hm-row-spark">
                  <Spark values={series} label={`${shortTheater(t.name)}: headlines per day, last ${series.length} days`} />
                </span>
                <span className="hm-row-dir">
                  <DirMark direction={t.escalation.direction} label />
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
      <p className="hm-all">
        <Link href="/intel/theaters" className="xt">
          All theaters
        </Link>
      </p>
    </section>
  );
}
