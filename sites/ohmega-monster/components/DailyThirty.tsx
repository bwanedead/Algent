import Link from "next/link";

import type { Daily } from "@/lib/daily";
import { editionTag, headlineOf, shortTheater, theaterAnchor } from "@/lib/daily";
import type { Direction } from "@/lib/intel";

import IsoFlags from "./IsoFlags";

// "The day in 30 seconds": the whole report for a newcomer, one line per theater (flags, the writer's headline,
// which way it is moving), each jumping to its section. Built only from fields the record already holds. A report
// built in parts shows the whole day: later additions and updates are lines too, the newest first.

const ARROW: Record<Direction, { glyph: string; word: string; moving: boolean }> = {
  rising: { glyph: "▲", word: "rising", moving: true },
  steady: { glyph: "◆", word: "steady", moving: false },
  easing: { glyph: "▼", word: "easing", moving: true },
  unclear: { glyph: "?", word: "unclear", moving: false },
};
const MAX_LINES = 5; // per part of the day
const MAX_FLAGS = 3;

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
          const a = ARROW[t.escalation.direction];
          const flags = [...new Set(t.pulses.flatMap((p) => p.actors_iso2))].slice(0, MAX_FLAGS);
          const line = headlineOf(t.headline, t.bottom_line, 120) || t.name;
          return (
            <li key={t.theater_id + i}>
              <Link href={`#${anchor}`} className="geo-thirty-link" title={t.name}>
                <span className="geo-thirty-flags">
                  <IsoFlags codes={flags} />
                </span>
                <span className="geo-thirty-text">
                  <span className="geo-micro">
                    {update ? "Update · " : ""}
                    {shortTheater(t.name)}
                    {editionTag(report, t.edition) ? ` · ${editionTag(report, t.edition)}` : ""}
                  </span>{" "}
                  {line}
                </span>
                <span className={`geo-dir${a.moving ? " is-moving" : ""}`} title={`Direction: ${a.word}`}>
                  <span aria-hidden="true">{a.glyph}</span>
                  <span className="geo-sr"> {a.word}</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
