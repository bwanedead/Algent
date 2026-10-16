import Link from "next/link";

import type { Daily } from "@/lib/daily";
import { editionTag, headlineOf, shortTheater, theaterAnchor } from "@/lib/daily";
import { categoryOf } from "@/lib/visual";

import IsoFlags from "./IsoFlags";
import Glyph from "./vl/Glyph";
import { DirMark } from "./vl/primitives";

// "The day in 30 seconds": the whole report for a newcomer, one line per theater (flags, the writer's headline,
// which way it is moving), each jumping to its section. Built only from fields the record already holds. A report
// built in parts shows the whole day: later additions and updates are lines too, the newest first.

const MAX_LINES = 5; // per part of the day
const MAX_FLAGS = 3;

const line0 = (t: { headline: string; bottom_line: string }) => `${t.headline} ${t.bottom_line}`;

export default function DailyThirty({ report }: { report: Daily }) {
  // One line per section and per update, each with the anchor it jumps to; newest part first, stable within a part.
  const all = report.theaters.flatMap((t, i) => [
    { t, anchor: theaterAnchor(t, i), update: false },
    ...t.updates.map((u, k) => ({ t: u, anchor: `${theaterAnchor(t, i)}-update-${k + 1}`, update: true })),
  ]);
  const parts = Math.max(1, report.editions.length);
  const rows = [...all].sort((a, b) => b.t.edition - a.t.edition).slice(0, MAX_LINES * parts);
  if (rows.length === 0) return null;
  return (
    <section className="geo-thirty" aria-label="The day in 30 seconds">
      <h2 className="geo-h2">The day in 30 seconds</h2>
      <ul>
        {rows.map(({ t, anchor, update }, i) => {
          const cat = categoryOf(t.name, line0(t));
          const flags = [...new Set(t.pulses.flatMap((p) => p.actors_iso2))].slice(0, MAX_FLAGS);
          const line = headlineOf(t.headline, t.bottom_line, 120) || t.name;
          return (
            <li key={t.theater_id + i} className={`vl-cat-${cat}`}>
              <Link href={`#${anchor}`} className="geo-thirty-link" title={t.name}>
                <span className="vl-chip">
                  <Glyph name={cat} size={16} />
                </span>
                <span className="geo-thirty-text">
                  <span className="geo-thirty-meta">
                    <IsoFlags codes={flags} />
                    <span className="geo-micro">
                      {update ? "Update · " : ""}
                      {shortTheater(t.name)}
                      {editionTag(report, t.edition) ? ` · ${editionTag(report, t.edition)}` : ""}
                    </span>
                  </span>
                  {line}
                </span>
                <DirMark direction={t.escalation.direction} />
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
