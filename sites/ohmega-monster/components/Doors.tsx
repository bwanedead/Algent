import Link from "next/link";

import Glyph, { type GlyphName } from "@/components/vl/Glyph";
import type { Door } from "@/lib/sections";
import { splitHint } from "@/lib/visual";

import "./doors.css";

// A compact, hairline-ruled index of the site's doors: glyph, title, and one tabular numeral (or a short hint) on the right. Used by
// Home and by the Intelligence directory. Each row is one whole link (a full-width target, easy to hit on a phone). `lines` adds
// the one-line description under the title (the directory shows it; Home does not).
const GLYPH: Record<string, GlyphName> = {
  "/geopolitics": "globe",
  "/intel/graph": "theater",
  "/intel/forecasts": "pulse",
  "/live": "live",
  "/intel/theaters": "theater",
  "/intel/actors": "actor",
  "/pulses": "pulse",
  "/intel/record": "record",
  "/articles": "article",
  "/headlines": "radar",
  "/calendar": "calendar",
  "/intel/sanctions": "sanction",
  "/intel/maritime": "ship",
  "/intel/attacks": "event",
  "/intel/gnss": "radar",
  "/intel/track-record": "pulse",
  "/intel/ai": "pulse",
  "/ai": "globe",
};

export default function Doors({ doors, label, lines = true }: { doors: Door[]; label: string; lines?: boolean }) {
  return (
    <ul className="doors" aria-label={label}>
      {doors.map((d) => {
        const { n, rest } = splitHint(d.hint);
        const note = n ? rest : d.hint;
        return (
          <li key={d.href}>
            <Link href={d.href} className="door">
              <span className="vl-chip door-glyph">
                <Glyph name={GLYPH[d.href] ?? "event"} size={18} />
              </span>
              <span className="door-text">
                <span className="door-title">{d.title}</span>
                {lines && <span className="door-line">{d.line}</span>}
              </span>
              <span className="door-meta">
                {n ? <span className="door-n">{n}</span> : null}
                {note ? <span className="vl-label door-rest">{note}</span> : null}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
