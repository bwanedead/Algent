import Link from "next/link";

import Age from "@/components/Fresh";
import NewDot from "@/components/NewDot";
import Glyph, { type GlyphName } from "@/components/vl/Glyph";
import { isStale } from "@/lib/fresh";
import type { Door } from "@/lib/sections";
import { splitHint } from "@/lib/visual";

import "./doors.css";

// A compact, hairline-ruled index of the site's doors: glyph, title, one tabular numeral (or a short hint) and the product's as-of age
// on the right. Used by Home and the Data hub. Each row is one whole link (a full-width target, easy to hit on a phone). `lines` adds
// the one-line description under the title (the Data hub shows it; Home does not). A door with a `stamp` shows how old its product is
// (dimmed when late for its own cadence) and a dot when it has changed since the reader last followed it.
const GLYPH: Record<string, GlyphName> = {
  "/daily": "globe",
  "/situations": "theater",
  "/globe": "globe",
  "/explore": "pulse",
  "/intel/graph": "theater",
  "/intel/forecasts": "pulse",
  "/intel/track-record": "pulse",
  "/live": "live",
  "/intel/actors": "actor",
  "/pulses": "pulse",
  "/intel/record": "record",
  "/articles": "article",
  "/daily/headlines": "radar",
  "/calendar": "calendar",
  "/intel/sanctions": "sanction",
  "/intel/maritime": "ship",
  "/intel/ai": "energy",
  "/intel/attacks": "event",
  "/intel/gnss": "radar",
  "/intel/satellite": "globe",
  "/developers": "event",
  "/feed.xml": "article",
  "/llms.txt": "record",
};

/** Files (RSS, plain text) are not pages: a plain anchor, so the router never tries to render them. */
const isFile = (href: string): boolean => /\.(xml|txt|json)$/.test(href);

export default function Doors({ doors, label, lines = true }: { doors: Door[]; label: string; lines?: boolean }) {
  return (
    <ul className="doors" aria-label={label}>
      {doors.map((d) => {
        const { n, rest } = splitHint(d.hint);
        const note = n ? rest : d.hint;
        const inner = (
          <>
            <span className="vl-chip door-glyph">
              <Glyph name={GLYPH[d.href] ?? "event"} size={18} />
            </span>
            <span className="door-text">
              <span className="door-title">
                {d.title}
                {d.stamp && d.cadenceHours ? <NewDot id={`door:${d.href}`} stamp={d.stamp} stale={isStale(d.checked || d.stamp, d.cadenceHours)} /> : null}
              </span>
              {lines && <span className="door-line">{d.line}</span>}
            </span>
            <span className="door-meta">
              {n ? <span className="door-n">{n}</span> : null}
              {note ? <span className="vl-label door-rest">{note}</span> : null}
              {d.stamp && d.cadenceHours ? <Age stamp={d.stamp} checked={d.checked} cadenceHours={d.cadenceHours} /> : null}
            </span>
          </>
        );
        return <li key={d.href}>{isFile(d.href) ? <a href={d.href} className="door">{inner}</a> : <Link href={d.href} className="door">{inner}</Link>}</li>;
      })}
    </ul>
  );
}
