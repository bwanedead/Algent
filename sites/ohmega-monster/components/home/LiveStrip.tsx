import Link from "next/link";

import Glyph, { type GlyphName } from "@/components/vl/Glyph";
import { StatusDot } from "@/components/vl/primitives";
import { compact, whenUtc, type Headline, type LiveWorld, type Summary } from "@/lib/live-shared";
import { freshnessOf } from "@/lib/visual";

import LiveMiniMap from "./LiveMiniMap";
import "./home.css";

// Live on Home: a postage-stamp map plus an icon row of counts, the whole card one link to /live. Counts come only from the summary
// snapshot (ships and tankers inside the watched straits, fire detections, outage and quake alerts); a count of zero is not drawn, and
// the card is absent when the snapshot is unreachable (never an empty box).

type Count = { key: string; glyph: GlyphName; n: number; label: string; color: string };

function counts(summary: Summary): Count[] {
  const gates = Object.values(summary.gates ?? {});
  const sum = (pick: (g: (typeof gates)[number]) => number | undefined) => gates.reduce((a, g) => a + (pick(g) ?? 0), 0);
  const heads = (layer: Headline["layer"]) => summary.headlines.filter((h) => h.layer === layer).length;
  const all: Count[] = [
    { key: "ships", glyph: "ship", n: sum((g) => g.in_strait), label: "ships in straits", color: "--vl-l-ship" },
    { key: "tankers", glyph: "tanker", n: sum((g) => g.tankers), label: "tankers", color: "--vl-l-ship" },
    { key: "fires", glyph: "fire", n: summary.fires?.detections ?? 0, label: "fires seen", color: "--vl-l-fire" },
    { key: "outages", glyph: "outage", n: heads("outage"), label: "outages", color: "--vl-l-outage" },
    { key: "quakes", glyph: "quake", n: heads("quake"), label: "quakes", color: "--vl-l-quake" },
    { key: "air", glyph: "aircraft", n: heads("aircraft"), label: "air alerts", color: "--vl-l-air" },
  ];
  return all.filter((c) => c.n > 0);
}

export default function LiveStrip({ summary, world }: { summary: Summary | null; world: LiveWorld | null }) {
  if (!summary) return null;
  const items = counts(summary);
  if (items.length === 0 && summary.headlines.length === 0) return null;
  const state = freshnessOf(summary.as_of, Date.now());
  return (
    <section className="hm-live" aria-label="Live now">
      <Link href="/live" className="vl-card hm-live-card" aria-label="Open the live map">
        <LiveMiniMap world={world} headlines={summary.headlines} />
        <div className="hm-live-body">
          <p className="hm-live-head">
            <Glyph name="live" size={16} />
            <span className="vl-label">Live now</span>
            <StatusDot state={state} label={state === "fresh" ? "Updated minutes ago" : state === "aging" ? "Updated within two hours" : "Not updated recently"} />
            <span className="hm-live-when">{whenUtc(summary.as_of)}</span>
          </p>
          <ul className="hm-live-counts">
            {items.map((c) => (
              <li key={c.key} style={{ color: `var(${c.color})` }}>
                <Glyph name={c.glyph} size={20} />
                <span className="hm-live-n">{compact(c.n)}</span>
                <span className="vl-label">{c.label}</span>
              </li>
            ))}
          </ul>
        </div>
        <span className="hm-live-go" aria-hidden="true">→</span>
      </Link>
    </section>
  );
}
