"use client";

import Glyph, { type GlyphName } from "@/components/vl/Glyph";
import { ANOMALY_COLOR, type LiveAnomaly } from "@/lib/live-shared";

// "Unusual right now": the places where Ohmega's own live memory (backend `live/memory`) finds ships, aircraft or fires far outside
// their learned normal for this hour of the week. One compact row each: what is counted, an arrow for above / below normal, and the
// plain sentence ("Strait of Hormuz: tankers 60% below normal for 18 h"). Tapping a row centres the map on the place. The words carry
// the meaning; colour and glyph only echo it. Nothing is drawn when nothing is flagged: a quiet board is not an alert.

const WHAT: Record<LiveAnomaly["layer"], GlyphName> = { ship: "ship", air: "aircraft", fire: "fire" };

export default function UnusualStrip({ rows, onPick }: { rows: LiveAnomaly[]; onPick: (a: LiveAnomaly) => void }) {
  if (rows.length === 0) return null;
  return (
    <section className="live-unusual" aria-label="Unusual right now">
      <p className="live-now-title">
        Unusual right now <span className="live-muted">· Ohmega analysis against its own learned normal, not a reported event</span>
      </p>
      <ul className="live-unusual-list">
        {rows.map((a) => (
          <li key={a.id}>
            <button type="button" className="live-unusual-row" onClick={() => onPick(a)} disabled={a.lat === null || a.lon === null}>
              <span className="live-unusual-glyph" style={{ color: ANOMALY_COLOR[a.direction] }} aria-hidden="true">
                <Glyph name={a.series === "ship.tanker" ? "tanker" : WHAT[a.layer]} size={16} />
                <Glyph name={a.direction === "above" ? "up" : "down"} size={12} />
              </span>
              <span className="live-unusual-text">
                {a.sentence}
                {a.ends_at !== null && <span className="live-muted"> (ended)</span>}
              </span>
              <span className="live-muted live-unusual-meta">
                {a.learning ? "learning · " : ""}
                {Math.round(a.confidence * 100)}%
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
