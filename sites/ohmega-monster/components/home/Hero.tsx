import Link from "next/link";

import GlobeSpinner from "@/components/GlobeSpinner";
import IsoFlags from "@/components/IsoFlags";
import { fmtDay, headlineOf, shortTheater, theaterAnchor, type Daily, type DailyTheater } from "@/lib/daily";
import { DIRECTION } from "@/lib/dossier-view";
import { SITE_DESCRIPTION } from "@/lib/site";

import "./home.css";

// Home's first screen: the state of the world today. The day's headline, then the few theaters that matter
// most (moving ones first), each one line with its direction and flags and a link to its section in the
// report. The globe turns beside it. Detail is one click away; nothing here asks to be read in full.

const SHOWN = 4;
const FLAGS = 2;

type Line = { t: DailyTheater; anchor: string };

/** Escalating theaters first, then by heat: the order a newcomer should meet them in. */
function topTheaters(report: Daily): Line[] {
  const rank = { rising: 0, easing: 1, steady: 2, unclear: 3 } as const;
  return report.theaters
    .map((t, i) => ({ t, anchor: theaterAnchor(t, i) }))
    .filter(({ t }) => t.kind === "section")
    .sort((a, b) => rank[a.t.escalation.direction] - rank[b.t.escalation.direction] || b.t.temperature.heat - a.t.temperature.heat)
    .slice(0, SHOWN);
}

export default function Hero({ report }: { report: Daily | null }) {
  const lines = report ? topTheaters(report) : [];
  return (
    <section className="hm-hero" aria-label="The world today">
      <div className="hm-hero-text">
        <p className="hm-kicker">{report ? `The world today · ${fmtDay(report.date)}` : "Ohmega Monster"}</p>
        <h1 className="hm-claim">{report?.headline || SITE_DESCRIPTION}</h1>
        {lines.length > 0 && (
          <ul className="hm-lines" aria-label="Theaters to watch">
            {lines.map(({ t, anchor }) => {
              const dir = DIRECTION[t.escalation.direction];
              const flags = [...new Set(t.pulses.flatMap((p) => p.actors_iso2))].slice(0, FLAGS);
              return (
                <li key={anchor}>
                  <Link href={`/geopolitics#${anchor}`} className="hm-line" title={t.name}>
                    <span className="hm-line-flags">
                      <IsoFlags codes={flags} />
                    </span>
                    <span className="hm-line-text">
                      <span className="hm-line-name">
                        {shortTheater(t.name)}
                        <span className={`hm-dir${t.escalation.direction === "rising" ? " is-up" : ""}`}>
                          {" "}
                          <span aria-hidden="true">{dir.glyph}</span>
                          <span className="hm-sr"> {dir.word}</span>
                        </span>
                      </span>
                      <span className="hm-line-claim">{headlineOf(t.headline, t.bottom_line, 110) || t.name}</span>
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
              Read today&apos;s report →
            </Link>
            <Link href="/intel/theaters" className="xt">
              All theaters →
            </Link>
          </p>
        )}
      </div>
      <div className="hm-globe">
        <GlobeSpinner cycle decorative size={160} />
      </div>
    </section>
  );
}
