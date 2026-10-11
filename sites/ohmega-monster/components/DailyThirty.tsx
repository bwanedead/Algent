import Link from "next/link";

import type { Daily } from "@/lib/daily";
import { headlineOf, shortTheater, theaterAnchor } from "@/lib/daily";
import type { Direction } from "@/lib/intel";

import IsoFlags from "./IsoFlags";

// "The day in 30 seconds": the whole report for a newcomer, one line per theater (flags, the writer's headline,
// which way it is moving), each jumping to its section. Built only from fields the record already holds.

const ARROW: Record<Direction, { glyph: string; word: string; moving: boolean }> = {
  rising: { glyph: "▲", word: "rising", moving: true },
  steady: { glyph: "◆", word: "steady", moving: false },
  easing: { glyph: "▼", word: "easing", moving: true },
  unclear: { glyph: "?", word: "unclear", moving: false },
};
const MAX_LINES = 5;
const MAX_FLAGS = 3;

export default function DailyThirty({ report }: { report: Daily }) {
  const rows = report.theaters.slice(0, MAX_LINES);
  if (rows.length === 0) return null;
  return (
    <section className="geo-thirty" aria-label="The day in 30 seconds">
      <h2 className="geo-h2">The day in 30 seconds</h2>
      <ul>
        {rows.map((t, i) => {
          const a = ARROW[t.escalation.direction];
          const flags = [...new Set(t.pulses.flatMap((p) => p.actors_iso2))].slice(0, MAX_FLAGS);
          const line = headlineOf(t.headline, t.bottom_line, 120) || t.name;
          return (
            <li key={t.theater_id + i}>
              <Link href={`#${theaterAnchor(t, i)}`} className="geo-thirty-link" title={t.name}>
                <span className="geo-thirty-flags">
                  <IsoFlags codes={flags} />
                </span>
                <span className="geo-thirty-text">
                  <span className="geo-micro">{shortTheater(t.name)}</span> {line}
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
