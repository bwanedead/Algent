import Link from "next/link";

import Glyph, { type GlyphName } from "@/components/vl/Glyph";
import type { Door } from "@/lib/sections";
import { splitHint } from "@/lib/visual";

import "./doors.css";

// A grid of doors into the site: a glyph, one big numeral (or a short hint) and a short title. Used by Home and by the Intelligence
// directory. Each door is one whole link, so it is easy to hit on a phone. `lines` adds the one-line description under the title
// (the directory shows it; Home does not: the glyph, the numeral and the title are the whole message).
const GLYPH: Record<string, GlyphName> = {
  "/geopolitics": "globe",
  "/live": "live",
  "/intel/theaters": "theater",
  "/intel/actors": "actor",
  "/pulses": "pulse",
  "/intel/record": "record",
  "/articles": "article",
  "/radar": "radar",
  "/intel/situation": "pulse",
  "/intel/briefs": "article",
};

export default function Doors({ doors, label, lines = true }: { doors: Door[]; label: string; lines?: boolean }) {
  return (
    <ul className="doors" aria-label={label}>
      {doors.map((d) => {
        const { n, rest } = splitHint(d.hint);
        return (
          <li key={d.href}>
            <Link href={d.href} className="vl-card door">
              <span className="door-top">
                <span className="vl-chip">
                  <Glyph name={GLYPH[d.href] ?? "event"} size={20} />
                </span>
                {n ? <span className="vl-num door-n">{n}</span> : null}
                <span className="door-go" aria-hidden="true">→</span>
              </span>
              <span className="door-title">{d.title}</span>
              {n ? rest ? <span className="vl-label door-rest">{rest}</span> : null : d.hint ? <span className="vl-label door-rest">{d.hint}</span> : null}
              {lines && <span className="door-line">{d.line}</span>}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
